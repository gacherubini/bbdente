"""Formatacao de numero para leitura em portugues.

Fica em `shared` porque tanto as telas quanto o PDF do prontuario precisam da
mesma regua: R$ 1.234,56 escrito de dois jeitos no mesmo sistema e erro de
leitura esperando acontecer.
"""

from decimal import ROUND_HALF_UP, Decimal


def moeda(valor) -> str:
    """1000 -> '1.000,00'. Sem o 'R$', que fica no texto de quem chama.

    Nao usamos `locale` porque ele depende do que esta instalado no servidor —
    no Fly, nada garante que pt_BR exista.
    """
    if valor is None:
        return "—"
    # ROUND_HALF_UP explicito: o padrao do Decimal e o arredondamento bancario,
    # que joga 10,005 para 10,00. Quem confere a mao espera 10,01.
    numero = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inteiro, centavos = f"{abs(numero):.2f}".split(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    sinal = "-" if numero < 0 else ""
    return f"{sinal}{'.'.join(grupos)},{centavos}"
