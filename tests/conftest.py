import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.config import config as config_app

# O env var manda (e o que o CI usa); sem ele, cai no .env local.
URL_TESTE = os.environ.get("DATABASE_URL_TESTE", config_app.database_url_teste)


def alembic_para(url: str) -> AlembicConfig:
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def recriar_banco(url: str) -> None:
    """Joga o banco de teste fora e cria um vazio no lugar.

    Isto substituiu um `alembic downgrade base`, e a razao e tempo de vida: o
    `downgrade` derruba tabela por tabela, e o custo dele **depende do que sobrou
    da rodada anterior** — 9 s com o banco limpo, 51 s depois dos testes de
    migracao, 100 s depois de uma rodada interrompida no meio deles. Era o custo
    fixo de TODA invocacao do pytest, e nao um teste: o teste mais lento da suite
    de agenda leva 0,11 s.

    `DROP DATABASE` nao percorre nada — o Postgres desliga os arquivos. Sao 0,35 s,
    sempre os mesmos 0,35 s, e sem herdar sujeira de ninguem.

    O `WITH (FORCE)` derruba conexao pendurada de uma rodada anterior morta, que
    e o unico jeito de isto travar. Precisa de Postgres 13+ e de um usuario que
    possa criar banco — o `bddente` do docker-compose e o do CI sao os dois.
    """
    alvo = make_url(url)
    admin = create_engine(alvo.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conexao:
        conexao.execute(text(f'DROP DATABASE IF EXISTS "{alvo.database}" WITH (FORCE)'))
        conexao.execute(text(f'CREATE DATABASE "{alvo.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine_teste():
    """Sobe o schema do zero uma vez por sessao de teste, pelo proprio Alembic.

    Usar o Alembic (e nao `Base.metadata.create_all`) e proposital: garante que as
    migrations que vao rodar em producao sao as mesmas que os testes exercitam.
    Quem exercita o caminho de VOLTA e `tests/test_migrations.py`, sozinho — antes
    ele vinha de graca aqui, e cobrava o preco descrito em `recriar_banco`.
    """
    recriar_banco(URL_TESTE)
    engine = create_engine(URL_TESTE)
    command.upgrade(alembic_para(URL_TESTE), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def sessao(engine_teste):
    """Uma sessao por teste, sempre revertida no fim. Testes nao se enxergam."""
    conexao = engine_teste.connect()
    transacao = conexao.begin()
    with Session(bind=conexao, expire_on_commit=False) as s:
        yield s
    transacao.rollback()
    conexao.close()
