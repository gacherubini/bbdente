"""A regua do numero para WhatsApp.

Fica no mesmo modulo do telefone do cadastro porque **regua de telefone e uma so
neste sistema** — e vale igual para o numero da ficha e para o `telefone_avulso`
digitado na agenda.

O WhatsApp e mais exigente que a tela: precisa de 55 + DDD + 8 ou 9 digitos. O
que esta funcao NAO faz e o que importa: nao acrescenta o nono digito, nao chuta
DDD e nao corta numero comprido. Inventar digito para fazer caber e exatamente o
que `formatar()` se recusa a fazer desde o primeiro dia — a diferenca e que aqui
o preco de errar e mandar mensagem de paciente para o telefone de um estranho.
"""

import pytest

from app.pacientes.telefone import numero_para_whatsapp


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("51999998888", "5551999998888"),          # celular com DDD
        ("(51) 99999-8888", "5551999998888"),      # ja formatado
        ("5133133087", "555133133087"),            # 10 digitos: NAO vira 11
        ("11987654321", "5511987654321"),
    ],
)
def test_numero_bom_ganha_o_55(entrada, esperado):
    assert numero_para_whatsapp(entrada) == esperado


def test_numero_de_dez_digitos_nao_ganha_o_nono():
    """Pode ser fixo (que nao tem WhatsApp) ou celular anterior ao nono digito.
    Somar um '9' e inventar digito."""
    assert numero_para_whatsapp("5133133087") == "555133133087"


@pytest.mark.parametrize(
    "entrada",
    [
        "36535051",                # 8 digitos, sem DDD — nao se chuta o 51
        "6531900",                 # 7 digitos, Porto Alegre antiga
        "32484554844055454",       # dois numeros colados
        "01999998888",             # DDD que nao existe
        "00999998888",
        "",
        None,
        "sem numero",
    ],
)
def test_numero_imprestavel_devolve_nada(entrada):
    assert numero_para_whatsapp(entrada) is None


def test_numero_que_ja_vem_com_55_nao_ganha_outro():
    assert numero_para_whatsapp("5551999998888") == "5551999998888"


def test_o_55_so_e_reconhecido_quando_sobra_numero_valido():
    """'5551' sozinho e '55' + '51' e mais nada — nao e telefone."""
    assert numero_para_whatsapp("5551") is None
