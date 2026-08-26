import pytest

from app.shared.tipos import Escopo, Regiao
from migracao.posdente import Alvo, centro_da_celula, decodificar

# --- geometria da grade --------------------------------------------------------


@pytest.mark.parametrize(
    ("indice", "centro"),
    [
        (1, (2, 9)),     # primeira celula da fileira superior
        (2, (7, 9)),     # celulas espacadas de 5 em 5 colunas
        (16, (77, 9)),   # ultima da superior
        (17, (2, 14)),   # a inferior recomeca em x=2, linha 14
        (32, (77, 14)),
    ],
)
def test_centro_da_celula(indice, centro):
    assert centro_da_celula(indice) == centro


# --- sentinelas ----------------------------------------------------------------


def test_8888_e_boca_toda():
    alvo = decodificar("00", "8888")
    assert alvo == Alvo(Escopo.BOCA, None, None, ())


def test_8888_com_dente_preenchido_entra_como_boca_mas_fica_marcado():
    """39 registros reais tem essa contradicao. Importa como BOCA e marca."""
    alvo = decodificar("16", "8888")
    assert alvo.escopo is Escopo.BOCA
    assert alvo.fdi is None
    assert "boca_com_dente_preenchido" in alvo.motivos


def test_9999_e_o_dente_inteiro():
    alvo = decodificar("1", "9999")
    assert alvo == Alvo(Escopo.DENTE, 18, None, ())


# --- as duas metades sao alinhadas a direita ------------------------------------


def test_posdente_com_espacos_e_lido_como_duas_metades_de_2_chars():
    """'9 45' e Y=9, X=45 — NAO 945. Fazer strip na string inteira quebra 17.791
    registros. Este teste existe para impedir exatamente esse bug."""
    indice = 10  # dente 22, centro x=47, y=9
    assert centro_da_celula(indice) == (47, 9)
    assert decodificar(str(indice), " 947").regiao is Regiao.OCLUSAL


# --- as 8 regioes, num dente superior direito (indice 3 = dente 16) -------------
# centro da celula: x=12, y=9. Superior, entao ndy = -(y - 9).


@pytest.mark.parametrize(
    ("y", "x", "regiao"),
    [
        (10, 12, Regiao.LINGUAL),        # ndy=-1, dx=0
        (9, 13, Regiao.MESIAL),          # ndy= 0, dx=+1  (quadrante 1: mesial a direita)
        (9, 11, Regiao.DISTAL),          # ndy= 0, dx=-1
        (9, 12, Regiao.OCLUSAL),         # ndy= 0, dx= 0
        (8, 12, Regiao.VESTIBULAR),      # ndy=+1, dx=0
        (7, 12, Regiao.CANAL_CENTRAL),   # ndy=+2, dx=0   (linha da raiz)
        (6, 14, Regiao.CANAL_MESIAL),    # ndy=+3, dx=+2
        (6, 10, Regiao.CANAL_DISTAL),    # ndy=+3, dx=-2
    ],
)
def test_as_oito_regioes_num_dente_superior_direito(y, x, regiao):
    alvo = decodificar("3", f"{y:>2}{x:>2}")
    assert alvo.escopo is Escopo.REGIOES
    assert alvo.fdi == 16
    assert alvo.regiao is regiao


# --- espelhamento: o teste que impede inverter 44.812 registros -----------------


def test_mesial_e_distal_invertem_do_outro_lado_da_linha_media():
    """Nos quadrantes 1 e 4 a linha media fica a DIREITA na tela, entao mesial e dx+1.
    Nos quadrantes 2 e 3 ela fica a ESQUERDA, entao mesial e dx-1."""
    # indice 3 = dente 16 (quadrante 1), centro x=12
    assert decodificar("3", " 913").regiao is Regiao.MESIAL
    assert decodificar("3", " 911").regiao is Regiao.DISTAL

    # indice 14 = dente 26 (quadrante 2), centro x=67 — espelhado
    assert centro_da_celula(14) == (67, 9)
    assert decodificar("14", " 966").regiao is Regiao.MESIAL
    assert decodificar("14", " 968").regiao is Regiao.DISTAL


@pytest.mark.parametrize(
    ("indice", "fdi", "quad"), [(3, 16, 1), (14, 26, 2), (30, 36, 3), (19, 46, 4)]
)
def test_espelhamento_nos_quatro_quadrantes(indice, fdi, quad):
    from app.shared.dentes import quadrante

    assert quadrante(fdi) == quad
    xc, yc = centro_da_celula(indice)
    superior = indice <= 16
    # ndy = 0 nas duas fileiras significa y == yc
    mesial_a_direita = quad in (1, 4)
    dx_mesial = 1 if mesial_a_direita else -1

    alvo = decodificar(str(indice), f"{yc:>2}{xc + dx_mesial:>2}")
    assert alvo.fdi == fdi
    assert alvo.regiao is Regiao.MESIAL

    alvo = decodificar(str(indice), f"{yc:>2}{xc - dx_mesial:>2}")
    assert alvo.regiao is Regiao.DISTAL
    assert superior == (indice <= 16)  # sanidade do parametro


def test_inferior_tem_a_raiz_para_baixo():
    """Indice 19 = dente 46, centro (12, 14). Na fileira inferior a raiz aponta para
    baixo, entao a linha dos canais tem y MAIOR que o centro, nao menor."""
    assert centro_da_celula(19) == (12, 14)
    assert decodificar("19", "1712").regiao is Regiao.CANAL_CENTRAL   # ndy=+3
    assert decodificar("19", "1312").regiao is Regiao.LINGUAL         # ndy=-1
    assert decodificar("19", "1512").regiao is Regiao.VESTIBULAR      # ndy=+1


# --- dado ruim -----------------------------------------------------------------


def test_posdente_corrompido_vira_dente_inteiro_marcado():
    """O unico registro real fora da grade tem POSDENTE '13-3'."""
    alvo = decodificar("5", "13-3")
    assert alvo.escopo is Escopo.DENTE
    assert alvo.fdi == 14
    assert "posdente_ilegivel" in alvo.motivos


def test_coordenada_valida_mas_fora_das_posicoes_conhecidas_e_marcada():
    alvo = decodificar("3", "0199")
    assert alvo.escopo is Escopo.DENTE
    assert "posdente_fora_da_grade" in alvo.motivos


def test_indice_de_dente_invalido_vira_boca_marcada():
    alvo = decodificar("99", "9999")
    assert alvo.escopo is Escopo.BOCA
    assert "indice_de_dente_invalido" in alvo.motivos


def test_dente_zerado_sem_sentinela_de_boca_e_marcado():
    alvo = decodificar("0", "9999")
    assert alvo.escopo is Escopo.BOCA
    assert "dente_zerado_sem_sentinela" in alvo.motivos


def test_alvo_e_imutavel():
    alvo = decodificar("3", " 912")
    with pytest.raises(Exception):  # noqa: B017
        alvo.regiao = Regiao.MESIAL  # type: ignore[misc]
