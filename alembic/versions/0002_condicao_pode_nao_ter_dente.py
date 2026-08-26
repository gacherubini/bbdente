"""condicao pode nao ter dente

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-26 00:24:41.963285

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Condicao sem dente: os 5.522 icones de boca inteira do ARQICONE (NUMDENTE
    de 81 a 88) sao condicao real, mas nao pertencem a um dente."""
    op.alter_column("condicao", "dente", existing_type=sa.SMALLINT(), nullable=True)


def downgrade() -> None:
    """Desce apagando o que nao cabe: sem dente, a linha nao pode existir."""
    op.execute("DELETE FROM condicao WHERE dente IS NULL")
    op.alter_column("condicao", "dente", existing_type=sa.SMALLINT(), nullable=False)
