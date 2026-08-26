"""Hash de senha com argon2 — o padrao recomendado hoje. Dado de saude e dado
pessoal sensivel pela LGPD; a senha que da acesso a ele nao pode ser reversivel."""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def conferir(senha: str, hash_guardado: str) -> bool:
    """Nunca levanta excecao: um hash corrompido no banco vira 'senha errada',
    nao erro 500 na tela de login."""
    try:
        return _hasher.verify(hash_guardado, senha)
    except (Argon2Error, ValueError, TypeError):
        return False
