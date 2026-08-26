import pytest

from app.shared.dentes import (
    TODOS_FDI,
    Parede,
    arcada_superior,
    canais_do_dente,
    canais_em_ordem_de_tela,
    numero_de_raizes,
    paredes_do_dente,
)
from app.shared.tipos import REGIOES_COROA, Regiao


def test_toda_parede_de_todo_dente_e_uma_regiao_de_coroa_distinta():
    for fdi in TODOS_FDI:
        paredes = paredes_do_dente(fdi)
        assert set(paredes) == set(Parede)
        assert set(paredes.values()) == REGIOES_COROA - {Regiao.OCLUSAL}


@pytest.mark.parametrize("fdi", [18, 11, 21, 28])
def test_na_arcada_de_cima_a_bochecha_fica_em_cima(fdi):
    """A raiz aponta para cima nos dentes superiores, e a face da bochecha
    (vestibular) acompanha — e como a tela do Dentalis sempre desenhou."""
    assert arcada_superior(fdi) is True
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.CIMA] is Regiao.VESTIBULAR
    assert paredes[Parede.BAIXO] is Regiao.LINGUAL


@pytest.mark.parametrize("fdi", [48, 41, 31, 38])
def test_na_arcada_de_baixo_tudo_inverte(fdi):
    assert arcada_superior(fdi) is False
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.CIMA] is Regiao.LINGUAL
    assert paredes[Parede.BAIXO] is Regiao.VESTIBULAR


@pytest.mark.parametrize("fdi", [18, 16, 11, 48, 46, 41])
def test_nos_quadrantes_1_e_4_a_linha_media_fica_a_direita(fdi):
    """Sao os dentes desenhados na METADE ESQUERDA da tela; andar para a direita
    aproxima da linha media, e aproximar da linha media e mesial."""
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.DIREITA] is Regiao.MESIAL
    assert paredes[Parede.ESQUERDA] is Regiao.DISTAL


@pytest.mark.parametrize("fdi", [21, 26, 28, 31, 36, 38])
def test_nos_quadrantes_2_e_3_o_espelho_inverte(fdi):
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.ESQUERDA] is Regiao.MESIAL
    assert paredes[Parede.DIREITA] is Regiao.DISTAL


def test_canais_na_ordem_da_tela_tem_o_mesmo_conjunto_da_anatomia():
    for fdi in TODOS_FDI:
        tela = canais_em_ordem_de_tela(fdi)
        assert len(tela) == numero_de_raizes(fdi)
        assert set(tela) == set(canais_do_dente(fdi))


def test_o_canal_mais_perto_da_linha_media_e_o_mesial():
    # dente 16 (quadrante 1, metade esquerda da tela): mesial e o da direita
    assert canais_em_ordem_de_tela(16)[-1] is Regiao.CANAL_MESIAL
    assert canais_em_ordem_de_tela(16)[0] is Regiao.CANAL_DISTAL
    # dente 26 (quadrante 2, metade direita): espelhado
    assert canais_em_ordem_de_tela(26)[0] is Regiao.CANAL_MESIAL
    assert canais_em_ordem_de_tela(26)[-1] is Regiao.CANAL_DISTAL


def test_dente_de_uma_raiz_so_tem_o_canal_central():
    assert canais_em_ordem_de_tela(11) == (Regiao.CANAL_CENTRAL,)
    assert canais_em_ordem_de_tela(44) == (Regiao.CANAL_CENTRAL,)


def test_dente_de_duas_raizes_nao_tem_canal_central():
    assert Regiao.CANAL_CENTRAL not in canais_em_ordem_de_tela(46)
    assert len(canais_em_ordem_de_tela(46)) == 2


def test_a_geometria_concorda_com_o_decodificador_do_legado():
    """Prova cruzada: a parede que o desenho chama de mesial e a mesma que o
    POSDENTE do Dentalis apontava como mesial. Se estas duas fontes divergirem,
    a tela vai pintar o historico no lugar errado."""
    from app.shared.dentes import indice_legado_de_fdi
    from migracao.posdente import centro_da_celula, decodificar

    for fdi in TODOS_FDI:
        indice = indice_legado_de_fdi(fdi)
        xc, yc = centro_da_celula(indice)
        paredes = paredes_do_dente(fdi)
        # dx +1 na grade legada = parede da direita no desenho
        assert decodificar(str(indice), f"{yc:>2}{xc + 1:>2}").regiao is paredes[Parede.DIREITA]
        assert decodificar(str(indice), f"{yc:>2}{xc - 1:>2}").regiao is paredes[Parede.ESQUERDA]
