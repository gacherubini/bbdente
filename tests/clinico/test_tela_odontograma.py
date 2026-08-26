import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo

JS = Path("app/static/odontograma.js")


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([categoria, paciente])
    sessao.flush()
    sessao.add(
        Procedimento(
            clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
            categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES,
            regioes_sugeridas=[],
        )
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c, paciente


def test_a_tela_abre_e_mostra_o_nome_do_paciente(cliente):
    c, paciente = cliente
    resposta = c.get(f"/odontograma/{paciente.id}")
    assert resposta.status_code == 200
    assert "Amanda" in resposta.text


def test_o_estado_inteiro_vem_embutido_na_pagina(cliente):
    """Sem segunda ida ao servidor so para desenhar: a tela ja nasce pronta."""
    c, paciente = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    bruto = re.search(
        r'id="estado-inicial"[^>]*>(.*?)</script>', html, re.S
    )
    assert bruto, "o JSON de estado nao esta embutido na pagina"
    estado = json.loads(bruto.group(1))
    assert len(estado["dentes"]) == 32
    assert estado["dentes"]["16"]["paredes"]["DIREITA"] == "MESIAL"


def test_a_tela_marca_a_aba_odontograma(cliente):
    c, paciente = cliente
    assert 'href="/odontograma" class="ativo"' in c.get(f"/odontograma/{paciente.id}").text


def test_a_legenda_das_tres_cores_aparece(cliente):
    c, paciente = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    for rotulo in ("Planejado", "Realizado", "Já existente"):
        assert rotulo in html


def test_paciente_inexistente_da_404(cliente):
    c, _ = cliente
    assert c.get("/odontograma/999999").status_code == 404


def test_odontograma_sem_paciente_volta_para_a_lista(cliente):
    c, _ = cliente
    resposta = c.get("/odontograma")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes"


# --- contrato do desenhista ----------------------------------------------------


def test_o_javascript_le_a_geometria_do_servidor_e_nao_a_recalcula():
    """Se o JS voltar a decidir sozinho qual parede e mesial, a regra de
    espelhamento passa a existir em dois lugares — e um deles nao tem teste."""
    fonte = JS.read_text(encoding="utf-8")
    assert "paredes" in fonte
    assert "canais_tela" in fonte
    for proibido in ("quadrante", "% 10", "fdi < 30"):
        assert proibido not in fonte, f"logica de anatomia vazou para o JS: {proibido}"


def test_toda_regiao_desenhada_carrega_dente_e_regiao_no_elemento():
    fonte = JS.read_text(encoding="utf-8")
    assert "data-dente" in fonte
    assert "data-regiao" in fonte
