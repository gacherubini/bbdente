import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.config import config as config_app

# O env var manda (e o que o CI usa); sem ele, cai no .env local.
URL_TESTE = os.environ.get("DATABASE_URL_TESTE", config_app.database_url_teste)


@pytest.fixture(scope="session")
def engine_teste():
    """Sobe o schema do zero uma vez por sessao de teste, pelo proprio Alembic.

    Usar o Alembic (e nao Base.metadata.create_all) e proposital: garante que as
    migrations que vao rodar em producao sao as mesmas que os testes exercitam.
    """
    engine = create_engine(URL_TESTE)
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", URL_TESTE)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
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
