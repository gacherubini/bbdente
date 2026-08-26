"""Dinheiro escrito como se le em portugues.

O Python formata no padrao americano; o consultorio le em portugues. Sem isto,
R$ 1.234,56 aparece como 1234.56 — e a virgula some justamente onde o valor
importa.
"""

from decimal import Decimal

import pytest

from app.shared.formato import moeda


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (0, "0,00"),
        (5, "5,00"),
        (Decimal("180.00"), "180,00"),
        (Decimal("1000"), "1.000,00"),
        (Decimal("1234.56"), "1.234,56"),
        (Decimal("1000000"), "1.000.000,00"),
        (Decimal("3430481.53"), "3.430.481,53"),
        (Decimal("-50.5"), "-50,50"),
    ],
)
def test_escreve_o_numero_em_portugues(valor, esperado):
    assert moeda(valor) == esperado


def test_arredonda_para_dois_centavos():
    assert moeda(Decimal("10.005")) == "10,01"
    assert moeda(Decimal("10.004")) == "10,00"


def test_sem_valor_vira_travessao():
    """'Nao ha valor' e diferente de 'zero': R$ 0,00 seria uma afirmacao."""
    assert moeda(None) == "—"


def test_aceita_float_sem_estragar_o_centavo():
    """A aplicacao usa Decimal, mas o PDF e os testes as vezes passam float."""
    assert moeda(1234.5) == "1.234,50"
