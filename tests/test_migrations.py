"""O caminho de volta das migrations, num banco descartável só dele.

Isto existia de graça dentro do `conftest.py`: cada invocação do pytest fazia
`downgrade base` antes de subir o schema, e com isso o `downgrade()` de cada
migration era exercitado sem ninguém pedir. Custava de 9 a 100 segundos por
rodada, e virou `DROP DATABASE` — que é 0,35 s e não passa por função nenhuma.

A cobertura não podia sumir junto: o plano pede `upgrade`/`downgrade` limpos, com
os enums sumindo no downgrade (Task 12). Ela mudou de lugar, e agora é um teste
que diz o que prova, num banco próprio para não atrapalhar a sessão dos outros.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from tests.conftest import URL_TESTE, alembic_para, recriar_banco

# Banco próprio: o `downgrade base` derruba tudo, e fazer isso no banco da sessão
# puxaria o tapete dos outros testes.
#
# `render_as_string(hide_password=False)` e não `str(url)`: o `str()` de uma URL do
# SQLAlchemy troca a senha por `***`, e o que sai dele não conecta em lugar nenhum.
_BASE = make_url(URL_TESTE)
URL = _BASE.set(database=f"{_BASE.database}_migrations").render_as_string(
    hide_password=False
)

# `alembic_version` fica de fora da conta: ela é a contabilidade do próprio
# Alembic, não do domínio, e sobrevive ao `downgrade base` de propósito — é ela
# que sabe que o banco está em "base" e não em "nunca migrado".
TABELAS = text(
    """select count(*) from information_schema.tables
       where table_schema = 'public' and table_name <> 'alembic_version'"""
)
ENUMS = text(
    """select count(*) from pg_type t
       join pg_namespace n on n.oid = t.typnamespace
       where n.nspname = 'public' and t.typtype = 'e'"""
)


def test_o_downgrade_desfaz_tudo_e_leva_os_enums_junto():
    """Enum é a pegadinha: o SQLAlchemy cria o tipo, mas `drop_table` não o
    remove. Um `downgrade` que esquece disso parece limpo e quebra o `upgrade`
    seguinte com "type already exists" — erro que só aparece na segunda vez."""
    recriar_banco(URL)
    cfg = alembic_para(URL)
    engine = create_engine(URL)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as conexao:
            assert conexao.execute(TABELAS).scalar() > 0
            assert conexao.execute(ENUMS).scalar() > 0

        command.downgrade(cfg, "base")
        with engine.connect() as conexao:
            assert conexao.execute(TABELAS).scalar() == 0
            assert conexao.execute(ENUMS).scalar() == 0

        # E sobe de novo: é aqui que um enum esquecido apareceria.
        command.upgrade(cfg, "head")
        with engine.connect() as conexao:
            assert conexao.execute(TABELAS).scalar() > 0
    finally:
        engine.dispose()
