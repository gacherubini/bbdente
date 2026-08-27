"""Contrato da tela do odontograma: o que fica onde, e o que o desenho responde.

Esta tela e usada de luva, com a paciente na cadeira. Dois defeitos que estes
testes travam: a lista do que ja foi marcado nascia no fim de um painel de dez
campos, fora da tela; e clicar num dente nao mudava nada no desenho, so no
painel ao lado.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao

CSS = Path("app/static/bddente.css")
JS_DESENHO = Path("app/static/odontograma.js")
JS_PAINEL = Path("app/static/painel.js")
PAINEL = Path("app/templates/_painel_lancamento.html")

# Os ids que o rascunho.js procura. Mover a lista de lugar nao pode derrubar
# nenhum deles — o JS acha por id, nao por posicao.
IDS_DO_RASCUNHO = ("atendimento-itens", "atendimento-vazio", "atendimento-concluir")


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    sessao.add_all([
        Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4),
        Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda"),
    ])
    sessao.flush()
    paciente = sessao.query(Paciente).first()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        yield c, paciente


def regra(nome: str) -> str:
    """O corpo de uma regra do CSS, pelo seletor exato."""
    css = CSS.read_text(encoding="utf-8")
    achado = re.search(rf"{re.escape(nome)}\s*\{{([^}}]*)\}}", css, re.S)
    assert achado, f"regra {nome} nao encontrada"
    return achado.group(1)


# --- onde a lista do rascunho mora -----------------------------------------

def test_a_lista_do_rascunho_nao_mora_dentro_do_painel():
    """Dentro do painel ela nascia depois de dez campos, abaixo da dobra — e e
    justamente o que se olha o tempo todo enquanto marca."""
    fonte = PAINEL.read_text(encoding="utf-8")
    for identificador in IDS_DO_RASCUNHO:
        assert identificador not in fonte, f"{identificador} ainda esta no painel"


def test_a_boca_em_branco_continua_com_todos_os_ganchos_do_rascunho(cliente):
    c, _ = cliente
    corpo = c.get("/odontograma").text
    for identificador in IDS_DO_RASCUNHO:
        assert f'id="{identificador}"' in corpo, identificador


def test_o_odontograma_de_um_paciente_nao_mostra_a_lista_do_rascunho(cliente):
    """Com paciente o lancamento grava na hora; nao ha rascunho para listar."""
    c, paciente = cliente
    corpo = c.get(f"/odontograma/{paciente.id}").text
    for identificador in IDS_DO_RASCUNHO:
        assert identificador not in corpo, identificador


# --- o desenho responde ao que foi selecionado -----------------------------

def test_o_desenho_sabe_destacar_o_que_esta_selecionado():
    """Antes, clicar num dente mudava so o texto do painel: no desenho sobrava
    o traco de :hover, que some quando o mouse sai."""
    assert "destacar" in JS_DESENHO.read_text(encoding="utf-8")


def test_o_painel_avisa_o_desenho_quando_a_selecao_muda():
    assert "destacar" in JS_PAINEL.read_text(encoding="utf-8")


def test_o_destaque_sobrevive_ao_redesenho():
    """`atualizar()` refaz o innerHTML inteiro. Se o destaque nao for reaplicado
    depois, lancar um tratamento apaga a selecao da tela."""
    fonte = JS_DESENHO.read_text(encoding="utf-8")
    assert re.search(r"function desenhar\b", fonte)
    assert re.search(r"aplicarDestaque\s*\(", fonte), (
        "desenhar() precisa reaplicar o destaque depois de refazer o SVG"
    )


def test_o_desenho_continua_sem_saber_anatomia():
    """Mesma trava do test_tela_odontograma, repetida aqui porque este arquivo
    mexe no desenhista: a regra de espelhamento vive em shared/dentes.py."""
    fonte = JS_DESENHO.read_text(encoding="utf-8")
    for proibido in ("quadrante", "% 10", "fdi < 30"):
        assert proibido not in fonte, f"anatomia vazou para o JS: {proibido}"


# --- geometria da tela ------------------------------------------------------

def test_o_desenho_acompanha_a_largura_que_tem():
    """O SVG nascia com largura fixa em px e a coluna sobrava ou faltava. Com
    largura fluida ele cresce ate o limite da coluna — dente maior e alvo de
    clique maior, que e o que importa para quem marca de luva."""
    corpo = regra("#odontograma svg")
    assert re.search(r"width\s*:\s*100%", corpo)
    assert re.search(r"height\s*:\s*auto", corpo)


def test_o_painel_gruda_na_janela():
    """Adicionar, Repetir e Concluir ficavam abaixo da dobra numa tela de 900px."""
    corpo = regra(".painel")
    assert re.search(r"position\s*:\s*sticky", corpo)
    assert re.search(r"top\s*:", corpo)
    assert re.search(r"overflow-y\s*:\s*auto", corpo), (
        "painel mais alto que a janela precisa rolar por dentro"
    )


def test_a_tela_do_odontograma_usa_a_faixa_larga():
    """Dente maior precisa de largura; esta tela e a unica que pede mais que as
    outras."""
    html = Path("app/templates/odontograma.html").read_text(encoding="utf-8")
    assert re.search(r"block largura\s*%\}\s*larga", html)
    assert re.search(r"max-width\s*:", regra(".faixa.larga"))


def test_o_historico_preenche_o_mesmo_vao_que_a_lista_do_rascunho(cliente):
    """Na tela do paciente o vao ao lado do painel era igualmente vazio. Quem o
    preenche la e o historico — mesma coluna, mesmo lugar."""
    c, paciente = cliente
    corpo = c.get(f"/odontograma/{paciente.id}").text
    coluna = corpo.index('class="odonto-coluna"')
    painel = corpo.index('class="painel"', coluna)
    assert coluna < corpo.index("titulo-historico") < painel, (
        "o historico saiu da coluna da esquerda"
    )


def test_titulo_e_tabela_do_historico_continuam_vizinhos():
    """O historico.js acha o historico por `.titulo-historico + table`. Uma linha
    entre os dois desliga a edicao de lancamento sem quebrar teste de rota."""
    html = Path("app/templates/odontograma.html").read_text(encoding="utf-8")
    achado = re.search(
        r'titulo-historico">[^<]*</h2>\s*<table>', html, re.S
    )
    assert achado, "titulo e tabela do historico precisam ser irmaos imediatos"
