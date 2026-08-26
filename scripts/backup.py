"""Backup do banco. Roda diariamente.

    python -m scripts.backup [pasta-destino]

Guarda um dump comprimido por dia. Nao apaga nada sozinho: prontuario tem guarda
minima de 10 anos e a decisao de descartar backup antigo e da clinica, nao do script.
"""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from app.config import config


def ambiente(url) -> dict[str, str]:
    """Ambiente do pg_dump: o da maquina, mais a senha.

    Nao cravar PATH aqui importa — o backup roda na maquina da clinica, que e
    Windows, onde um PATH de Linux faz o pg_dump nem ser encontrado.
    """
    return {**os.environ, "PGPASSWORD": url.password or ""}


def main() -> int:
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "backups")
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"bddente-{date.today().isoformat()}.dump"

    url = urlparse(config.database_url.replace("postgresql+psycopg://", "postgresql://"))
    comando = [
        "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
        f"--file={arquivo}",
        f"--host={url.hostname}", f"--port={url.port or 5432}",
        f"--username={url.username}", (url.path or "/bddente").lstrip("/"),
    ]
    resultado = subprocess.run(comando, env=ambiente(url))
    if resultado.returncode != 0:
        print("backup FALHOU", file=sys.stderr)
        return resultado.returncode

    tamanho = arquivo.stat().st_size
    if tamanho < 100_000:
        # Um dump de 5.559 cadastros e 44.812 lancamentos nunca e pequeno assim.
        print(f"backup suspeito: apenas {tamanho} bytes", file=sys.stderr)
        return 2
    print(f"backup gravado: {arquivo} ({tamanho // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
