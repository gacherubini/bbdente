from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.shared.modelos  # noqa: F401  — registra todos os modelos no metadata
from alembic import context
from app.config import config as config_app
from app.shared.db import Base

config = context.config
if config.config_file_name is not None:
    # `disable_existing_loggers=False` nao e enfeite: o padrao do `fileConfig` e
    # DESLIGAR todo logger que ja exista. Rodando o Alembic no mesmo processo do
    # app — que e o que o `conftest.py` faz — isso emudece
    # `app/agenda/relogio.py`, e um relogio que falha em silencio e exatamente o
    # que ele nao pode ser.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", config_app.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectavel = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectavel.connect() as conexao:
        context.configure(connection=conexao, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
