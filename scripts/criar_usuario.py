"""Cria (ou troca a senha de) o usuario da clinica.

    python -m scripts.criar_usuario katia@exemplo.com "Katia"

A senha e pedida no terminal, sem eco, e nunca fica no historico do shell.
"""

import getpass
import sys

from sqlalchemy import select

from app.auth.models import Clinica, Usuario
from app.auth.senha import TAMANHO_MINIMO_SENHA, gerar_hash
from app.auth.service import criar_usuario
from app.shared.db import Sessao


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 64
    email, nome = sys.argv[1].strip().lower(), sys.argv[2].strip()

    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        print("as senhas nao conferem", file=sys.stderr)
        return 1
    if len(senha) < TAMANHO_MINIMO_SENHA:
        print(
            f"senha curta demais: use ao menos {TAMANHO_MINIMO_SENHA} caracteres. "
            "Esta senha abre 30 anos de prontuario.",
            file=sys.stderr,
        )
        return 1

    with Sessao() as sessao:
        clinica = sessao.scalars(select(Clinica).limit(1)).first()
        if clinica is None:
            clinica = Clinica(nome="Consultorio")
            sessao.add(clinica)
            sessao.flush()

        existente = sessao.scalars(select(Usuario).where(Usuario.email == email)).first()
        if existente is not None:
            existente.senha_hash = gerar_hash(senha)
            existente.ativo = True
            acao = "senha trocada"
        else:
            criar_usuario(
                sessao, clinica_id=clinica.id, email=email, senha=senha, nome=nome
            )
            acao = "usuario criado"
        sessao.commit()
    print(f"{acao}: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
