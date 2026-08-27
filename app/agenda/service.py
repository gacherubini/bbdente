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
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agenda.models import DURACAO_PADRAO_MIN, Agendamento, SituacaoAgendamento
from app.auth.auditoria import registrar
from app.clinico.service import atendidos_por_dia
from app.pacientes.service import contatos_de
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


# A faixa de horas da grade sai do dado, com piso e teto: sem horario de
# funcionamento configuravel no primeiro corte (§8 do plano).
PRIMEIRA_HORA_PADRAO = 8
ULTIMA_HORA_PADRAO = 19


@dataclass(frozen=True)
class Periodo:
    """Um retangulo de dias. A semana e o mes sao o mesmo objeto — e por isso a
    tela e uma rota so com duas vistas."""

    de: date
    ate: date

    @property
    def dias(self) -> list[date]:
        return [
            self.de + timedelta(days=n) for n in range((self.ate - self.de).days + 1)
        ]


def semana_de(dia: date) -> Periodo:
    """Segunda a domingo.

    Domingo entra mesmo com o consultorio fechado: e mais barato mostrar uma
    coluna vazia do que explicar por que o horario marcado num domingo sumiu.
    """
    segunda = dia - timedelta(days=dia.weekday())
    return Periodo(de=segunda, ate=segunda + timedelta(days=6))


def mes_de(dia: date) -> Periodo:
    """A grade retangular do mes: da segunda da semana do dia 1 ao domingo da
    semana do ultimo dia. Sem isso a primeira linha teria buracos e fevereiro
    mudaria de formato."""
    primeiro = dia.replace(day=1)
    seguinte = (primeiro + timedelta(days=32)).replace(day=1)
    ultimo = seguinte - timedelta(days=1)
    return Periodo(de=semana_de(primeiro).de, ate=semana_de(ultimo).ate)


@dataclass(frozen=True)
class Cartao:
    """Um horario, pronto para a tela. Sem objeto do banco e sem consulta nova."""

    id: int
    paciente_id: int | None
    nome: str
    telefone: str | None
    dia: date
    inicio: time
    fim: time
    duracao_min: int
    situacao: str
    observacao: str | None
    atendida: bool

    @property
    def desmarcado(self) -> bool:
        return self.situacao == SituacaoAgendamento.DESMARCADO.value

    @property
    def ocupa_horario(self) -> bool:
        return self.situacao in {s.value for s in SITUACOES_VIVAS}


@dataclass(frozen=True)
class Grade:
    """O periodo inteiro montado. A tela nao consulta nada — so le daqui."""

    periodo: Periodo
    cartoes: dict[date, list[Cartao]]
    sem_hora: dict[date, list[Contato]]
    primeira_hora: int
    ultima_hora: int

    def do_dia(self, dia: date) -> list[Cartao]:
        return self.cartoes.get(dia, [])

    @property
    def horas(self) -> list[int]:
        """As linhas da grade. Uma por hora — a leitura da semana e por hora, e
        dobrar as linhas dobrava a rolagem para mostrar o mesmo dia.

        Cada linha tem DUAS secoes por dentro (§`no_slot`): a de cima marca em
        ponto, a de baixo na meia. Consulta de 30 minutos e a mais comum, e sem
        as duas secoes marcar as 09:30 exigia corrigir a hora na mao.
        """
        return list(range(self.primeira_hora, self.ultima_hora + 1))

    def no_slot(self, dia: date, hora: int, minuto: int) -> list[Cartao]:
        """Os cartoes daquela meia hora.

        Hora quebrada (09:15, 09:45) cai na faixa que ja comecou — encaixe nao
        respeita grade, e o horario nao pode sumir da tela por nao bater com o
        relogio.
        """
        return [
            cartao
            for cartao in self.do_dia(dia)
            if cartao.inicio.hour == hora
            and (cartao.inicio.minute >= 30) == (minuto >= 30)
        ]

    def sem_hora_no_dia(self, dia: date) -> list[Contato]:
        """Quem foi atendido no dia sem ter horario marcado.

        Vem do prontuario, e e por isso que nao tem hora: `lancamento` guarda
        data, nunca hora (§8 do plano).
        """
        return self.sem_hora.get(dia, [])

    def quantos_no_dia(self, dia: date) -> int:
        """Quantos ocupam o dia. O desmarcado sai da contagem sem sair da tela."""
        return sum(1 for cartao in self.do_dia(dia) if cartao.ocupa_horario)


def grade(sessao: Session, *, clinica_id: int, periodo: Periodo) -> Grade:
    """Monta a semana ou o mes em tres consultas, sempre.

    Fica aqui, e nao na rota, porque semana e mes montam a mesma coisa — na rota
    seria a mesma montagem escrita duas vezes, e a segunda envelheceria.

    As tres: os horarios do periodo, quem foi atendido em cada dia (do prontuario,
    pela service do `clinico`), e nome/telefone de todo mundo que apareceu nas
    duas primeiras — de uma vez, nunca por cartao.
    """
    agendamentos = sessao.scalars(
        select(Agendamento)
        .where(
            Agendamento.clinica_id == clinica_id,
            Agendamento.dia.between(periodo.de, periodo.ate),
            Agendamento.excluido_em.is_(None),
        )
        .order_by(Agendamento.dia, Agendamento.inicio, Agendamento.id)
    ).all()

    atendidos = atendidos_por_dia(
        sessao, clinica_id=clinica_id, de=periodo.de, ate=periodo.ate
    )

    interessados = {a.paciente_id for a in agendamentos if a.paciente_id is not None}
    for do_dia in atendidos.values():
        interessados |= do_dia
    contatos = contatos_de(sessao, clinica_id=clinica_id, paciente_ids=interessados)

    cartoes: dict[date, list[Cartao]] = {}
    for agendamento in agendamentos:
        nome, telefone = contatos.get(
            agendamento.paciente_id, (agendamento.nome_avulso or "", agendamento.telefone_avulso)
        )
        cartoes.setdefault(agendamento.dia, []).append(
            Cartao(
                id=agendamento.id,
                paciente_id=agendamento.paciente_id,
                nome=nome,
                telefone=telefone,
                dia=agendamento.dia,
                inicio=agendamento.inicio,
                fim=agendamento.fim,
                duracao_min=agendamento.duracao_min,
                situacao=agendamento.situacao.value,
                observacao=agendamento.observacao,
                atendida=agendamento.paciente_id in atendidos.get(agendamento.dia, ()),
            )
        )

    sem_hora: dict[date, list[Contato]] = {}
    for dia, do_dia in atendidos.items():
        com_horario = {c.paciente_id for c in cartoes.get(dia, [])}
        faltantes = [
            Contato(nome=contatos[pid][0], telefone=contatos[pid][1], paciente_id=pid)
            for pid in sorted(do_dia - com_horario)
            if pid in contatos
        ]
        if faltantes:
            sem_hora[dia] = faltantes

    return Grade(
        periodo=periodo,
        cartoes=cartoes,
        sem_hora=sem_hora,
        primeira_hora=min(
            [PRIMEIRA_HORA_PADRAO] + [a.inicio.hour for a in agendamentos]
        ),
        ultima_hora=max(
            [ULTIMA_HORA_PADRAO] + [a.fim.hour + (1 if a.fim.minute else 0) for a in agendamentos]
        ),
    )


def vincular_paciente(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int | None,
    agendamento_id: int,
    paciente_id: int,
) -> bool:
    """Da dono ao horario avulso quando o atendimento dele e concluido.

    **Nunca levanta excecao, nunca deixa a sessao suja.** Quem chama e o
    `clinico.api`, depois de o prontuario ja estar gravado — e o prontuario e
    mais importante que a agenda. Um id velho numa aba aberta ha uma hora, um
    horario de outra clinica ou um horario que ja tem dono nao podem fazer um
    tratamento se perder. Devolve se vinculou, para quem quiser contar.

    Horario que ja tem `paciente_id` fica como esta: reescrever de quem era
    aquele horario seria apagar a historia sem ninguem pedir.
    """
    agendamento = obter(sessao, clinica_id=clinica_id, agendamento_id=agendamento_id)
    if agendamento is None or agendamento.paciente_id is not None:
        return False

    antes = _retrato(agendamento)
    agendamento.paciente_id = paciente_id
    # O nome digitado ao telefone sai: quem manda agora e o cadastro. O que foi
    # escrito ali continua legivel na auditoria.
    agendamento.nome_avulso = None
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="VINCULAR",
        entidade="agendamento",
        entidade_id=agendamento.id,
        antes=antes,
        depois=_retrato(agendamento),
    )
    return True
