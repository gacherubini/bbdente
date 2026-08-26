from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import config


class Base(DeclarativeBase):
    """Base declarativa unica. Um banco, um metadata — a fronteira entre modulos
    e de codigo, nao de schema."""


engine = create_engine(config.database_url, pool_pre_ping=True)
Sessao = sessionmaker(engine, expire_on_commit=False)


def obter_sessao() -> Iterator[Session]:
    """Dependencia do FastAPI. Commit fica a cargo de quem chama."""
    with Sessao() as sessao:
        yield sessao
