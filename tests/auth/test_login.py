import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica, Usuario  # noqa: F401
from app.auth.service import autenticar, criar_usuario
from app.auth.sessao import NOME_COOKIE
from app.main import criar_app
from app.shared.db import obter_sessao


@pytest.fixture
def cliente(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def katia(sessao):
    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao,
        clinica_id=clinica.id,
        email="katia@exemplo.com",
        senha="senha-forte-de-verdade",
        nome="Katia",
    )
    sessao.flush()
    return usuario


def test_autenticar_aceita_a_senha_certa(sessao, katia):
    assert autenticar(sessao, "katia@exemplo.com", "senha-forte-de-verdade") is not None


@pytest.mark.parametrize(
    ("email", "senha"),
    [
        ("katia@exemplo.com", "errada"),
        ("naoexiste@exemplo.com", "senha-forte-de-verdade"),
        ("", ""),
    ],
)
def test_autenticar_recusa_o_resto(sessao, katia, email, senha):
    assert autenticar(sessao, email, senha) is None


def test_usuario_inativo_nao_entra(sessao, katia):
    katia.ativo = False
    sessao.flush()
    assert autenticar(sessao, "katia@exemplo.com", "senha-forte-de-verdade") is None


def test_login_bem_sucedido_seta_cookie_e_redireciona(cliente, katia):
    resposta = cliente.post(
        "/login", data={"email": "katia@exemplo.com", "senha": "senha-forte-de-verdade"}
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes"
    assert NOME_COOKIE in resposta.cookies


def test_login_errado_volta_para_a_tela_sem_cookie(cliente, katia):
    resposta = cliente.post("/login", data={"email": "katia@exemplo.com", "senha": "x"})
    assert resposta.status_code == 200
    assert NOME_COOKIE not in resposta.cookies
    assert "senha" in resposta.text.lower()


@pytest.mark.xfail(reason="rota /pacientes chega na Task 12")
def test_pagina_protegida_sem_sessao_manda_para_o_login(cliente):
    resposta = cliente.get("/pacientes")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_logout_apaga_o_cookie(cliente, katia):
    cliente.post(
        "/login", data={"email": "katia@exemplo.com", "senha": "senha-forte-de-verdade"}
    )
    resposta = cliente.post("/logout")
    assert resposta.status_code == 303
    assert cliente.cookies.get(NOME_COOKIE) in (None, "")


def test_criar_usuario_deixa_rastro_na_auditoria(sessao, katia):
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "usuario")
    ).all()
    assert len(linhas) == 1
    assert linhas[0].acao == "CRIAR"
    assert linhas[0].entidade_id == katia.id
    assert "senha" not in str(linhas[0].dados_depois).lower()


def test_auditoria_nunca_guarda_hash_de_senha(sessao, katia):
    for linha in sessao.scalars(select(Auditoria)):
        assert "argon2" not in str(linha.dados_depois or "")
