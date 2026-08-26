"""Fronteira publica do modulo clinico.

Quando o modulo financeiro chegar, ele chama funcoes daqui — nunca consulta a
tabela lancamento direto.
"""

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clinico.models import Lancamento, Odontograma
from app.shared.tipos import StatusLancamento


def contar_pacientes_com_pendencia(sessao: Session, *, clinica_id: int) -> int:
    """Quantos pacientes tem ao menos um tratamento planejado. Uma agregacao so."""
    return sessao.scalars(
        select(func.count(func.distinct(Odontograma.paciente_id)))
        .select_from(Odontograma)
        .join(Lancamento, Lancamento.odontograma_id == Odontograma.id)
        .where(
            Lancamento.clinica_id == clinica_id,
            Lancamento.status == StatusLancamento.PLANEJADO,
            Lancamento.excluido_em.is_(None),
        )
    ).one()


def resumo_por_paciente(
    sessao: Session, *, clinica_id: int, paciente_ids: Iterable[int]
) -> dict[int, tuple[int, Decimal]]:
    """Para cada paciente, quantos tratamentos estao pendentes e quanto somam.

    Uma consulta agregada para a lista inteira — nunca uma por linha da tabela.
    """
    ids = list(paciente_ids)
    if not ids:
        return {}
    linhas = sessao.execute(
        select(
            Odontograma.paciente_id,
            func.count(Lancamento.id),
            func.coalesce(func.sum(Lancamento.valor), 0),
        )
        .join(Lancamento, Lancamento.odontograma_id == Odontograma.id)
        .where(
            Odontograma.paciente_id.in_(ids),
            Lancamento.clinica_id == clinica_id,
            Lancamento.status == StatusLancamento.PLANEJADO,
            Lancamento.excluido_em.is_(None),
        )
        .group_by(Odontograma.paciente_id)
    ).all()
    resumo: defaultdict[int, tuple[int, Decimal]] = defaultdict(
        lambda: (0, Decimal("0.00"))
    )
    for paciente_id, pendentes, soma in linhas:
        resumo[paciente_id] = (pendentes, Decimal(soma).quantize(Decimal("0.01")))
    return dict(resumo)
