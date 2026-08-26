import pytest

from app.auth.senha import conferir, gerar_hash
from app.auth.sessao import assinar, ler


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
    assert ler(assinar(42)) == 42


@pytest.mark.parametrize("token", ["", "lixo", "eyJ1IjoxfQ.assinatura-falsa"])
def test_token_adulterado_e_recusado(token):
    assert ler(token) is None


def test_token_expirado_e_recusado(monkeypatch):
    import app.auth.sessao as modulo

    token = assinar(42)
    monkeypatch.setattr(modulo, "MAX_IDADE_SEGUNDOS", -1)
    assert ler(token) is None
