"""Regras da agenda.

Tres delas decidem se a tela vai ser usada ou se ela volta para o papel:

1. **Horario avulso e caminho normal**, nao excecao. Quem liga nem sempre e da
   base, e exigir cadastro antes de anotar um telefonema custa mais do que a
   agenda vale.
2. **Conflito avisa, nunca bloqueia.** Encaixe, urgencia e acompanhante
   acontecem de verdade; um sistema que proibe e um sistema contornado.
3. **Desmarcar nao apaga.** `situacao` guarda a historia; `excluido_em` e so
   para engano.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agenda.models import DURACAO_PADRAO_MIN, Agendamento, SituacaoAgendamento
from app.auth.auditoria import registrar
from app.pacientes.service import obter as obter_paciente
from app.pacientes.telefone import formatar

# Quem nao ocupa mais o horario: nao conflita com ninguem, nao conta na grade.
SITUACOES_VIVAS = (SituacaoAgendamento.MARCADO, SituacaoAgendamento.CONFIRMADO)


class SemDono(ValueError):
    """Horario sem paciente e sem nome nenhum — nao responde "quem vem"."""


class PacienteDeOutraClinica(ValueError):
    pass


class NaoEncontrado(LookupError):
    pass


def _limpo(texto: str | None) -> str | None:
    limpo = (texto or "").strip()
    return limpo or None


def _minutos(hora: time) -> int:
    return hora.hour * 60 + hora.minute


@dataclass(frozen=True)
class Contato:
    """O que a agenda sabe de quem vem — sem tocar no prontuario."""

    nome: str
    telefone: str | None
    paciente_id: int | None


def obter(
    sessao: Session, *, clinica_id: int, agendamento_id: int
) -> Agendamento | None:
    return sessao.scalars(
        select(Agendamento).where(
            Agendamento.id == agendamento_id,
            Agendamento.clinica_id == clinica_id,
            Agendamento.excluido_em.is_(None),
        )
    ).one_or_none()


def _exigir(sessao: Session, *, clinica_id: int, agendamento_id: int) -> Agendamento:
    agendamento = obter(sessao, clinica_id=clinica_id, agendamento_id=agendamento_id)
    if agendamento is None:
        raise NaoEncontrado(agendamento_id)
    return agendamento


def marcar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int | None,
    dia: date,
    inicio: time,
    duracao_min: int = DURACAO_PADRAO_MIN,
    paciente_id: int | None = None,
    nome_avulso: str | None = None,
    telefone_avulso: str | None = None,
    observacao: str | None = None,
) -> Agendamento:
    """Marca um horario. De paciente cadastrada ou de um telefonema avulso.

    Nao recusa telefone estranho: a mesma regra do CPF suspeito e do numero
    incompleto na migracao — dado esquisito e guardado como veio, nunca barra
    quem esta com a paciente na linha.
    """
    nome_avulso = _limpo(nome_avulso)
    if paciente_id is None and not nome_avulso:
        raise SemDono("horario precisa de paciente ou de um nome")

    if paciente_id is not None:
        # Pela service do outro modulo, nunca por JOIN — e e aqui que se descobre
        # que a paciente e de outra clinica.
        if obter_paciente(sessao, clinica_id=clinica_id, paciente_id=paciente_id) is None:
            raise PacienteDeOutraClinica(paciente_id)
        nome_avulso = None

    agendamento = Agendamento(
        clinica_id=clinica_id,
        paciente_id=paciente_id,
        nome_avulso=nome_avulso,
        telefone_avulso=_telefone(telefone_avulso) if paciente_id is None else None,
        dia=dia,
        inicio=inicio,
        duracao_min=duracao_min,
        observacao=_limpo(observacao),
        criado_por=usuario_id,
    )
    sessao.add(agendamento)
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="MARCAR",
        entidade="agendamento",
        entidade_id=agendamento.id,
        depois=_retrato(agendamento),
    )
    return agendamento


def _telefone(bruto: str | None) -> str | None:
    """A mesma regua do cadastro — `pacientes/telefone.py`, uma so no sistema.

    `formatar()` devolve o numero como veio quando nao reconhece o formato; e
    proposital, e por isso nao ha ramo de erro aqui.
    """
    limpo = _limpo(bruto)
    return formatar(limpo) if limpo else None


def _retrato(agendamento: Agendamento) -> dict:
    """O que vai para a auditoria. So o que muda e so o que da para ler depois."""
    return {
        "paciente_id": agendamento.paciente_id,
        "nome_avulso": agendamento.nome_avulso,
        "dia": agendamento.dia.isoformat(),
        "inicio": agendamento.inicio.isoformat(),
        "duracao_min": agendamento.duracao_min,
        "situacao": agendamento.situacao.value,
        "observacao": agendamento.observacao,
    }


def remarcar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int | None,
    agendamento_id: int,
    dia: date,
    inicio: time,
    duracao_min: int,
    observacao: str | None = None,
) -> Agendamento:
    """Muda quando e por quanto tempo.

    Nao existe tabela de historico de remarcacao porque o antes e o depois ficam
    na auditoria — uma verdade so, no lugar onde ja se procura por ela.
    """
    agendamento = _exigir(
        sessao, clinica_id=clinica_id, agendamento_id=agendamento_id
    )
    antes = _retrato(agendamento)

    agendamento.dia = dia
    agendamento.inicio = inicio
    agendamento.duracao_min = duracao_min
    agendamento.observacao = _limpo(observacao)
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="REMARCAR",
        entidade="agendamento",
        entidade_id=agendamento.id,
        antes=antes,
        depois=_retrato(agendamento),
    )
    return agendamento


def mudar_situacao(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int | None,
    agendamento_id: int,
    situacao: SituacaoAgendamento,
) -> Agendamento:
    """Confirmar, marcar falta ou desmarcar.

    Desmarcar entra aqui, e nao em `excluir`, de proposito: o horario continua
    na tela, riscado, para que ninguem remarque em cima achando que aquilo
    sempre esteve vazio.
    """
    agendamento = _exigir(
        sessao, clinica_id=clinica_id, agendamento_id=agendamento_id
    )
    antes = _retrato(agendamento)

    agendamento.situacao = situacao
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="SITUACAO",
        entidade="agendamento",
        entidade_id=agendamento.id,
        antes=antes,
        depois=_retrato(agendamento),
    )
    return agendamento


def excluir(
    sessao: Session, *, clinica_id: int, usuario_id: int | None, agendamento_id: int
) -> Agendamento:
    """Foi engano — marcou no dia errado, duplicou. Exclusao logica, como todo o
    resto do sistema. Quem desmarcou usa `mudar_situacao`."""
    agendamento = _exigir(
        sessao, clinica_id=clinica_id, agendamento_id=agendamento_id
    )
    antes = _retrato(agendamento)

    agendamento.excluido_em = datetime.now(UTC)
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="EXCLUIR",
        entidade="agendamento",
        entidade_id=agendamento.id,
        antes=antes,
    )
    return agendamento


def conflitos_de(sessao: Session, *, agendamento: Agendamento) -> list[Agendamento]:
    """Quem mais ocupa esta faixa no mesmo dia.

    Serve para AVISAR. Bloquear seria proibir encaixe, urgencia e acompanhante —
    coisas que acontecem de verdade e que fariam a agenda voltar para o papel.

    Horario encostado nao conflita: quem termina 09:30 nao briga com quem comeca
    09:30, senao o aviso apareceria em toda consulta seguida e viraria ruido.
    """
    if agendamento.situacao not in SITUACOES_VIVAS:
        return []

    inicio = _minutos(agendamento.inicio)
    fim = inicio + agendamento.duracao_min
    vizinhos = sessao.scalars(
        select(Agendamento).where(
            Agendamento.clinica_id == agendamento.clinica_id,
            Agendamento.dia == agendamento.dia,
            Agendamento.id != agendamento.id,
            Agendamento.excluido_em.is_(None),
            Agendamento.situacao.in_(SITUACOES_VIVAS),
        )
    ).all()

    return [
        vizinho
        for vizinho in vizinhos
        if _minutos(vizinho.inicio) < fim
        and _minutos(vizinho.inicio) + vizinho.duracao_min > inicio
    ]
