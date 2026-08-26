import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def cliente_logado(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    sessao.add(
        Paciente(
            clinica_id=clinica.id, codigo_legado="0001/PT",
            nome="Claudia Moreira Sant'Ana",
            revisar_motivo=["data_suspeita", "telefone_incompleto"],
        )
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def test_a_tela_lista_o_paciente(cliente_logado):
    resposta = cliente_logado.get("/pacientes?filtro=todos")
    assert resposta.status_code == 200
    # O apostrofo sai escapado: o autoescape do Jinja2 esta ligado, e e assim que
    # tem de ser. Procurar o literal cru testaria a ausencia de protecao contra XSS.
    assert "Claudia Moreira Sant&#39;Ana" in resposta.text


def test_a_busca_e_o_primeiro_campo_da_tela(cliente_logado):
    """E o que ela faz o dia inteiro; nao pode estar escondido atras de um menu."""
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert html.index('class="busca"') < html.index("<table")


def test_dado_suspeito_aparece_marcado_nao_escondido(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'class="aviso"' in html


def test_a_tela_marca_a_aba_pacientes_como_ativa(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'href="/pacientes" class="ativo"' in html


def test_os_quatro_filtros_aparecem(cliente_logado):
    html = cliente_logado.get("/pacientes").text
    for rotulo in ("Ativos", "Com pendência", "Em aberto", "Todos"):
        assert rotulo in html


def test_cada_linha_leva_para_o_odontograma(cliente_logado, sessao):
    paciente = sessao.query(Paciente).one()
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert f'/odontograma/{paciente.id}' in html


def test_filtro_invalido_cai_no_padrao_em_vez_de_dar_erro(cliente_logado):
    assert cliente_logado.get("/pacientes?filtro=inventado").status_code == 200
