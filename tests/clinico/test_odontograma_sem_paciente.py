"""Clicar em 'Odontograma' no menu sem paciente escolhido nao pode parecer que a tela
travou. O odontograma e sempre de alguem: leva para a busca e diz por que esta ali."""

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    sessao.add(Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda"))
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def test_o_menu_leva_para_a_busca_dizendo_o_motivo(cliente):
    resposta = cliente.get("/odontograma")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes?escolher=odontograma"


def test_a_lista_explica_que_falta_escolher_o_paciente(cliente):
    resposta = cliente.get("/pacientes?escolher=odontograma")
    assert resposta.status_code == 200
    assert "Escolha um paciente para abrir o odontograma" in resposta.text


def test_o_menu_do_odontograma_fica_marcado_como_a_aba_atual(cliente):
    """Senao o clique no menu nao da retorno nenhum: a lista abre identica."""
    html = cliente.get("/pacientes?escolher=odontograma").text
    assert 'href="/odontograma" class="ativo"' in html


def test_sem_o_parametro_a_lista_nao_mostra_aviso_nenhum(cliente):
    assert "Escolha um paciente" not in cliente.get("/pacientes").text
