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
