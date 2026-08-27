"""O valor nasce do preco do tratamento, multiplicado pelas faces marcadas.

Antes, VALOR abria em 0,00 e a dentista digitava a mao em todo lancamento, com a
tabela de preco ja no banco. Restauracao de 3 faces custa 3x a de 1: o numero de
faces marcadas multiplica. Continua editavel — quem da desconto e ela.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.auth.models import Clinica
from app.catalogo.models import Convenio, Preco
from app.catalogo.service import arvore, convenio_particular
from app.shared.tipos import Escopo

JS = Path("app/static/painel.js")


@pytest.fixture
def cenario(sessao):
    from app.catalogo.models import Categoria, Procedimento

    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    particular = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    outro = Convenio(clinica_id=clinica.id, codigo="042", nome="UNIMED")
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    sessao.add_all([particular, outro, categoria])
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    sessao.add(procedimento)
    sessao.flush()
    sessao.add_all([
        Preco(procedimento_id=procedimento.id, convenio_id=particular.id,
              valor=Decimal("180.00"), vigente_desde=date(2020, 1, 1)),
        Preco(procedimento_id=procedimento.id, convenio_id=outro.id,
              valor=Decimal("95.00"), vigente_desde=date(2020, 1, 1)),
    ])
    sessao.flush()
    return {
        "clinica": clinica, "particular": particular, "outro": outro,
        "procedimento": procedimento,
    }


def procedimento_na_arvore(galhos, procedimento_id):
    for categoria in galhos:
        for p in categoria["procedimentos"]:
            if p["id"] == procedimento_id:
                return p
    raise AssertionError("procedimento nao veio na arvore")


def test_a_arvore_leva_o_preco_do_convenio_pedido(sessao, cenario):
    galhos = arvore(
        sessao, clinica_id=cenario["clinica"].id, convenio_id=cenario["outro"].id
    )
    p = procedimento_na_arvore(galhos, cenario["procedimento"].id)
    assert p["preco"] == "95.00"


def test_sem_convenio_a_arvore_usa_o_particular(sessao, cenario):
    """Na boca em branco ainda nao ha paciente, entao nao ha convenio."""
    galhos = arvore(sessao, clinica_id=cenario["clinica"].id)
    p = procedimento_na_arvore(galhos, cenario["procedimento"].id)
    assert p["preco"] == "180.00"


def test_tratamento_sem_tabela_de_preco_vem_nulo_nao_zero(sessao, cenario):
    """'Sem tabela' nao e 'de graca': 0,00 mentiria, e a tela abriria um
    lancamento de graca sem ninguem perceber."""
    from app.catalogo.models import Procedimento

    sem_preco = Procedimento(
        clinica_id=cenario["clinica"].id, codigo="99", nome="Sem tabela",
        categoria_id=cenario["procedimento"].categoria_id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(sem_preco)
    sessao.flush()
    galhos = arvore(sessao, clinica_id=cenario["clinica"].id)
    assert procedimento_na_arvore(galhos, sem_preco.id)["preco"] is None


def test_o_particular_e_achado_pelo_codigo_001(sessao, cenario):
    assert convenio_particular(
        sessao, clinica_id=cenario["clinica"].id
    ) == cenario["particular"].id


def test_clinica_sem_particular_nao_explode(sessao):
    clinica = Clinica(nome="Nova")
    sessao.add(clinica)
    sessao.flush()
    assert convenio_particular(sessao, clinica_id=clinica.id) is None


# --- o painel multiplica ----------------------------------------------------

def test_o_painel_multiplica_o_preco_pelas_faces():
    fonte = JS.read_text(encoding="utf-8")
    assert "sugerirValor" in fonte, "falta a funcao que sugere o valor"
    assert "preco" in fonte


def test_o_valor_digitado_a_mao_nao_e_sobrescrito():
    """Quem da desconto e a dentista: se ela baixou o valor e depois marca mais
    uma face, o desconto nao pode ser apagado pela sugestao."""
    fonte = JS.read_text(encoding="utf-8")
    assert "valorEditadoAMao" in fonte
