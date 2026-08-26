import pytest

from app.shared.dentes import (
    FDI_INFERIOR,
    FDI_SUPERIOR,
    TODOS_FDI,
    canais_do_dente,
    e_anterior,
    e_fdi_valido,
    fdi_de_indice_legado,
    indice_legado_de_fdi,
    numero_de_raizes,
    quadrante,
    rotulo_regiao,
)
from app.shared.tipos import REGIOES_RAIZ, Regiao

# --- conversao indice legado 1..32 <-> FDI -------------------------------------

@pytest.mark.parametrize(
    ("indice", "fdi"),
    [
        (1, 18), (8, 11),    # superior direito: da ponta ate a linha media
        (9, 21), (16, 28),   # superior esquerdo
        (17, 48), (24, 41),  # inferior direito
        (25, 31), (32, 38),  # inferior esquerdo
    ],
)
def test_indice_legado_vira_o_fdi_certo(indice, fdi):
    assert fdi_de_indice_legado(indice) == fdi


def test_conversao_ida_e_volta_para_os_32():
    for indice in range(1, 33):
        assert indice_legado_de_fdi(fdi_de_indice_legado(indice)) == indice


def test_os_32_sao_distintos_e_todos_fdi_valido():
    assert len(TODOS_FDI) == 32
    assert len(set(TODOS_FDI)) == 32
    assert all(e_fdi_valido(f) for f in TODOS_FDI)
    assert FDI_SUPERIOR + FDI_INFERIOR == TODOS_FDI


@pytest.mark.parametrize("indice", [0, -1, 33, 100])
def test_indice_fora_de_1_a_32_e_erro(indice):
    with pytest.raises(ValueError):
        fdi_de_indice_legado(indice)


@pytest.mark.parametrize("fdi", [0, 10, 19, 29, 39, 49, 50, 11.5])
def test_numero_que_nao_e_fdi_e_rejeitado(fdi):
    assert not e_fdi_valido(fdi)
    with pytest.raises(ValueError):
        indice_legado_de_fdi(fdi)


# --- quadrante e posicao -------------------------------------------------------

@pytest.mark.parametrize(
    ("fdi", "q"), [(18, 1), (11, 1), (21, 2), (28, 2), (31, 3), (38, 3), (41, 4), (48, 4)]
)
def test_quadrante_e_a_dezena(fdi, q):
    assert quadrante(fdi) == q


def test_anteriores_sao_as_posicoes_1_a_3_dos_quatro_quadrantes():
    anteriores = {f for f in TODOS_FDI if e_anterior(f)}
    assert anteriores == {11, 12, 13, 21, 22, 23, 31, 32, 33, 41, 42, 43}


# --- raizes e canais -----------------------------------------------------------

@pytest.mark.parametrize(
    ("fdi", "n"),
    [
        (16, 3), (17, 3), (18, 3), (26, 3),  # molares superiores: 3 raizes
        (36, 2), (37, 2), (46, 2), (48, 2),  # molares inferiores: 2
        (14, 2), (24, 2),                    # primeiro pre-molar superior: 2
        (15, 1), (25, 1), (34, 1), (44, 1),  # demais pre-molares: 1
        (11, 1), (13, 1), (31, 1), (43, 1),  # anteriores: 1
    ],
)
def test_numero_de_raizes(fdi, n):
    assert numero_de_raizes(fdi) == n


def test_canais_acompanham_o_numero_de_raizes():
    assert canais_do_dente(11) == (Regiao.CANAL_CENTRAL,)
    assert canais_do_dente(14) == (Regiao.CANAL_MESIAL, Regiao.CANAL_DISTAL)
    assert canais_do_dente(16) == (
        Regiao.CANAL_MESIAL,
        Regiao.CANAL_CENTRAL,
        Regiao.CANAL_DISTAL,
    )
    for fdi in TODOS_FDI:
        canais = canais_do_dente(fdi)
        assert len(canais) == numero_de_raizes(fdi)
        assert set(canais) <= REGIOES_RAIZ


# --- rotulos de tela -----------------------------------------------------------

def test_oclusal_vira_incisal_so_nos_anteriores():
    assert rotulo_regiao(Regiao.OCLUSAL, 11) == "Incisal"
    assert rotulo_regiao(Regiao.OCLUSAL, 43) == "Incisal"
    assert rotulo_regiao(Regiao.OCLUSAL, 16) == "Oclusal"
    assert rotulo_regiao(Regiao.OCLUSAL, 24) == "Oclusal"


def test_demais_rotulos_nao_dependem_do_dente():
    assert rotulo_regiao(Regiao.LINGUAL, 11) == rotulo_regiao(Regiao.LINGUAL, 16)
    assert rotulo_regiao(Regiao.VESTIBULAR, 16) == "Vestibular"
    assert rotulo_regiao(Regiao.CANAL_MESIAL, 16) == "Canal mesial"


def test_todo_par_regiao_dente_tem_rotulo_nao_vazio():
    for fdi in TODOS_FDI:
        for regiao in Regiao:
            assert rotulo_regiao(regiao, fdi).strip()
