"""O CSS e o JavaScript precisam trocar de endereco quando mudam.

Sem isso o navegador guarda os arquivos antigos e a tela aparece quebrada depois
de cada deploy, ate alguem saber que precisa forcar a recarga. Numa clinica
ninguem sabe — aconteceu em producao em 26/08/2026, e este arquivo existe por
causa disso.
"""

import re
from pathlib import Path

import pytest

from app.templates import ESTATICOS, estatico

TEMPLATES = Path("app/templates")


def test_o_endereco_leva_uma_marca_de_versao():
    assert re.fullmatch(r"/static/bddente\.css\?v=\d+", estatico("bddente.css"))


def test_arquivos_diferentes_tem_marcas_diferentes():
    assert estatico("bddente.css") != estatico("painel.js")


def test_arquivo_que_nao_existe_nao_derruba_a_tela():
    """Arquivo ausente e problema de deploy, nao motivo para a tela morrer."""
    assert estatico("nao-existe.css") == "/static/nao-existe.css"


def test_a_marca_muda_quando_o_arquivo_muda(tmp_path, monkeypatch):
    alvo = ESTATICOS / "bddente.css"
    antes = estatico.__wrapped__("bddente.css")
    conteudo = alvo.read_bytes()
    try:
        alvo.write_bytes(conteudo + b"\n/* teste */\n")
        assert estatico.__wrapped__("bddente.css") != antes
    finally:
        alvo.write_bytes(conteudo)


@pytest.mark.parametrize(
    "template", sorted(p.name for p in TEMPLATES.glob("*.html"))
)
def test_nenhum_template_aponta_para_static_sem_versao(template):
    html = (TEMPLATES / template).read_text(encoding="utf-8")
    cru = re.findall(r'(?:href|src)="/static/[^"]+"', html)
    assert cru == [], f"{template} usa /static direto: {cru}"
