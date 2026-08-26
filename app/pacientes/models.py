from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base


class Paciente(Base):
    __tablename__ = "paciente"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo_legado: Mapped[str | None] = mapped_column(String(10), index=True)

    nome: Mapped[str] = mapped_column(String(160), index=True)
    nascimento: Mapped[date | None] = mapped_column(Date)
    cpf: Mapped[str | None] = mapped_column(String(14))
    ci: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))
    profissao: Mapped[str | None] = mapped_column(String(60))
    estado_civil: Mapped[str | None] = mapped_column(String(30))
    indicacao: Mapped[str | None] = mapped_column(String(60))
    pai: Mapped[str | None] = mapped_column(String(120))
    mae: Mapped[str | None] = mapped_column(String(120))
    # Texto livre: o que a recepcao anota nao cabe em campo estruturado.
    observacao: Mapped[str | None] = mapped_column(Text)

    # FK declarada por nome: pacientes NAO importa o modelo Convenio. Para exibir o
    # nome do convenio, chame catalogo.service.convenio(id).
    convenio_id: Mapped[int | None] = mapped_column(ForeignKey("convenio.id"))

    cadastrado_em: Mapped[date | None] = mapped_column(Date)
    ultimo_atendimento: Mapped[date | None] = mapped_column(Date, index=True)

    # Dado suspeito e marcado, nunca corrigido no chute nem escondido.
    revisar_motivo: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # O filtro do `excluido_em` mora aqui para que todo leitor de
    # `paciente.telefones` — ficha, busca, PDF — veja so os numeros vivos, sem
    # precisar lembrar da regra em cada consulta.
    telefones: Mapped[list["PacienteTelefone"]] = relationship(
        back_populates="paciente",
        cascade="all",
        primaryjoin=(
            "and_(Paciente.id == PacienteTelefone.paciente_id,"
            " PacienteTelefone.excluido_em.is_(None))"
        ),
    )
    enderecos: Mapped[list["PacienteEndereco"]] = relationship(
        back_populates="paciente", cascade="all"
    )


class PacienteTelefone(Base):
    __tablename__ = "paciente_telefone"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    numero: Mapped[str] = mapped_column(String(24))
    # O campo cru do Dentalis, guardado caso a separacao em varios numeros erre.
    numero_original: Mapped[str | None] = mapped_column(String(60))
    principal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Trocar o telefone nao apaga o antigo: ele sai da ficha e fica no banco.
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    paciente: Mapped[Paciente] = relationship(back_populates="telefones")


class PacienteEndereco(Base):
    __tablename__ = "paciente_endereco"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(12))  # RESIDENCIAL | COMERCIAL
    logradouro: Mapped[str | None] = mapped_column(String(120))
    bairro: Mapped[str | None] = mapped_column(String(60))
    cidade: Mapped[str | None] = mapped_column(String(60))
    uf: Mapped[str | None] = mapped_column(String(2))
    cep: Mapped[str | None] = mapped_column(String(9))

    paciente: Mapped[Paciente] = relationship(back_populates="enderecos")
