"""Fronteira publica do modulo catalogo."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Convenio


def nomes_de_convenio(
    sessao: Session, *, clinica_id: int, convenio_ids: Iterable[int]
) -> dict[int, str]:
    """Uma consulta para a lista inteira. Outros modulos guardam convenio_id e
    perguntam o nome aqui — nunca fazem JOIN na tabela convenio."""
    ids = list(convenio_ids)
    if not ids:
        return {}
    return {
        c.id: c.nome
        for c in sessao.scalars(
            select(Convenio).where(
                Convenio.clinica_id == clinica_id, Convenio.id.in_(ids)
            )
        )
    }
