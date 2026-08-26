from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base
from app.shared.tipos import Escopo, Regiao, StatusLancamento, TipoCondicao

ESCOPO_PG = Enum(
    Escopo, name="escopo", create_type=False, values_callable=lambda e: [m.value for m in e]
)
REGIAO_PG = Enum(
    Regiao, name="regiao", create_type=False, values_callable=lambda e: [m.value for m in e]
)
STATUS_PG = Enum(
    StatusLancamento,
    name="status_lancamento",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
TIPO_CONDICAO_PG = Enum(
    TipoCondicao,
    name="tipo_condicao",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Odontograma(Base):
    """Um paciente pode ter mais de um odontograma ao longo dos anos (NUMODO no
    Dentalis: 43.887 lancamentos no numero 1, o resto espalhado ate o 5)."""

    __tablename__ = "odontograma"
    __table_args__ = (UniqueConstraint("paciente_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    numero: Mapped[int] = mapped_column(SmallInteger, default=1)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Lancamento(Base):
    """O que a dentista faz e cobra. Vermelho (planejado) ou verde (realizado)."""

    __tablename__ = "lancamento"
    __table_args__ = (
        CheckConstraint(
            "(escopo = 'BOCA') = (dente IS NULL)",
            name="ck_lancamento_dente_conforme_escopo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    odontograma_id: Mapped[int] = mapped_column(ForeignKey("odontograma.id"), index=True)

    dente: Mapped[int | None] = mapped_column(SmallInteger)  # FDI; NULL quando escopo=BOCA
    escopo: Mapped[Escopo] = mapped_column(ESCOPO_PG)
    procedimento_id: Mapped[int] = mapped_column(ForeignKey("procedimento.id"), index=True)
    status: Mapped[StatusLancamento] = mapped_column(STATUS_PG)

    data_planejada: Mapped[date | None] = mapped_column(Date, index=True)
    data_realizada: Mapped[date | None] = mapped_column(Date, index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    observacao: Mapped[str | None] = mapped_column(Text)

    codigo_legado: Mapped[str | None] = mapped_column(String(20), index=True)
    revisar_motivo: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    regioes: Mapped[list["LancamentoRegiao"]] = relationship(
        back_populates="lancamento", cascade="all"
    )


class LancamentoRegiao(Base):
    """N:N livre. Nao ha validacao de compatibilidade entre tratamento e regiao: o
    historico real mostra o mesmo tratamento em escopos diferentes, e travar
    rejeitaria dados verdadeiros."""

    __tablename__ = "lancamento_regiao"

    lancamento_id: Mapped[int] = mapped_column(ForeignKey("lancamento.id"), primary_key=True)
    regiao: Mapped[Regiao] = mapped_column(REGIAO_PG, primary_key=True)

    lancamento: Mapped[Lancamento] = relationship(back_populates="regioes")


class Condicao(Base):
    """A camada azul: estado pre-existente do dente. Sem preco, sem status."""

    __tablename__ = "condicao"

    id: Mapped[int] = mapped_column(primary_key=True)
    odontograma_id: Mapped[int] = mapped_column(ForeignKey("odontograma.id"), index=True)
    dente: Mapped[int] = mapped_column(SmallInteger)
    tipo: Mapped[TipoCondicao] = mapped_column(TIPO_CONDICAO_PG)
    regioes: Mapped[list[Regiao]] = mapped_column(
        ARRAY(REGIAO_PG), default=list, server_default="{}"
    )
    # Os 309 codigos de icone do Dentalis, preservados ate a Dra. Katia traduzi-los.
    icone_legado: Mapped[str | None] = mapped_column(String(20), index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PerguntaAnamnese(Base):
    __tablename__ = "pergunta_anamnese"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(4))
    texto: Mapped[str] = mapped_column(Text)
    tipo_resposta: Mapped[int] = mapped_column(SmallInteger, default=1)
    ordem: Mapped[int] = mapped_column(default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class RespostaAnamnese(Base):
    __tablename__ = "resposta_anamnese"
    __table_args__ = (UniqueConstraint("paciente_id", "pergunta_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    pergunta_id: Mapped[int] = mapped_column(ForeignKey("pergunta_anamnese.id"))
    resposta: Mapped[str] = mapped_column(Text)
    respondido_em: Mapped[date | None] = mapped_column(Date)


class ObservacaoClinica(Base):
    __tablename__ = "observacao_clinica"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    texto: Mapped[str] = mapped_column(Text)
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
