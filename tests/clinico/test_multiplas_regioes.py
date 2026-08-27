"""Clicar em varias faces do mesmo dente soma, em vez de trocar.

O painel sempre teve caixas de marcacao para varias regioes, mas o gesto que a
dentista usa e clicar no desenho — e clicar substituia a selecao inteira. Na
pratica dava para marcar uma face so, e a multiplicacao de preco por face
(restauracao de 3 faces custa 3x) nunca acontecia sem alguem descobrir as
caixinhas.

Estes testes leem a fonte do JavaScript. Nao ha runner de JS neste projeto, e a
alternativa seria nao testar — o mesmo caminho de `test_valor_sugerido.py`.
"""

from pathlib import Path

JS = Path("app/static/painel.js")
PAINEL = Path("app/templates/_painel_lancamento.html")


def test_clicar_no_mesmo_dente_alterna_a_face_em_vez_de_trocar():
    fonte = JS.read_text(encoding="utf-8")
    assert "mesmoDente" in fonte
    assert "alternarRegiao" in fonte


def test_clicar_em_outro_dente_recomeca_a_selecao():
    """Selecao pertence a um dente. Levar as faces do 36 para o 37 lancaria
    tratamento em face que ninguem mandou."""
    fonte = JS.read_text(encoding="utf-8")
    assert "marcarSomente([clique.regiao])" in fonte


def test_a_selecao_feita_a_mao_sobrevive_a_troca_de_tratamento():
    """Marcou tres faces e so entao escolheu o tratamento: a sugestao do
    procedimento nao pode apagar o que ela montou."""
    fonte = JS.read_text(encoding="utf-8")
    assert "regioesMarcadas().length > 1" in fonte


def test_a_tela_conta_que_da_para_somar_faces():
    """Gesto que ninguem descobre e gesto que nao existe."""
    html = PAINEL.read_text(encoding="utf-8")
    assert "mais de uma face" in html
