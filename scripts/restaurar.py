"""Restaura um backup num banco de destino e CONFERE o resultado.

    python -m scripts.restaurar backups/bddente-2026-08-25.dump \\
        postgresql://usuario:senha@host:5432/bddente_restaurado

Backup nunca restaurado nao conta como backup. Este script existe para que o teste
de restauracao seja um comando, nao um projeto.
"""

import subprocess
import sys
from urllib.parse import urlparse

import psycopg

MINIMOS = {"paciente": 5_561, "lancamento": 44_812, "lancamento_regiao": 29_350}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 64

    arquivo, destino = sys.argv[1], sys.argv[2]
    url = urlparse(destino)
    resultado = subprocess.run(
        [
            "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
            f"--host={url.hostname}", f"--port={url.port or 5432}",
            f"--username={url.username}", f"--dbname={(url.path or '').lstrip('/')}",
            arquivo,
        ],
        env={"PGPASSWORD": url.password or "", "PATH": "/usr/bin:/bin"},
    )
    if resultado.returncode != 0:
        print("restauracao FALHOU", file=sys.stderr)
        return resultado.returncode

    with psycopg.connect(destino) as conexao:
        for tabela, esperado in MINIMOS.items():
            encontrado = conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]
            marca = "ok" if encontrado >= esperado else "FALHOU"
            print(f"  {tabela}: {encontrado} (esperado >= {esperado}) {marca}")
            if encontrado < esperado:
                return 3

    print("restauracao conferida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
