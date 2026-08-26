"""Fronteira publica do modulo auth. Nenhum outro modulo importa auth.models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.models import Usuario
from app.auth.senha import conferir, gerar_hash


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
