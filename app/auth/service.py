"""Fronteira publica do modulo auth. Nenhum outro modulo importa auth.models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.models import Usuario
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
