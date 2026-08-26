from datetime import date

import pytest

from migracao.texto import data_legada, limpar


@pytest.mark.parametrize(
    ("entrada", "saida"),
    [("  Fulana  ", "Fulana"), ("", None), ("   ", None), (None, None), ("X", "X")],
)
def test_limpar_tira_espaco_e_transforma_vazio_em_nulo(entrada, saida):
    assert limpar(entrada) == saida


def test_data_valida_passa_sem_motivo():
    assert data_legada("1962-04-12") == (date(1962, 4, 12), None)


def test_data_vazia_e_nula_sem_motivo():
    """Faltar data de nascimento nao e erro de digitacao: 1.574 pacientes nao tem."""
    assert data_legada("") == (None, None)
    assert data_legada(None) == (None, None)


@pytest.mark.parametrize("valor", ["1194-05-01", "2080-06-09", "9200-01-01"])
def test_data_impossivel_e_preservada_e_marcada(valor):
    """Erros de digitacao de 30 anos atras. O dado dela nao e apagado nem 'consertado'."""
    lida, motivo = data_legada(valor)
    assert lida is not None
    assert motivo == "data_suspeita"


def test_data_ilegivel_vira_nula_e_marcada():
    assert data_legada("nao-e-data") == (None, "data_ilegivel")
