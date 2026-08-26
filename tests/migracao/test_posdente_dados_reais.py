"""Roda o decodificador contra os 44.812 lancamentos reais.

E o teste mais valioso do modulo: os numeros abaixo sao os mesmos da conferencia
bloqueante da spec. Se algum mudar, a migracao inteira esta errada.
"""

import os
import sqlite3
from collections import Counter

import pytest

from app.shared.tipos import Escopo, Regiao
from migracao.posdente import decodificar

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO),
    reason=f"extrato nao disponivel em {EXTRATO} (nunca e versionado — dado de paciente)",
)


@pytest.fixture(scope="module")
def contagens():
    conexao = sqlite3.connect(EXTRATO)
    escopos: Counter = Counter()
    regioes: Counter = Counter()
    motivos: Counter = Counter()
    for numdente, posdente in conexao.execute("SELECT NUMDENTE, POSDENTE FROM ARQDENTE"):
        alvo = decodificar(numdente, posdente)
        escopos[alvo.escopo] += 1
        if alvo.regiao is not None:
            regioes[alvo.regiao] += 1
        for motivo in alvo.motivos:
            motivos[motivo] += 1
    conexao.close()
    return escopos, regioes, motivos


def test_totais_por_escopo(contagens):
    escopos, _, _ = contagens
    assert sum(escopos.values()) == 44_812
    assert escopos[Escopo.REGIOES] == 29_350
    assert escopos[Escopo.BOCA] == 7_638
    assert escopos[Escopo.DENTE] == 7_824


def test_uma_regiao_por_lancamento_com_escopo_regioes(contagens):
    escopos, regioes, _ = contagens
    assert sum(regioes.values()) == escopos[Escopo.REGIOES] == 29_350


def test_apenas_um_registro_e_perdido(contagens):
    _, _, motivos = contagens
    assert motivos["posdente_ilegivel"] == 1
    assert motivos["posdente_fora_da_grade"] == 0
    assert motivos["boca_com_dente_preenchido"] == 39


def test_distribuicao_bate_com_a_anatomia(contagens):
    """A face de mastigacao e de longe a mais tratada; as duas proximais vem
    empatadas entre si, como esperado de restauracoes classe II e III."""
    _, regioes, _ = contagens
    total = sum(regioes.values())
    assert regioes[Regiao.OCLUSAL] / total == pytest.approx(0.303, abs=0.005)
    assert regioes[Regiao.MESIAL] / total == pytest.approx(0.164, abs=0.005)
    assert regioes[Regiao.DISTAL] / total == pytest.approx(0.160, abs=0.005)
    assert regioes[Regiao.VESTIBULAR] / total == pytest.approx(0.103, abs=0.005)
    assert regioes[Regiao.LINGUAL] / total == pytest.approx(0.060, abs=0.005)
    # as duas proximais sao praticamente simetricas — se uma disparar, o
    # espelhamento mesial/distal esta invertido em algum quadrante
    assert abs(regioes[Regiao.MESIAL] - regioes[Regiao.DISTAL]) < 300
