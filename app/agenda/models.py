"""Tabela da agenda.

Uma tabela so: `agendamento`. O que ela nao guarda esta tao decidido quanto o
que ela guarda — ver o plano da agenda, secao 3.3.
"""

from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base

DURACAO_PADRAO_MIN = 30
DURACAO_MINIMA_MIN = 5
DURACAO_MAXIMA_MIN = 600


class SituacaoAgendamento(StrEnum):
    """O que nao da para derivar de outra tabela.

    `ATENDIDO` nao esta aqui de proposito: quem foi atendido se sabe pelo
    lancamento do dia, e duas verdades sobre o mesmo fato divergem na primeira
    vez que alguem lancar sem passar pela agenda.
    """

    MARCADO = "MARCADO"
    CONFIRMADO = "CONFIRMADO"
    FALTOU = "FALTOU"
    DESMARCADO = "DESMARCADO"


SITUACAO_PG = Enum(
    SituacaoAgendamento,
    name="situacao_agendamento",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Agendamento(Base):
    """Um horario. Da paciente cadastrada ou de um telefonema avulso."""

    __tablename__ = "agendamento"
    __table_args__ = (
        # A linha precisa responder "quem vem". Sem paciente e sem nome, nao
        # responde — e a regra e do banco, nao de um `if` que alguem esquece.
        CheckConstraint(
            "paciente_id IS NOT NULL OR coalesce(nome_avulso, '') <> ''",
            name="ck_agendamento_tem_dono",
        ),
        CheckConstraint(
            f"duracao_min BETWEEN {DURACAO_MINIMA_MIN} AND {DURACAO_MAXIMA_MIN}",
            name="ck_agendamento_duracao_plausivel",
        ),
        # Os dois eixos de toda consulta: a grade de um periodo, e o historico
        # de horarios de uma paciente.
        Index("ix_agendamento_clinica_dia", "clinica_id", "dia"),
        Index("ix_agendamento_paciente_dia", "paciente_id", "dia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)

    # FK declarada por nome: a agenda NAO importa o modelo Paciente. Para nome e
    # telefone, chame pacientes.service.
    paciente_id: Mapped[int | None] = mapped_column(ForeignKey("paciente.id"), index=True)
    # Horario avulso: o telefonema anotado antes de existir cadastro. E etapa,
    # nunca estado permanente — concluir o atendimento cria a paciente e vincula.
    nome_avulso: Mapped[str | None] = mapped_column(String(160))
    telefone_avulso: Mapped[str | None] = mapped_column(String(24))

    # `dia` e `inicio` separados, no relogio da clinica: a grade e desenhada por
    # dia e hora, e timestamp com fuso obrigaria a converter em toda celula.
    dia: Mapped[date] = mapped_column(Date)
    inicio: Mapped[time] = mapped_column(Time)
    duracao_min: Mapped[int] = mapped_column(
        SmallInteger, default=DURACAO_PADRAO_MIN, server_default=str(DURACAO_PADRAO_MIN)
    )

    situacao: Mapped[SituacaoAgendamento] = mapped_column(
        SITUACAO_PG,
        default=SituacaoAgendamento.MARCADO,
        server_default=SituacaoAgendamento.MARCADO.value,
    )
    observacao: Mapped[str | None] = mapped_column(Text)
    # So significa algo quando `paciente_id` e nulo. Nasce ligado porque o
    # telefone avulso foi ditado agora, ao telefone, para marcar ESTA consulta —
    # avisar dela e a finalidade para a qual o numero acabou de ser dado. Quem
    # disser "nao me manda mensagem" desliga aqui, no mesmo formulario.
    avisar_avulso: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Exclusao logica e para engano — marcou no dia errado, duplicou. Desmarcar
    # e outra coisa, e mora em `situacao`.
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def fim(self) -> time:
        """`inicio + duracao_min`. Derivado, nunca guardado — coluna seria a
        mesma verdade em dois lugares.

        Nao vira o dia: consultorio nao atende de madrugada, e um fim que dobra
        para 01:00 poria o cartao no topo do dia, antes do proprio comeco.
        """
        minutos = self.inicio.hour * 60 + self.inicio.minute + self.duracao_min
        if minutos >= 24 * 60:
            return time(23, 59)
        return time(minutos // 60, minutos % 60)


class TipoLembrete(StrEnum):
    """So um, e de proposito: modelo que nada dispara e peso morto.

    O de confirmacao na marcacao e o proximo, e o encanamento ja o comporta sem
    schema novo — e por isso que `tipo` existe com um valor so.
    """

    VESPERA = "VESPERA"


class SituacaoLembrete(StrEnum):
    """O caminho de um lembrete, incluindo os becos sem saida.

    `DESCARTADO` e `EXPIRADO` existem porque **saber quem NAO vai receber e a
    informacao sobre a qual a clinica consegue agir hoje**, com a paciente na
    cadeira. Um lembrete que simplesmente nao e criado nao aparece em tela
    nenhuma.
    """

    PENDENTE = "PENDENTE"
    ENVIANDO = "ENVIANDO"
    ENVIADO = "ENVIADO"
    FALHOU = "FALHOU"
    DESCARTADO = "DESCARTADO"
    EXPIRADO = "EXPIRADO"
    CANCELADO = "CANCELADO"


TIPO_LEMBRETE_PG = Enum(
    TipoLembrete,
    name="tipo_lembrete",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
SITUACAO_LEMBRETE_PG = Enum(
    SituacaoLembrete,
    name="situacao_lembrete",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Lembrete(Base):
    """Uma mensagem que vai (ou nao) sair para um horario."""

    __tablename__ = "lembrete"
    __table_args__ = (
        # A IDEMPOTENCIA MORA AQUI. Nao e um `if`, nao e lock, nao e disciplina:
        # e o banco recusando a segunda linha. Vale se o cron disparar duas
        # vezes, se houver duas maquinas durante um deploy, e se alguem clicar em
        # "enviar agora" enquanto o cron roda.
        UniqueConstraint(
            "agendamento_id", "tipo", name="uq_lembrete_um_por_agendamento"
        ),
        Index("ix_lembrete_fila", "clinica_id", "situacao", "agendado_para"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    agendamento_id: Mapped[int] = mapped_column(
        ForeignKey("agendamento.id"), index=True
    )
    tipo: Mapped[TipoLembrete] = mapped_column(TIPO_LEMBRETE_PG)

    # Para onde foi e o que saiu, congelados no envio. Se ela corrigir o telefone
    # depois, o registro continua dizendo para onde foi de fato — mesma filosofia
    # do prontuario: guarda o que aconteceu, nao o estado de agora.
    numero: Mapped[str | None] = mapped_column(String(24))
    texto: Mapped[str | None] = mapped_column(Text)
    modelo_id: Mapped[int | None] = mapped_column(ForeignKey("modelo_mensagem.id"))

    situacao: Mapped[SituacaoLembrete] = mapped_column(
        SITUACAO_LEMBRETE_PG,
        default=SituacaoLembrete.PENDENTE,
        server_default=SituacaoLembrete.PENDENTE.value,
    )
    # Por que nao saiu. E o que a tela mostra para ela poder corrigir hoje.
    motivo: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )

    provedor: Mapped[str | None] = mapped_column(String(20))
    id_externo: Mapped[str | None] = mapped_column(String(80))

    agendado_para: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModeloMensagem(Base):
    """O texto que ela edita. Tabela e nao constante porque o requisito e que
    **ela** escreva — e o texto dela vai ser melhor que o nosso."""

    __tablename__ = "modelo_mensagem"
    __table_args__ = (
        UniqueConstraint("clinica_id", "codigo", name="uq_modelo_por_clinica"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(30))
    texto: Mapped[str] = mapped_column(Text)
    atualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConfiguracaoClinica(Base):
    """Uma linha por clinica, com colunas tipadas — nao chave/valor.

    Neste repositorio o `tests/test_schema.py` afirma colunas, e o schema e a
    documentacao. Chave/valor generico e `varchar` para tudo e invisivel ao teste.
    """

    __tablename__ = "configuracao_clinica"

    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), primary_key=True)

    # A CHAVE GERAL. Nasce desligada: deploy que ja sai mandando mensagem para
    # paciente e a definicao de acidente.
    lembrete_ativo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    lembrete_hora: Mapped[time] = mapped_column(Time, server_default="18:00")
    lembrete_horas_antes: Mapped[int] = mapped_column(
        SmallInteger, default=24, server_default="24"
    )
    # Teto de volume: ritmo humano e a mitigacao que a via nao oficial exige.
    lembrete_teto_diario: Mapped[int] = mapped_column(
        SmallInteger, default=20, server_default="20"
    )
    whatsapp_provedor: Mapped[str | None] = mapped_column(String(20))

    # Viram {endereco} e {telefone_clinica} na mensagem.
    endereco: Mapped[str | None] = mapped_column(String(200))
    telefone_clinica: Mapped[str | None] = mapped_column(String(24))

    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
