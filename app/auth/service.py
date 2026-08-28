"""Fronteira publica do modulo auth. Nenhum outro modulo importa auth.models."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.models import Clinica, Usuario
from app.auth.senha import TAMANHO_MINIMO_SENHA, conferir, gerar_hash


def autenticar(sessao: Session, email: str, senha: str) -> Usuario | None:
    """Devolve o usuario ou None. Nao distingue 'email nao existe' de 'senha errada':
    a tela nao deve confirmar quais emails existem."""
    if not email or not senha:
        return None
    usuario = sessao.scalars(
        select(Usuario).where(Usuario.email == email.strip().lower())
    ).first()
    if usuario is None or not usuario.ativo:
        return None
    if not conferir(senha, usuario.senha_hash):
        return None
    return usuario


def criar_usuario(
    sessao: Session, *, clinica_id: int, email: str, senha: str, nome: str
) -> Usuario:
    usuario = Usuario(
        clinica_id=clinica_id,
        email=email.strip().lower(),
        senha_hash=gerar_hash(senha),
        nome=nome.strip(),
    )
    sessao.add(usuario)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario.id,
        acao="CRIAR",
        entidade="usuario",
        entidade_id=usuario.id,
        depois={"email": usuario.email, "nome": usuario.nome},
    )
    return usuario


class SenhaRecusada(ValueError):
    """A troca de senha nao passou. A mensagem vai para a tela como esta."""


def renomear(sessao: Session, usuario: Usuario, *, nome: str) -> Usuario:
    nome = nome.strip()
    if not nome:
        raise ValueError("o nome nao pode ficar vazio")
    antes = usuario.nome
    usuario.nome = nome
    registrar(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        acao="ATUALIZAR",
        entidade="usuario",
        entidade_id=usuario.id,
        antes={"nome": antes},
        depois={"nome": nome},
    )
    return usuario


def trocar_senha(
    sessao: Session, usuario: Usuario, *, atual: str, nova: str, repetida: str
) -> Usuario:
    """Troca a senha depois de conferir a atual.

    Exigir a senha atual e o que impede que um computador deixado aberto na
    recepcao vire uma troca de dono da conta.

    A auditoria registra que houve troca e quando — nunca a senha nem o hash. O
    `_sem_segredo()` do modulo de auditoria e a segunda barreira disso.
    """
    if not conferir(atual, usuario.senha_hash):
        raise SenhaRecusada("a senha atual nao confere")
    if nova != repetida:
        raise SenhaRecusada("a senha nova e a repeticao nao conferem")
    if len(nova) < TAMANHO_MINIMO_SENHA:
        raise SenhaRecusada(
            f"senha curta demais: use ao menos {TAMANHO_MINIMO_SENHA} caracteres. "
            "Esta senha abre 30 anos de prontuario."
        )
    if conferir(nova, usuario.senha_hash):
        raise SenhaRecusada("a senha nova precisa ser diferente da atual")

    usuario.senha_hash = gerar_hash(nova)
    registrar(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        acao="ATUALIZAR",
        entidade="usuario",
        entidade_id=usuario.id,
        antes={"senha_trocada": False},
        depois={"senha_trocada": True},
    )
    return usuario


def ids_de_clinica(sessao: Session) -> list[int]:
    """As clinicas que existem, em ordem — para quem precisa rodar por todas.

    Existe para o relogio dos lembretes nao precisar chutar. Ele supunha
    `clinica_id = 1`, e em 28/08/2026 a clinica de producao tinha outro id: TODA
    batida morria em `ForeignKeyViolation` antes de olhar um horario, e nenhum
    lembrete saiu. Chave primaria e surrogate — ela e o que o banco decidiu, nao
    o que o codigo espera.

    Devolve so os ids: quem chama nao precisa de `auth.models` para percorrer as
    clinicas, e a fronteira de modulo (§2) continua de pe.
    """
    return list(sessao.scalars(select(Clinica.id).order_by(Clinica.id)))


@dataclass(frozen=True)
class IdentidadeDaClinica:
    """Como a clinica se apresenta para fora — nada mais que isso.

    Existe para outro modulo nao precisar importar `auth.models` so para
    escrever "Consultorio Dra. Katia" numa mensagem.
    """

    clinica: str
    dentista: str


def identidade_da_clinica(sessao: Session, *, clinica_id: int) -> IdentidadeDaClinica:
    """O nome da clinica e o de quem atende.

    Um usuario so, sem papeis: quem atende e o usuario ativo da clinica. Se nao
    houver nenhum (base recem-criada), o nome da clinica serve para os dois — e
    melhor do que uma mensagem assinada por ninguem.
    """
    clinica = sessao.get(Clinica, clinica_id)
    nome_da_clinica = clinica.nome if clinica else ""
    dentista = sessao.scalars(
        select(Usuario.nome)
        .where(Usuario.clinica_id == clinica_id, Usuario.ativo.is_(True))
        .order_by(Usuario.id)
        .limit(1)
    ).one_or_none()
    return IdentidadeDaClinica(
        clinica=nome_da_clinica, dentista=dentista or nome_da_clinica
    )
