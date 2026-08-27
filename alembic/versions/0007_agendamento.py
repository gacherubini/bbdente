"""agendamento

Revision ID: 0007
Revises: 0006

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A agenda: quem vem, e quando.

    O enum e criado aqui, na mao, e nao pelo autogenerate — e o padrao do
    `0001_schema_inicial.py`, e e o que faz o downgrade conseguir limpar.
    """
    bind = op.get_bind()
    postgresql.ENUM(
        "MARCADO", "CONFIRMADO", "FALTOU", "DESMARCADO", name="situacao_agendamento"
    ).create(bind, checkfirst=True)

    op.create_table(
        "agendamento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinica_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=True),
        sa.Column("nome_avulso", sa.String(length=160), nullable=True),
        sa.Column("telefone_avulso", sa.String(length=24), nullable=True),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("inicio", sa.Time(), nullable=False),
        sa.Column("duracao_min", sa.SmallInteger(), server_default="30", nullable=False),
        sa.Column(
            "situacao",
            postgresql.ENUM(name="situacao_agendamento", create_type=False),
            server_default="MARCADO",
            nullable=False,
        ),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("criado_por", sa.Integer(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "paciente_id IS NOT NULL OR coalesce(nome_avulso, '') <> ''",
            name="ck_agendamento_tem_dono",
        ),
        sa.CheckConstraint(
            "duracao_min BETWEEN 5 AND 600", name="ck_agendamento_duracao_plausivel"
        ),
        sa.ForeignKeyConstraint(["clinica_id"], ["clinica.id"]),
        sa.ForeignKeyConstraint(["criado_por"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["paciente_id"], ["paciente.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agendamento_clinica_id"), "agendamento", ["clinica_id"])
    op.create_index(op.f("ix_agendamento_paciente_id"), "agendamento", ["paciente_id"])
    op.create_index("ix_agendamento_clinica_dia", "agendamento", ["clinica_id", "dia"])
    op.create_index("ix_agendamento_paciente_dia", "agendamento", ["paciente_id", "dia"])


def downgrade() -> None:
    op.drop_index("ix_agendamento_paciente_dia", table_name="agendamento")
    op.drop_index("ix_agendamento_clinica_dia", table_name="agendamento")
    op.drop_index(op.f("ix_agendamento_paciente_id"), table_name="agendamento")
    op.drop_index(op.f("ix_agendamento_clinica_id"), table_name="agendamento")
    op.drop_table("agendamento")
    postgresql.ENUM(name="situacao_agendamento").drop(op.get_bind(), checkfirst=True)
