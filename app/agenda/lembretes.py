"""Reservar e despachar o lembrete da vespera.

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
nenhuma funcao daqui chama `datetime.now()` por dentro.
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
    configuracao_de,
    modelo_da_vespera,
)
from app.agenda.whatsapp import Provedor
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


def _quando(agendamento: Agendamento) -> datetime:
    """O momento da consulta no relogio da parede da clinica."""
    return datetime.combine(agendamento.dia, agendamento.inicio)


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
        numero, motivo = _destino(agendamento, contatos)
        if motivo is None and ja_reservados >= configuracao.lembrete_teto_diario:
            motivo = "teto_diario"
        criado = _criar(
            sessao,
            agendamento=agendamento,
            numero=numero,
            motivo=motivo,
            quando=_quando(agendamento)
            - timedelta(hours=configuracao.lembrete_horas_antes),
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
