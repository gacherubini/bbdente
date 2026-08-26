"""Fronteira publica do modulo pacientes."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalogo.service import nomes_de_convenio
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.telefone import formatar, parecer_incompleto

# "Ativo" = veio nos ultimos 4 anos. Sao 494 dos 5.561 no banco real.
ANOS_PARA_SER_ATIVO = 4
LIMITE_PADRAO = 100


class Filtro(StrEnum):
    ATIVOS = "ativos"
    COM_PENDENCIA = "com_pendencia"
    EM_ABERTO = "em_aberto"
    TODOS = "todos"


@dataclass
class LinhaPaciente:
    id: int
    nome: str
    codigo_legado: str | None
    idade: int | None
    telefone: str | None
    telefone_suspeito: bool
    ultimo_atendimento: date | None
    data_suspeita: bool
    convenio: str | None
    pendentes: int
    em_aberto: Decimal
    revisar_motivo: list[str] = field(default_factory=list)


def _idade(nascimento: date | None) -> int | None:
    if nascimento is None:
        return None
    hoje = date.today()
    return (
        hoje.year
        - nascimento.year
        - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
    )


def _corte_de_atividade() -> date:
    hoje = date.today()
    try:
        return hoje.replace(year=hoje.year - ANOS_PARA_SER_ATIVO)
    except ValueError:
        # 29 de fevereiro: o ano de 4 anos atras pode nao ter o dia 29.
        return hoje.replace(year=hoje.year - ANOS_PARA_SER_ATIVO, day=28)


def obter(sessao: Session, *, clinica_id: int, paciente_id: int) -> Paciente | None:
    return sessao.scalars(
        select(Paciente).where(
            Paciente.id == paciente_id,
            Paciente.clinica_id == clinica_id,
            Paciente.excluido_em.is_(None),
        )
    ).first()


def contagens(sessao: Session, *, clinica_id: int) -> dict[str, int]:
    """Numeros do cabecalho. Tres agregacoes no banco — nunca carregando a base.

    A versao ingenua chamaria buscar() e contaria em Python: com 5.561 pacientes
    isso seria uma varredura completa a cada abertura da tela.
    """
    from app.clinico.service import contar_pacientes_com_pendencia

    base = select(func.count()).select_from(Paciente).where(
        Paciente.clinica_id == clinica_id, Paciente.excluido_em.is_(None)
    )
    return {
        "total": sessao.scalars(base).one(),
        "ativos": sessao.scalars(
            base.where(Paciente.ultimo_atendimento >= _corte_de_atividade())
        ).one(),
        "com_pendencia": contar_pacientes_com_pendencia(sessao, clinica_id=clinica_id),
    }


def buscar(
    sessao: Session,
    *,
    clinica_id: int,
    termo: str = "",
    filtro: Filtro = Filtro.ATIVOS,
    limite: int | None = LIMITE_PADRAO,
) -> list[LinhaPaciente]:
    consulta = (
        select(Paciente)
        .options(selectinload(Paciente.telefones))
        .where(Paciente.clinica_id == clinica_id, Paciente.excluido_em.is_(None))
        .order_by(Paciente.nome)
    )

    termo = (termo or "").strip()
    if termo:
        padrao = f"%{termo}%"
        so_digitos = "".join(c for c in termo if c.isdigit())
        condicoes = [Paciente.nome.ilike(padrao), Paciente.codigo_legado.ilike(padrao)]
        if so_digitos:
            condicoes.append(
                Paciente.id.in_(
                    select(PacienteTelefone.paciente_id).where(
                        PacienteTelefone.numero.like(f"%{so_digitos}%")
                    )
                )
            )
        consulta = consulta.where(or_(*condicoes))
    elif filtro is Filtro.ATIVOS:
        consulta = consulta.where(Paciente.ultimo_atendimento >= _corte_de_atividade())

    # COM_PENDENCIA e EM_ABERTO sao peneirados em Python depois da consulta, entao
    # trazemos uma folga do banco para o limite final ainda poder ser preenchido.
    if limite is not None:
        folga = limite * 10 if filtro in (Filtro.COM_PENDENCIA, Filtro.EM_ABERTO) else limite
        consulta = consulta.limit(folga)

    # Import aqui dentro, nao no topo: clinico.service importa pacientes.service,
    # e importar nos dois sentidos no topo trava o Python com import circular.
    from app.clinico.service import resumo_por_paciente

    pacientes = list(sessao.scalars(consulta))
    resumo = resumo_por_paciente(
        sessao, clinica_id=clinica_id, paciente_ids=[p.id for p in pacientes]
    )
    convenios = nomes_de_convenio(
        sessao,
        clinica_id=clinica_id,
        convenio_ids={p.convenio_id for p in pacientes if p.convenio_id},
    )

    linhas: list[LinhaPaciente] = []
    for paciente in pacientes:
        pendentes, em_aberto = resumo.get(paciente.id, (0, Decimal("0.00")))
        if filtro is Filtro.COM_PENDENCIA and not pendentes:
            continue
        if filtro is Filtro.EM_ABERTO and em_aberto <= 0:
            continue

        principal = next(
            (t for t in paciente.telefones if t.principal), None
        ) or next(iter(paciente.telefones), None)

        linhas.append(
            LinhaPaciente(
                id=paciente.id,
                nome=paciente.nome,
                codigo_legado=paciente.codigo_legado,
                idade=_idade(paciente.nascimento),
                telefone=formatar(principal.numero) if principal else None,
                telefone_suspeito=bool(principal)
                and parecer_incompleto(principal.numero),
                ultimo_atendimento=paciente.ultimo_atendimento,
                data_suspeita="data_suspeita" in (paciente.revisar_motivo or []),
                convenio=convenios.get(paciente.convenio_id),
                pendentes=pendentes,
                em_aberto=em_aberto,
                revisar_motivo=list(paciente.revisar_motivo or []),
            )
        )
    if limite is not None:
        return linhas[:limite]
    return linhas
