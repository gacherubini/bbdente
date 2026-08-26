import pytest

from app.pacientes.telefone import (
    formatar,
    parecer_incompleto,
    parecer_longo,
    separar,
)


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


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        # Casos reais do banco dela: os numeros vinham separados por espaco ou por
        # uma palavra ("OU", "TIA:"), nunca por barra. Sem tratar isso, os digitos
        # de tres telefones viravam um numero de 32 digitos.
        (
            "32680751 OU 32680729 OU 99031569 OU 99010095",
            ["32680751", "32680729", "99031569", "99010095"],
        ),
        (
            "[0.54]223237649 TIA:(051)2238110-PAI:(051)4693706",
            ["054223237649", "0512238110", "0514693706"],
        ),
        ("COM.32498102-RES.32490129", ["32498102", "32490129"]),
        # Hifen sem espaco continua sendo formatacao, nao separador.
        ("3269-3124", ["32693124"]),
    ],
)
def test_espaco_e_palavra_tambem_separam_numeros(bruto, esperado):
    assert separar(bruto) == esperado


@pytest.mark.parametrize(
    ("numero", "longo"),
    [
        ("51999990001", False),  # 11 digitos: celular com DDD, o maior valido
        ("3248455484055454", True),  # dois numeros colados por hifen no legado
        ("32693124", False),
    ],
)
def test_parecer_longo(numero, longo):
    """Numero com mais digitos que um celular com DDD e dois numeros colados.
    Marca, nao corta: cortar escolheria qual metade jogar fora."""
    assert parecer_longo(numero) is longo


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        (" 51/97546623", ["5197546623"]),
        ("(55) 33133087/99115592", ["5533133087", "99115592"]),
        ("051 6531900", ["0516531900"]),
        ("014 48 96022746", ["014", "4896022746"]),  # 014 e operadora, 48 e o DDD
        ("2218799 ramal 268", ["2218799", "268"]),  # ramal nao vira DDD
    ],
)
def test_ddd_solto_volta_para_o_numero(bruto, esperado):
    assert separar(bruto) == esperado
