"""lembrete, modelo de mensagem e configuracao da clinica

Revision ID: 0009
Revises: 0008

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# O texto inicial. Ela vai reescrever, e o dela vai ser melhor — este existe para
# a tela nunca abrir vazia. Nada de dado clinico: nome, dia, hora e a clinica.
TEXTO_INICIAL = (
    "Oi {primeiro_nome}! Passando para lembrar do seu horário\n"
    "{dia_relativo}, {dia}, às {hora}, com a {dentista}.\n"
    "\n"
    "{clinica} — {endereco}\n"
    "Se não puder vir, me avise: {telefone_clinica}"
)


def upgrade() -> None:
    bind = op.get_bind()
    for nome, valores in (
        ("tipo_lembrete", ["VESPERA"]),
        (
            "situacao_lembrete",
            ["PENDENTE", "ENVIANDO", "ENVIADO", "FALHOU", "DESCARTADO",
             "EXPIRADO", "CANCELADO"],
        ),
    ):
        postgresql.ENUM(*valores, name=nome).create(bind, checkfirst=True)

    op.create_table(
        "modelo_mensagem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinica_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("atualizado_por", sa.Integer(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["clinica_id"], ["clinica.id"]),
        sa.ForeignKeyConstraint(["atualizado_por"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinica_id", "codigo", name="uq_modelo_por_clinica"),
    )
    op.create_index(
        op.f("ix_modelo_mensagem_clinica_id"), "modelo_mensagem", ["clinica_id"]
    )

    op.create_table(
        "configuracao_clinica",
        sa.Column("clinica_id", sa.Integer(), nullable=False),
        sa.Column(
            "lembrete_ativo", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("lembrete_hora", sa.Time(), server_default="18:00", nullable=False),
        sa.Column(
            "lembrete_horas_antes", sa.SmallInteger(), server_default="24", nullable=False
        ),
        sa.Column(
            "lembrete_teto_diario", sa.SmallInteger(), server_default="20", nullable=False
        ),
        sa.Column("whatsapp_provedor", sa.String(length=20), nullable=True),
        sa.Column("endereco", sa.String(length=200), nullable=True),
        sa.Column("telefone_clinica", sa.String(length=24), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["clinica_id"], ["clinica.id"]),
        sa.PrimaryKeyConstraint("clinica_id"),
    )

    op.create_table(
        "lembrete",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinica_id", sa.Integer(), nullable=False),
        sa.Column("agendamento_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo", postgresql.ENUM(name="tipo_lembrete", create_type=False), nullable=False
        ),
        sa.Column("numero", sa.String(length=24), nullable=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("modelo_id", sa.Integer(), nullable=True),
        sa.Column(
            "situacao",
            postgresql.ENUM(name="situacao_lembrete", create_type=False),
            server_default="PENDENTE",
            nullable=False,
        ),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("tentativas", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("provedor", sa.String(length=20), nullable=True),
        sa.Column("id_externo", sa.String(length=80), nullable=True),
        sa.Column("agendado_para", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["clinica_id"], ["clinica.id"]),
        sa.ForeignKeyConstraint(["agendamento_id"], ["agendamento.id"]),
        sa.ForeignKeyConstraint(["modelo_id"], ["modelo_mensagem.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agendamento_id", "tipo", name="uq_lembrete_um_por_agendamento"
        ),
    )
    op.create_index(op.f("ix_lembrete_clinica_id"), "lembrete", ["clinica_id"])
    op.create_index(op.f("ix_lembrete_agendamento_id"), "lembrete", ["agendamento_id"])
    op.create_index(
        "ix_lembrete_fila", "lembrete", ["clinica_id", "situacao", "agendado_para"]
    )

    # Semeia as clinicas que ja existem. Clinica criada DEPOIS ganha as linhas na
    # primeira leitura (`agenda.service.configuracao_de`) — "existe porque a
    # migration passou naquele dia" e suposicao que envelhece mal.
    op.execute(
        "INSERT INTO configuracao_clinica (clinica_id) "
        "SELECT id FROM clinica ON CONFLICT DO NOTHING"
    )
    op.execute(
        sa.text(
            "INSERT INTO modelo_mensagem (clinica_id, codigo, texto) "
            "SELECT id, 'LEMBRETE_VESPERA', :texto FROM clinica "
            "ON CONFLICT DO NOTHING"
        ).bindparams(texto=TEXTO_INICIAL)
    )


def downgrade() -> None:
    op.drop_index("ix_lembrete_fila", table_name="lembrete")
    op.drop_index(op.f("ix_lembrete_agendamento_id"), table_name="lembrete")
    op.drop_index(op.f("ix_lembrete_clinica_id"), table_name="lembrete")
    op.drop_table("lembrete")
    op.drop_table("configuracao_clinica")
    op.drop_index(op.f("ix_modelo_mensagem_clinica_id"), table_name="modelo_mensagem")
    op.drop_table("modelo_mensagem")
    bind = op.get_bind()
    for nome in ("situacao_lembrete", "tipo_lembrete"):
        postgresql.ENUM(name=nome).drop(bind, checkfirst=True)
