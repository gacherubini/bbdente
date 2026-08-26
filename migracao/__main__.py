"""Roda a migracao inteira numa transacao so.

    python -m migracao

Nada e gravado se a conferencia final reprovar. Rodar de novo e seguro: cada etapa
e idempotente.
"""

import sys

from sqlalchemy import select

from app.auth.models import Clinica
from app.config import config
from app.shared.db import Sessao
from migracao import (
    anamnese,
    catalogo,
    condicoes,
    financeiro,
    lancamentos,
    pacientes,
)
from migracao.conferencia import ConferenciaFalhou, conferir
from migracao.extrato import Extrato


def main() -> int:
    with Sessao() as sessao, Extrato(config.extrato_sqlite) as extrato:
        clinica = sessao.scalars(select(Clinica).limit(1)).first()
        if clinica is None:
            clinica = Clinica(nome="Consultorio Dra. Katia")
            sessao.add(clinica)
            sessao.flush()

        print("catalogo...", flush=True)
        print(" ", catalogo.migrar(sessao, extrato, clinica.id))
        print("pacientes...", flush=True)
        print(" ", pacientes.migrar(sessao, extrato, clinica.id))
        print("lancamentos... (44.812 registros, leva alguns minutos)", flush=True)
        print(" ", lancamentos.migrar(sessao, extrato, clinica.id))
        print("condicoes...", flush=True)
        print(" ", condicoes.migrar(sessao, extrato, clinica.id))
        print("anamnese...", flush=True)
        print(" ", anamnese.migrar(sessao, extrato, clinica.id))
        print("financeiro... (28.244 parcelas)", flush=True)
        print(" ", financeiro.migrar(sessao, extrato, clinica.id))

        print("conferindo...", flush=True)
        divergencias = conferir(sessao, clinica.id)
        if divergencias:
            sessao.rollback()
            raise ConferenciaFalhou(divergencias)

        sessao.commit()
        print("conferencia aprovada. migracao gravada.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConferenciaFalhou as erro:
        print(erro, file=sys.stderr)
        sys.exit(1)
