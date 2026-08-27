"""consentimento de whatsapp

Revision ID: 0008
Revises: 0007

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Quem autorizou receber mensagem, e quem nunca foi perguntado.

    `paciente.aceita_whatsapp` nasce NULO em TODAS as linhas, inclusive nos 5.559
    cadastros migrados — e nao ha backfill de proposito. NULO significa "nunca
    perguntamos", e nao recebe. Marcar todo mundo como `true` aqui mandaria
    mensagem para 5.559 pessoas cujo telefone foi coletado desde 1996 para outra
    finalidade, sem registro de autorizacao nenhum.

    `agendamento.avisar_avulso` nasce LIGADO, e a diferenca nao e incoerencia: o
    telefone avulso e ditado ao telefone para marcar aquela consulta, e avisar
    dela e a finalidade para a qual o numero acabou de ser dado.
    """
    op.add_column("paciente", sa.Column("aceita_whatsapp", sa.Boolean(), nullable=True))
    op.add_column(
        "agendamento",
        sa.Column(
            "avisar_avulso", sa.Boolean(), server_default="true", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("agendamento", "avisar_avulso")
    op.drop_column("paciente", "aceita_whatsapp")
