"""Registro de toda escrita da aplicacao.

Exigencia de LGPD e a unica forma de responder 'quem mudou este prontuario, quando,
e o que estava la antes'. Chamado por todos os service.py — nao ha escrita sem linha
aqui.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.auth.models import Auditoria

CAMPOS_PROIBIDOS = frozenset({"senha", "senha_hash", "token"})


def _sem_segredo(dados: dict[str, Any] | None) -> dict[str, Any] | None:
    """Auditoria nunca guarda credencial — nem em hash."""
    if dados is None:
        return None
    return {k: v for k, v in dados.items() if k.lower() not in CAMPOS_PROIBIDOS}


def registrar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int | None,
    acao: str,
    entidade: str,
    entidade_id: int | None,
    antes: dict[str, Any] | None = None,
    depois: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    sessao.add(
        Auditoria(
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            dados_antes=_sem_segredo(antes),
            dados_depois=_sem_segredo(depois),
            ip=ip,
        )
    )
