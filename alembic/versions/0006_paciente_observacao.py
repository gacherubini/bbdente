"""paciente observacao

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-26 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """O unico campo da ficha que o Dentalis nao tinha.

    CPF, indicacao e endereco vieram do ARQCLIEN e ja estao no schema desde o
    0001 — faltava so a tela. A observacao nasce aqui, vazia para os 5.561
    cadastros migrados, e e texto livre de proposito: o que a recepcao anota
    ('nao atende de manha', 'filha da dona Marta') nao cabe em campo estruturado.
    """
    op.add_column("paciente", sa.Column("observacao", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("paciente", "observacao")
