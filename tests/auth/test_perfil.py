"""Perfil do usuario: ver quem esta logado, mudar o nome, trocar a senha.

O teste que mais importa aqui e o da sessao: trocar a senha tem de derrubar todo
cookie emitido antes. Sem isso, senha vazada continua abrindo 30 anos de
prontuario ate o cookie expirar sozinho.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica, Usuario
from app.auth.senha import TAMANHO_MINIMO_SENHA, conferir, impressao
from app.auth.service import SenhaRecusada, criar_usuario, renomear, trocar_senha
from app.auth.sessao import NOME_COOKIE, assinar, ler
from app.main import criar_app
from app.shared.db import obter_sessao

SENHA = "senha-forte-de-verdade"
NOVA = "outra-senha-bem-longa"


@pytest.fixture
def cliente(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def katia(sessao):
    clinica = Clinica(nome="Consultorio da Katia")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="katia@exemplo.com", senha=SENHA,
        nome="Katia",
    )
    sessao.flush()
    return usuario


@pytest.fixture
def logada(cliente, katia):
    cliente.cookies.set(NOME_COOKIE, assinar(katia))
    return cliente


# --- service ---------------------------------------------------------------

def test_trocar_senha_grava_a_nova_e_aposenta_a_antiga(sessao, katia):
    trocar_senha(sessao, katia, atual=SENHA, nova=NOVA, repetida=NOVA)
    sessao.flush()
    assert conferir(NOVA, katia.senha_hash) is True
    assert conferir(SENHA, katia.senha_hash) is False


def test_trocar_senha_exige_a_senha_atual_certa(sessao, katia):
    with pytest.raises(SenhaRecusada, match="atual"):
        trocar_senha(sessao, katia, atual="chute", nova=NOVA, repetida=NOVA)
    assert conferir(SENHA, katia.senha_hash) is True


def test_trocar_senha_exige_a_repeticao_conferindo(sessao, katia):
    with pytest.raises(SenhaRecusada, match="conferem"):
        trocar_senha(sessao, katia, atual=SENHA, nova=NOVA, repetida=NOVA + "x")
    assert conferir(SENHA, katia.senha_hash) is True


def test_trocar_senha_recusa_senha_curta(sessao, katia):
    curta = "a" * (TAMANHO_MINIMO_SENHA - 1)
    with pytest.raises(SenhaRecusada, match=str(TAMANHO_MINIMO_SENHA)):
        trocar_senha(sessao, katia, atual=SENHA, nova=curta, repetida=curta)
    assert conferir(SENHA, katia.senha_hash) is True


def test_trocar_senha_recusa_repetir_a_mesma_senha(sessao, katia):
    with pytest.raises(SenhaRecusada, match="diferente"):
        trocar_senha(sessao, katia, atual=SENHA, nova=SENHA, repetida=SENHA)


def test_trocar_senha_audita_sem_guardar_nada_da_senha(sessao, katia):
    trocar_senha(sessao, katia, atual=SENHA, nova=NOVA, repetida=NOVA)
    sessao.flush()
    linha = sessao.scalars(
        select(Auditoria)
        .where(Auditoria.entidade == "usuario", Auditoria.acao == "ATUALIZAR")
        .order_by(Auditoria.id.desc())
    ).first()
    assert linha is not None
    assert linha.entidade_id == katia.id
    registro = str(linha.dados_antes) + str(linha.dados_depois)
    assert NOVA not in registro
    assert SENHA not in registro
    assert "argon2" not in registro


def test_renomear_troca_o_nome_e_audita(sessao, katia):
    renomear(sessao, katia, nome="Katia Abreu")
    sessao.flush()
    assert katia.nome == "Katia Abreu"
    linha = sessao.scalars(
        select(Auditoria)
        .where(Auditoria.entidade == "usuario", Auditoria.acao == "ATUALIZAR")
        .order_by(Auditoria.id.desc())
    ).first()
    assert linha.dados_antes["nome"] == "Katia"
    assert linha.dados_depois["nome"] == "Katia Abreu"


def test_renomear_recusa_nome_vazio(sessao, katia):
    with pytest.raises(ValueError, match="nome"):
        renomear(sessao, katia, nome="   ")


# --- sessao ----------------------------------------------------------------

def test_o_cookie_carrega_a_marca_da_senha(katia):
    assert ler(assinar(katia)) == (katia.id, impressao(katia.senha_hash))


def test_o_cookie_nao_carrega_o_hash_da_senha(katia):
    """A marca viaja no navegador; o hash nunca sai do banco."""
    token = assinar(katia)
    assert katia.senha_hash not in token
    assert "argon2" not in token


def test_trocar_a_senha_derruba_o_cookie_antigo(logada, sessao, katia):
    assert logada.get("/pacientes").status_code == 200

    trocar_senha(sessao, katia, atual=SENHA, nova=NOVA, repetida=NOVA)
    sessao.flush()

    resposta = logada.get("/pacientes")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


# --- telas -----------------------------------------------------------------

def test_a_tela_de_perfil_mostra_quem_esta_logado(logada):
    corpo = logada.get("/perfil").text
    assert "Katia" in corpo
    assert "katia@exemplo.com" in corpo
    assert "Consultorio da Katia" in corpo


def test_perfil_exige_sessao(cliente):
    resposta = cliente.get("/perfil")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_toda_tela_mostra_o_nome_de_quem_esta_logado(logada):
    """A auditoria grava usuario_id em toda escrita. A tela tem de dizer em nome
    de quem voce esta gravando."""
    for caminho in ("/pacientes", "/odontograma", "/perfil"):
        assert "Katia" in logada.get(caminho).text, caminho


def test_toda_tela_tem_como_sair(logada):
    for caminho in ("/pacientes", "/odontograma", "/perfil"):
        assert 'action="/logout"' in logada.get(caminho).text, caminho


def test_trocar_a_senha_pela_tela_mantem_quem_trocou_logada(logada, sessao, katia):
    resposta = logada.post(
        "/perfil/senha", data={"atual": SENHA, "nova": NOVA, "repetida": NOVA}
    )
    assert resposta.status_code == 303
    assert conferir(NOVA, katia.senha_hash) is True
    # o cookie foi reemitido com a marca nova: quem trocou continua trabalhando
    assert logada.get("/pacientes").status_code == 200


def test_trocar_a_senha_pela_tela_com_a_atual_errada_nao_troca(logada, katia):
    resposta = logada.post(
        "/perfil/senha", data={"atual": "chute", "nova": NOVA, "repetida": NOVA}
    )
    assert resposta.status_code == 200
    assert "atual" in resposta.text.lower()
    assert conferir(SENHA, katia.senha_hash) is True


def test_mudar_o_nome_pela_tela(logada, katia):
    resposta = logada.post("/perfil", data={"nome": "Dra. Katia"})
    assert resposta.status_code == 303
    assert katia.nome == "Dra. Katia"


def test_login_depois_da_troca_usa_a_senha_nova(cliente, sessao, katia):
    trocar_senha(sessao, katia, atual=SENHA, nova=NOVA, repetida=NOVA)
    sessao.flush()
    assert cliente.post(
        "/login", data={"email": "katia@exemplo.com", "senha": SENHA}
    ).status_code == 200
    resposta = cliente.post(
        "/login", data={"email": "katia@exemplo.com", "senha": NOVA}
    )
    assert resposta.status_code == 303
    assert NOME_COOKIE in resposta.cookies


def test_cookie_de_usuario_inexistente_volta_para_o_login(cliente, katia):
    """Cookie bem assinado apontando para quem nao esta no banco: login, nao 500."""
    fantasma = Usuario(id=999_999, senha_hash=katia.senha_hash)
    cliente.cookies.set(NOME_COOKIE, assinar(fantasma))
    assert cliente.get("/pacientes").status_code == 303


def test_usuario_desativado_perde_a_sessao_em_andamento(logada, sessao, katia):
    assert logada.get("/pacientes").status_code == 200
    katia.ativo = False
    sessao.flush()
    assert logada.get("/pacientes").status_code == 303
