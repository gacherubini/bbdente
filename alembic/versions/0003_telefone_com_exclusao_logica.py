"""telefone com exclusao logica

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-26 07:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Editar o cadastro pode trocar o telefone, e trocar nao pode apagar.

    O numero antigo as vezes e a unica forma de achar alguem que nao volta ha
    vinte anos. A regra da casa vale aqui como em todo o resto: exclusao e
    logica, nunca DELETE.
    """
    op.add_column(
        "paciente_telefone",
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Voltar apaga de verdade os numeros que estavam so marcados — nao ha para
    # onde guarda-los num schema sem a coluna.
    op.execute("DELETE FROM paciente_telefone WHERE excluido_em IS NOT NULL")
    op.drop_column("paciente_telefone", "excluido_em")
