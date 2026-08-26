"""O `fly postgres attach` grava DATABASE_URL no formato 'postgres://...', que o
SQLAlchemy nao aceita — e 'postgresql://' sozinho procura o psycopg2, que nao esta
instalado. Sem normalizar, o app sobe no Fly e morre na primeira consulta."""

import pytest

from app.config import normalizar_url


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        (
            "postgres://bddente:senha@host.internal:5432/bddente",
            "postgresql+psycopg://bddente:senha@host.internal:5432/bddente",
        ),
        (
            "postgresql://bddente:senha@host:5432/bddente",
            "postgresql+psycopg://bddente:senha@host:5432/bddente",
        ),
        (
            "postgresql+psycopg://bddente:senha@host:5432/bddente",
            "postgresql+psycopg://bddente:senha@host:5432/bddente",
        ),
        ("", ""),
    ],
)
def test_normalizar_url(bruto, esperado):
    assert normalizar_url(bruto) == esperado


def test_a_config_normaliza_o_que_vem_do_ambiente(monkeypatch):
    from app.config import Config

    monkeypatch.setenv("DATABASE_URL", "postgres://u:s@h:5432/d")
    assert Config().database_url == "postgresql+psycopg://u:s@h:5432/d"
