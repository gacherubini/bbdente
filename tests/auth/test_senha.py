import pytest

from app.auth.models import Usuario
from app.auth.senha import conferir, gerar_hash, impressao
from app.auth.sessao import assinar, ler


def usuario_solto(identificador: int = 42, senha: str = "seja-la-qual-for") -> Usuario:
    """Um Usuario de memoria, sem banco: estes testes sao sobre o token."""
    return Usuario(id=identificador, senha_hash=gerar_hash(senha))


def test_hash_nao_guarda_a_senha_em_claro():
    h = gerar_hash("segredo-da-katia")
    assert "segredo-da-katia" not in h
    assert h.startswith("$argon2")


def test_senha_certa_confere_e_errada_nao():
    h = gerar_hash("segredo-da-katia")
    assert conferir("segredo-da-katia", h) is True
    assert conferir("outra-coisa", h) is False


def test_duas_chamadas_geram_hashes_diferentes():
    """Sal aleatorio: dois usuarios com a mesma senha nao ficam iguais no banco."""
    assert gerar_hash("igual") != gerar_hash("igual")


def test_hash_corrompido_nao_derruba_o_login():
    assert conferir("qualquer", "isto-nao-e-um-hash") is False


def test_token_de_sessao_faz_ida_e_volta():
    usuario = usuario_solto()
    assert ler(assinar(usuario)) == (42, impressao(usuario.senha_hash))


@pytest.mark.parametrize("token", ["", "lixo", "eyJ1IjoxfQ.assinatura-falsa"])
def test_token_adulterado_e_recusado(token):
    assert ler(token) is None


def test_token_expirado_e_recusado(monkeypatch):
    import app.auth.sessao as modulo

    token = assinar(usuario_solto())
    monkeypatch.setattr(modulo, "MAX_IDADE_SEGUNDOS", -1)
    assert ler(token) is None
