"""estado do whatsapp, visto pela ultima vez

Revision ID: 0010
Revises: 0009

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """O ultimo estado conhecido da conexao, para a agenda poder avisar.

    A agenda precisa mostrar a faixa "o WhatsApp desconectou" — e ela e a tela
    mais aberta do sistema. Perguntar a Evolution a cada carregamento poria uma
    chamada de rede no caminho da tela que ela usa o dia inteiro, com o timeout
    junto: uma Evolution travada deixaria a AGENDA lenta, e a agenda nao depende
    do lembrete para funcionar.

    Entao guarda-se o que ja se sabe. Quem escreve aqui e quem falou com a
    Evolution por outro motivo: o relogio, quando vai despachar, e a propria tela
    de Configuracoes, quando e aberta. A agenda so le.

    **Nao ha credencial nenhuma nestas colunas, e nao pode haver.** A sessao do
    WhatsApp vive dentro da Evolution, que e quem tem disco para ela. O que entra
    aqui e o que ja aparece na tela: um estado, um numero e uma hora.
    """
    op.add_column(
        "configuracao_clinica", sa.Column("whatsapp_estado", sa.String(20), nullable=True)
    )
    op.add_column(
        "configuracao_clinica", sa.Column("whatsapp_numero", sa.String(24), nullable=True)
    )
    op.add_column(
        "configuracao_clinica",
        sa.Column("whatsapp_visto_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("configuracao_clinica", "whatsapp_visto_em")
    op.drop_column("configuracao_clinica", "whatsapp_numero")
    op.drop_column("configuracao_clinica", "whatsapp_estado")
