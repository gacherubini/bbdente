import pytest

from app.pacientes.telefone import formatar, parecer_incompleto, separar


def test_campo_com_varios_numeros_e_quebrado():
    """No Dentalis vem tudo num campo so, separado por barra."""
    assert separar("32671690/99684152 /84257133") == ["32671690", "99684152", "84257133"]


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("51999990001", ["51999990001"]),
        ("  3269-3124  ", ["32693124"]),
        ("", []),
        (None, []),
        ("/", []),
        ("3248-5030 / 9968-4152", ["32485030", "99684152"]),
    ],
)
def test_separar_normaliza_e_descarta_vazio(bruto, esperado):
    assert separar(bruto) == esperado


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [
        ("51999990001", "(51) 99999-0001"),
        ("5199990002", "(51) 9999-0002"),
        ("999990001", "99999-0001"),
        ("99990002", "9999-0002"),
        ("2490143", "2490143"),  # 7 digitos: nao reconhece, devolve cru
    ],
)
def test_formatar(numero, esperado):
    assert formatar(numero) == esperado


@pytest.mark.parametrize(
    ("numero", "incompleto"),
    [("2490143", True), ("32693124", False), ("51999990001", False), ("123", True)],
)
def test_parecer_incompleto(numero, incompleto):
    """Numero real do banco dela: '2490-143', com um digito a menos."""
    assert parecer_incompleto(numero) is incompleto
