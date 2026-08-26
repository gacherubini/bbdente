"""parcela substituida

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-26 08:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """O Dentalis registrava carne regravando o SALDO a cada pagamento.

    Sete linhas com o mesmo vencimento e ORIGINAL caindo 1.200, 1.050, 900...
    nao sao sete dividas de R$ 5.250: sao uma divida de R$ 1.200 sendo paga em
    sete vezes. Somar todas as linhas inflava o 'a receber' em R$ 1.392.888,31.

    A linha continua no banco — preservar e marcar, como o resto da migracao. O
    que muda e que a soma da divida pula as que ja foram substituidas.
    """
    op.add_column(
        "parcela",
        sa.Column(
            "substituida",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("parcela", "substituida")
