"""Hash de senha com argon2 — o padrao recomendado hoje. Dado de saude e dado
pessoal sensivel pela LGPD; a senha que da acesso a ele nao pode ser reversivel."""

import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()

# Esta senha abre 30 anos de prontuario. O minimo vale para a tela de perfil e para
# o `scripts/criar_usuario.py` — os dois leem daqui para nao divergirem.
TAMANHO_MINIMO_SENHA = 12


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def conferir(senha: str, hash_guardado: str) -> bool:
    """Nunca levanta excecao: um hash corrompido no banco vira 'senha errada',
    nao erro 500 na tela de login."""
    try:
        return _hasher.verify(hash_guardado, senha)
    except (Argon2Error, ValueError, TypeError):
        return False


def impressao(senha_hash: str) -> str:
    """Marca curta do hash, para carimbar no cookie de sessao.

    Trocar a senha muda o hash, muda a marca, e todo cookie emitido antes para de
    valer — inclusive o de quem estava com a senha vazada. Sem isso a sessao
    antiga continuaria abrindo o prontuario ate expirar sozinha, horas depois.

    Nao e o hash: e um resumo dele. O cookie viaja pelo navegador, e o que abre a
    senha por forca bruta nao pode sair do banco.
    """
    return hashlib.sha256(senha_hash.encode()).hexdigest()[:16]
