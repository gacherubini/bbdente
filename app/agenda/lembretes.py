"""Reservar e despachar o lembrete da vespera.

**Cada lembrete tem a SUA hora.** O vencimento e `consulta - antecedencia`, e
`agenda/relogio.py` bate de 15 em 15 minutos ate passar por ele: consulta das 21h
e avisada as 21h da vespera, a das 8h as 8h da vespera. Nao existe "hora do
disparo" — existe a hora de cada paciente. E a janela da reserva e a propria
antecedencia, entao um horario so vira candidato quando falta exatamente ela.

Duas fases, e a ordem importa:

1. **Reservar** — so banco, nenhuma rede. Decide quem recebe e quem nao, cria a
   linha e commita. Se o processo morrer aqui, ninguem recebeu nada.
2. **Despachar** — uma mensagem por vez, marcando `ENVIANDO` e commitando ANTES
   de tocar na rede.

Fica uma janela impossivel de fechar: a mensagem sai e o processo morre antes do
commit. A linha fica `ENVIANDO` para sempre, e **`ENVIANDO` nunca e reenviado
automaticamente** — vai para a tela como "nao sei se saiu", para uma pessoa
decidir. A garantia escolhida e **no maximo uma vez, nunca ao menos uma vez**:
mandar duas vezes queima a paciente e e o padrao que a deteccao procura.

`agora` entra por parametro e e RELOGIO DE PAREDE da clinica (§4 do plano):
nenhuma funcao daqui chama `datetime.now()` por dentro. Hora que vem do BANCO e
outra historia — as colunas sao `timestamptz` e voltam em UTC, enquanto a clinica
vive em UTC-3. Toda leitura dessas passa por `parede()`; leia o porque la.
"""

import random
import time as tempo
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agenda.mensagem import ModeloInvalido, de_agendamento, renderizar
from app.agenda.models import (
    Agendamento,
    Lembrete,
    SituacaoLembrete,
    TipoLembrete,
)
from app.agenda.service import (
    SITUACOES_VIVAS,
    anotar_conexao,
    configuracao_de,
    modelo_da_vespera,
)
from app.agenda.whatsapp import EstadoDaConexao, Provedor
from app.auth.auditoria import registrar
from app.auth.service import identidade_da_clinica
from app.pacientes.service import contatos_de
from app.pacientes.telefone import numero_para_whatsapp

# Um lembrete so sai se ainda faltar isto para a consulta. Menos que isso, a
# paciente ja saiu de casa ou ja perdeu — e lembrete que chega em cima da hora
# nao evita falta nenhuma.
HORAS_MINIMAS_DE_ANTECEDENCIA = 6

# Ritmo humano entre um envio e o outro. A deteccao do WhatsApp pesa padrao
# temporal robotico, e mensagem identica no mesmo segundo e a assinatura disso.
PAUSA_MINIMA_S, PAUSA_MAXIMA_S = 20, 90


@dataclass
class Resumo:
    """O que aconteceu numa execucao. Sem nome de paciente: este numero vai para
    a resposta de um endpoint que um servico de terceiro chama."""

    reservados: int = 0
    enviados: int = 0
    descartados: int = 0
    expirados: int = 0
    falhados: int = 0
    cancelados: int = 0
    # Reservados que ainda nao venceram. Numa batida qualquer este e o numero
    # grande: a agenda inteira de amanha esta esperando a hora dela.
    esperando: int = 0


def _quando(agendamento: Agendamento) -> datetime:
    """O momento da consulta no relogio da parede da clinica."""
    return datetime.combine(agendamento.dia, agendamento.inicio)


def parede(momento: datetime) -> datetime:
    """Um instante vindo do banco, na hora do relogio da parede da clinica.

    O Postgres devolve `timestamptz` no fuso da SESSAO dele, que no container e
    UTC; o consultorio vive em UTC-3. Descartar o fuso sem converter empurra o
    horario tres horas para a frente, e o estrago e silencioso: um horario
    marcado com folga passa a parecer marcado DEPOIS do vencimento, e a paciente
    simplesmente nao recebe — sem excecao, sem log, sem tela vermelha.

    Momento ingenuo ja e hora de parede e volta como veio.
    """
    if momento.tzinfo is None:
        return momento
    return momento.astimezone().replace(tzinfo=None)


def _vencimento(agendamento: Agendamento, horas_antes: int) -> datetime:
    """Quando ESTE lembrete tem de sair: a hora da consulta, menos a antecedencia.

    E sempre recalculado do agendamento vivo, nunca lido do que ficou gravado —
    `remarcar` muda dia e hora na mesma linha (`agenda/service.py`), entao o
    `agendado_para` de um lembrete ja reservado envelhece calado. Confiar nele
    manda a mensagem na hora do horario velho.
    """
    return _quando(agendamento) - timedelta(hours=horas_antes)


def _pausa_humana() -> None:
    tempo.sleep(random.uniform(PAUSA_MINIMA_S, PAUSA_MAXIMA_S))


def reservar(sessao: Session, *, clinica_id: int, agora: datetime) -> Resumo:
    """Fase 1: decide quem recebe amanha e grava a decisao. Nenhuma rede.

    Quem NAO vai receber tambem vira linha, `DESCARTADO` com motivo. Isso e o que
    permite a tela dizer "8 pacientes de amanha nao vao receber: 6 sem permissao,
    2 sem numero" — informacao sobre a qual a clinica consegue agir hoje, com a
    paciente na cadeira. Lembrete que simplesmente nao e criado nao aparece em
    tela nenhuma.
    """
    resumo = Resumo()
    configuracao = configuracao_de(sessao, clinica_id=clinica_id)
    if not configuracao.lembrete_ativo:
        return resumo

    limite = agora + timedelta(hours=configuracao.lembrete_horas_antes)
    candidatos = [
        agendamento
        for agendamento in sessao.scalars(
            select(Agendamento)
            .where(
                Agendamento.clinica_id == clinica_id,
                Agendamento.dia.between(agora.date(), limite.date()),
                Agendamento.situacao.in_(SITUACOES_VIVAS),
                Agendamento.excluido_em.is_(None),
            )
            .order_by(Agendamento.dia, Agendamento.inicio, Agendamento.id)
        ).all()
        if agora < _quando(agendamento) <= limite
    ]
    if not candidatos:
        return resumo

    contatos = contatos_de(
        sessao,
        clinica_id=clinica_id,
        paciente_ids={a.paciente_id for a in candidatos if a.paciente_id},
    )
    ja_reservados = _quantos_de_pe(sessao, [a.id for a in candidatos])

    for agendamento in candidatos:
        vence = _vencimento(agendamento, configuracao.lembrete_horas_antes)
        numero, motivo = _destino(agendamento, contatos)
        if motivo is None and parede(agendamento.criado_em) > vence:
            # Marcado depois da propria hora de avisar: nao manda. A comparacao e
            # com quando o HORARIO foi marcado, e nao com o relogio de agora, de
            # proposito — se fosse com o relogio, uma queda do app de duas horas
            # descartaria quem marcou com folga, e a tela diria "marcou em cima
            # da hora", que seria mentira sobre a paciente.
            motivo = "marcado_em_cima"
        if motivo is None and ja_reservados >= configuracao.lembrete_teto_diario:
            motivo = "teto_diario"
        criado = _criar(
            sessao,
            agendamento=agendamento,
            numero=numero,
            motivo=motivo,
            quando=vence,
        )
        if criado is None:
            continue  # ja existia: a segunda execucao nao duplica
        if motivo is None:
            ja_reservados += 1
            resumo.reservados += 1
        else:
            resumo.descartados += 1
    return resumo


def _quantos_de_pe(sessao: Session, agendamento_ids: list[int]) -> int:
    """Quantos lembretes desta mesma janela ja estao de pe para sair.

    Conta pelos agendamentos da janela, e nao por data de criacao: e a pergunta
    exata do teto ("quantas mensagens este disparo vai mandar") e nao depende de
    fuso nenhum. Descartado e expirado nao ocupam cota — nao viram mensagem.
    """
    if not agendamento_ids:
        return 0
    return len(
        sessao.scalars(
            select(Lembrete.id).where(
                Lembrete.agendamento_id.in_(agendamento_ids),
                Lembrete.situacao.in_(
                    (
                        SituacaoLembrete.PENDENTE,
                        SituacaoLembrete.ENVIANDO,
                        SituacaoLembrete.ENVIADO,
                    )
                ),
            )
        ).all()
    )


def _destino(agendamento: Agendamento, contatos: dict) -> tuple[str | None, str | None]:
    """Para onde mandar, ou por que nao mandar.

    A diferenca entre paciente da base e horario avulso nao e tecnica, e de
    consentimento: o telefone avulso foi ditado agora, ao telefone, para marcar
    ESTA consulta; os 5.559 migrados foram coletados desde 1996 sem registro de
    autorizacao nenhum.
    """
    if agendamento.paciente_id is None:
        if not agendamento.avisar_avulso:
            return None, "avulso_recusou"
        numero = numero_para_whatsapp(agendamento.telefone_avulso)
        return (numero, None) if numero else (None, "sem_numero")

    contato = contatos.get(agendamento.paciente_id)
    if contato is None or contato.aceita_whatsapp is not True:
        return None, "sem_permissao"
    numero = numero_para_whatsapp(contato.telefone)
    return (numero, None) if numero else (None, "sem_numero")


def _criar(
    sessao: Session,
    *,
    agendamento: Agendamento,
    numero: str | None,
    motivo: str | None,
    quando: datetime,
) -> Lembrete | None:
    """Insere a linha, ou devolve `None` se ja existia.

    `IntegrityError` aqui e caminho normal, nao erro: e a `UNIQUE` fazendo o
    trabalho dela quando duas execucoes se cruzam. O savepoint existe para que a
    recusa nao derrube a sessao inteira e leve os outros lembretes junto.
    """
    lembrete = Lembrete(
        clinica_id=agendamento.clinica_id,
        agendamento_id=agendamento.id,
        tipo=TipoLembrete.VESPERA,
        numero=numero,
        situacao=(
            SituacaoLembrete.PENDENTE if motivo is None else SituacaoLembrete.DESCARTADO
        ),
        motivo=motivo,
        agendado_para=quando.astimezone(),
    )
    try:
        with sessao.begin_nested():
            sessao.add(lembrete)
            sessao.flush()
    except IntegrityError:
        return None
    return lembrete


def despachar(
    sessao: Session,
    *,
    clinica_id: int,
    agora: datetime,
    provedor: Provedor,
    pausar=None,
) -> Resumo:
    """Fase 2: manda uma mensagem por vez.

    `ENVIANDO` e gravado e COMMITADO antes de tocar na rede — e o que faz duas
    execucoes concorrentes nao mandarem a mesma mensagem. E `ENVIANDO` que sobrou
    de uma execucao morta nunca e retomado: na duvida sobre se saiu, nao manda.
    """
    pausar = _pausa_humana if pausar is None else pausar
    resumo = Resumo()
    configuracao = configuracao_de(sessao, clinica_id=clinica_id)
    if not configuracao.lembrete_ativo:
        return resumo

    modelo = modelo_da_vespera(sessao, clinica_id=clinica_id)
    pendentes = sessao.scalars(
        select(Lembrete)
        .where(
            Lembrete.clinica_id == clinica_id,
            Lembrete.situacao == SituacaoLembrete.PENDENTE,
            Lembrete.excluido_em.is_(None),
        )
        .order_by(Lembrete.agendado_para, Lembrete.id)
    ).all()

    # A conexao e perguntada UMA vez por execucao, e so quando a primeira
    # mensagem esta prestes a sair. Uma vez porque sao 96 batidas por dia e a
    # maioria nao tem nada para mandar — perguntar sempre seria bater na Evolution
    # a toa; so na hora porque `pendentes` inclui quem ainda nao venceu, e a
    # conexao de agora nao diz nada sobre a de daqui a seis horas.
    conexao: list[EstadoDaConexao] = []

    def conectado() -> bool:
        if not conexao:
            conexao.append(provedor.estado())
            # O que se descobriu aqui e o que faz a AGENDA poder mostrar a faixa
            # "o WhatsApp desconectou" sem falar com a rede. Quem carrega a agenda
            # nao devia esperar por uma Evolution travada para ver os horarios.
            anotar_conexao(
                sessao, clinica_id=clinica_id, estado=conexao[0].value
            )
            sessao.commit()
        return conexao[0] is EstadoDaConexao.CONECTADO

    primeiro = True
    for lembrete in pendentes:
        agendamento = sessao.get(Agendamento, lembrete.agendamento_id)
        # Reconfere na hora de mandar: desmarcou as 17h, nao recebe as 18h.
        if (
            agendamento is None
            or agendamento.excluido_em is not None
            or agendamento.situacao not in SITUACOES_VIVAS
        ):
            _fechar(sessao, lembrete, SituacaoLembrete.CANCELADO, "desmarcado")
            resumo.cancelados += 1
            continue

        # Cada lembrete tem a SUA hora, e ela e recalculada do horario vivo. Quem
        # ainda nao venceu fica na fila esperando a batida dele: consulta das 21h
        # sai as 21h da vespera, nao junto com a das 8h.
        vence = _vencimento(agendamento, configuracao.lembrete_horas_antes)
        if agora < vence:
            if parede(lembrete.agendado_para) != vence:
                # Remarcado para depois. A fila se conserta aqui, e por isso
                # `remarcar()` nao precisa saber que lembrete existe.
                lembrete.agendado_para = vence.astimezone()
                sessao.commit()
            resumo.esperando += 1
            continue

        faltam = _quando(agendamento) - agora
        if faltam < timedelta(hours=HORAS_MINIMAS_DE_ANTECEDENCIA):
            _fechar(sessao, lembrete, SituacaoLembrete.EXPIRADO, "tarde_demais")
            resumo.expirados += 1
            continue

        try:
            texto = _texto(
                sessao,
                clinica_id=clinica_id,
                configuracao=configuracao,
                modelo=modelo,
                agendamento=agendamento,
                agora=agora,
            )
        except ModeloInvalido:
            _fechar(sessao, lembrete, SituacaoLembrete.FALHOU, "modelo_invalido")
            lembrete.tentativas += 1
            sessao.commit()
            resumo.falhados += 1
            continue

        if not conectado():
            # Antes de `_reservar_para_envio`, de proposito: `ENVIANDO` significa
            # "nao sei se saiu" e nunca e retomado sozinho. Com o socket caido eu
            # SEI que nao saiu, e deixar a linha travada nesse estado trocaria uma
            # certeza por uma duvida que so uma pessoa consegue desfazer.
            _fechar(sessao, lembrete, SituacaoLembrete.FALHOU, "desconectado")
            lembrete.tentativas += 1
            sessao.commit()
            resumo.falhados += 1
            continue

        if not _reservar_para_envio(sessao, lembrete):
            continue  # outra execucao pegou este

        if not primeiro:
            pausar()
        primeiro = False

        envio = provedor.enviar(numero=lembrete.numero, texto=texto)
        if envio.ok:
            lembrete.situacao = SituacaoLembrete.ENVIADO
            lembrete.texto = texto
            lembrete.modelo_id = modelo.id
            lembrete.enviado_em = datetime.now(UTC)
            lembrete.id_externo = envio.id_externo
            lembrete.motivo = None
            resumo.enviados += 1
            registrar(
                sessao,
                clinica_id=clinica_id,
                usuario_id=None,
                acao="ENVIAR",
                entidade="lembrete",
                entidade_id=lembrete.id,
                depois={"numero": lembrete.numero, "agendamento_id": agendamento.id},
            )
        else:
            lembrete.situacao = SituacaoLembrete.FALHOU
            lembrete.motivo = envio.erro
            resumo.falhados += 1
        lembrete.tentativas += 1
        lembrete.provedor = type(provedor).__name__
        sessao.commit()

    return resumo


def rodar(
    sessao: Session,
    *,
    clinica_id: int,
    agora: datetime,
    provedor: Provedor,
    pausar=None,
) -> Resumo:
    """Uma passada inteira: reserva e despacha.

    E o que o relogio faz a cada 15 minutos, o que o botao "Enviar agora" faz e o
    que o endpoint do gatilho manual faz. Uma funcao so, de proposito: se os tres
    caminhos fossem tres copias, um deles acabaria divergindo, e o modo que
    divergisse seria justamente o de emergencia — o que so roda no dia ruim.
    """
    reserva = reservar(sessao, clinica_id=clinica_id, agora=agora)
    sessao.commit()
    envio = despachar(
        sessao, clinica_id=clinica_id, agora=agora, provedor=provedor, pausar=pausar
    )
    return Resumo(
        reservados=reserva.reservados,
        descartados=reserva.descartados,
        enviados=envio.enviados,
        expirados=envio.expirados,
        falhados=envio.falhados,
        cancelados=envio.cancelados,
        esperando=envio.esperando,
    )


def _texto(
    sessao: Session,
    *,
    clinica_id: int,
    configuracao,
    modelo,
    agendamento: Agendamento,
    agora: datetime,
) -> str:
    """O texto final. Passa OBRIGATORIAMENTE pelo `ContextoDaMensagem`, que e a
    unica porta por onde dado chega numa mensagem."""
    if agendamento.paciente_id is not None:
        contato = contatos_de(
            sessao, clinica_id=clinica_id, paciente_ids=[agendamento.paciente_id]
        ).get(agendamento.paciente_id)
        nome = contato.nome if contato else ""
    else:
        nome = agendamento.nome_avulso or ""

    identidade = identidade_da_clinica(sessao, clinica_id=clinica_id)
    contexto = de_agendamento(
        nome=nome,
        dia=agendamento.dia,
        inicio=agendamento.inicio,
        agora=agora,
        clinica=identidade.clinica,
        dentista=identidade.dentista,
        endereco=configuracao.endereco or "",
        telefone_clinica=configuracao.telefone_clinica or "",
    )
    return renderizar(modelo.texto, contexto)


def _reservar_para_envio(sessao: Session, lembrete: Lembrete) -> bool:
    """Marca `ENVIANDO` e commita ANTES da rede. Quem ganhar o UPDATE manda."""
    ganhou = sessao.execute(
        update(Lembrete)
        .where(Lembrete.id == lembrete.id, Lembrete.situacao == SituacaoLembrete.PENDENTE)
        .values(situacao=SituacaoLembrete.ENVIANDO)
        .returning(Lembrete.id)
    ).scalar_one_or_none()
    sessao.commit()
    if ganhou is None:
        return False
    sessao.refresh(lembrete)
    return True


def _fechar(
    sessao: Session, lembrete: Lembrete, situacao: SituacaoLembrete, motivo: str
) -> None:
    lembrete.situacao = situacao
    lembrete.motivo = motivo
    sessao.commit()


@dataclass(frozen=True)
class LinhaDaPrevisao:
    """Uma pessoa do proximo disparo, e o que vai acontecer com ela."""

    nome: str
    paciente_id: int | None
    hora: str
    # A que horas a mensagem DELA sai. Nao existe mais uma hora do disparo para
    # a tela anunciar: existe uma por paciente, e e esta.
    sai_as: str
    recebe: bool
    motivo: str | None


def previsao(sessao: Session, *, clinica_id: int, agora: datetime) -> list[LinhaDaPrevisao]:
    """Quem vai e quem NAO vai receber no proximo disparo, sem gravar nada.

    A parte que importa e a segunda: "3 sem permissao de WhatsApp, 1 sem numero"
    e a unica informacao da tela sobre a qual ela consegue agir HOJE, com a
    paciente na cadeira. Por isso a lista traz nome e link para a ficha — aqui e
    a tela dela, nao uma mensagem que sai para fora.
    """
    configuracao = configuracao_de(sessao, clinica_id=clinica_id)
    limite = agora + timedelta(hours=configuracao.lembrete_horas_antes)
    agendamentos = [
        agendamento
        for agendamento in sessao.scalars(
            select(Agendamento)
            .where(
                Agendamento.clinica_id == clinica_id,
                Agendamento.dia.between(agora.date(), limite.date()),
                Agendamento.situacao.in_(SITUACOES_VIVAS),
                Agendamento.excluido_em.is_(None),
            )
            .order_by(Agendamento.dia, Agendamento.inicio, Agendamento.id)
        ).all()
        if agora < _quando(agendamento) <= limite
    ]
    contatos = contatos_de(
        sessao,
        clinica_id=clinica_id,
        paciente_ids={a.paciente_id for a in agendamentos if a.paciente_id},
    )

    linhas = []
    for agendamento in agendamentos:
        vence = _vencimento(agendamento, configuracao.lembrete_horas_antes)
        _, motivo = _destino(agendamento, contatos)
        if motivo is None and parede(agendamento.criado_em) > vence:
            motivo = "marcado_em_cima"
        contato = contatos.get(agendamento.paciente_id)
        linhas.append(
            LinhaDaPrevisao(
                nome=contato.nome if contato else (agendamento.nome_avulso or ""),
                paciente_id=agendamento.paciente_id,
                hora=agendamento.inicio.strftime("%H:%M"),
                sai_as=vence.strftime("%d/%m às %H:%M"),
                recebe=motivo is None,
                motivo=motivo,
            )
        )
    return linhas


def ultimos_envios(sessao: Session, *, clinica_id: int, limite: int = 50) -> list[Lembrete]:
    """Os ultimos lembretes, mais novos primeiro. E o extrato do que saiu."""
    return list(
        sessao.scalars(
            select(Lembrete)
            .where(Lembrete.clinica_id == clinica_id)
            .order_by(Lembrete.criado_em.desc(), Lembrete.id.desc())
            .limit(limite)
        ).all()
    )


def ultimo_disparo(sessao: Session, *, clinica_id: int) -> datetime | None:
    """Quando saiu a ultima mensagem. So informacao, na tela.

    Nao e mais alarme: o "faixa vermelha depois de 48h" existia para descobrir
    que um cron de terceiro tinha morrido calado. O relogio mora dentro do app
    agora, entao "o relogio parou" e a mesma coisa que "o app caiu", e disso o
    healthcheck cuida. Como alarme, isto ficaria vermelho todo feriado
    prolongado — e alarme que grita a toa se aprende a ignorar.
    """
    return sessao.scalars(
        select(Lembrete.enviado_em)
        .where(
            Lembrete.clinica_id == clinica_id,
            Lembrete.enviado_em.is_not(None),
        )
        .order_by(Lembrete.enviado_em.desc())
        .limit(1)
    ).one_or_none()
