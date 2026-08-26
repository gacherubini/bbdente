from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.tipos import Escopo, Regiao

# Os tipos enum sao criados uma vez pela migration; as colunas apenas os referenciam.
ESCOPO_PG = Enum(
    Escopo, name="escopo", create_type=False, values_callable=lambda e: [m.value for m in e]
)
REGIAO_PG = Enum(
    Regiao, name="regiao", create_type=False, values_callable=lambda e: [m.value for m in e]
)


class Categoria(Base):
    __tablename__ = "categoria"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(4))
    nome: Mapped[str] = mapped_column(String(80))
    ordem: Mapped[int] = mapped_column(default=0)


class Convenio(Base):
    __tablename__ = "convenio"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(4))
    nome: Mapped[str] = mapped_column(String(80))


class Procedimento(Base):
    __tablename__ = "procedimento"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(8), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Calculados a partir do historico na migracao: o palpite inicial da tela e o
    # habito real da dentista, nao uma opiniao de quem programou.
    escopo_sugerido: Mapped[Escopo] = mapped_column(ESCOPO_PG, default=Escopo.DENTE)
    regioes_sugeridas: Mapped[list[Regiao]] = mapped_column(
        ARRAY(REGIAO_PG), default=list, server_default="{}"
    )
    duracao_min: Mapped[int | None] = mapped_column()


class Preco(Base):
    __tablename__ = "preco"

    id: Mapped[int] = mapped_column(primary_key=True)
    procedimento_id: Mapped[int] = mapped_column(ForeignKey("procedimento.id"), index=True)
    convenio_id: Mapped[int] = mapped_column(ForeignKey("convenio.id"), index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    vigente_desde: Mapped[date] = mapped_column(Date)
