"""Leitor do extrato imutavel do Dentalis.

A migracao le daqui, nunca dos .DBF originais. O extrato ja foi verificado: 100%
dos registros lidos, encoding CP1252 confirmado, zero registros deletados, zero
referencias orfas. Ver dados_extraidos/DICIONARIO.md.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType


class Extrato:
    """Acesso somente leitura ao SQLite do extrato."""

    def __init__(self, caminho: str | Path) -> None:
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f"extrato nao encontrado: {caminho}")
        self._conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        self._conexao.row_factory = sqlite3.Row

    def linhas(self, tabela: str, ordem: str | None = None) -> Iterator[dict]:
        sql = f'SELECT * FROM "{tabela}"'  # noqa: S608 — nome de tabela vem de constante
        if ordem:
            sql += f' ORDER BY "{ordem}"'
        for linha in self._conexao.execute(sql):
            yield dict(linha)

    def contar(self, tabela: str) -> int:
        return self._conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]  # noqa: S608

    def consultar(self, sql: str, parametros: tuple = ()) -> list[sqlite3.Row]:
        return list(self._conexao.execute(sql, parametros))

    def fechar(self) -> None:
        self._conexao.close()

    def __enter__(self) -> "Extrato":
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        traco: TracebackType | None,
    ) -> None:
        self.fechar()
