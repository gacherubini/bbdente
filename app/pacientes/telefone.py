"""Telefones do Dentalis vinham todos num campo unico de texto livre, por exemplo
'32671690/99684152 /84257133'. Aqui separamos e formatamos — sempre guardando o
campo cru em PacienteTelefone.numero_original, caso a separacao erre."""

import re

_SEPARADORES = re.compile(r"[/;,]")
_NAO_DIGITO = re.compile(r"\D")

TAMANHO_MINIMO = 8  # fixo local sem DDD


def separar(bruto: str | None) -> list[str]:
    """Quebra o campo unico em numeros individuais, so com digitos."""
    if not bruto:
        return []
    numeros = []
    for pedaco in _SEPARADORES.split(bruto):
        digitos = _NAO_DIGITO.sub("", pedaco)
        if digitos:
            numeros.append(digitos)
    return numeros


def formatar(numero: str) -> str:
    """Formata para leitura. Devolve o numero cru quando nao reconhece o formato —
    nunca inventa digito para fazer caber."""
    match len(numero):
        case 11:
            return f"({numero[:2]}) {numero[2:7]}-{numero[7:]}"
        case 10:
            return f"({numero[:2]}) {numero[2:6]}-{numero[6:]}"
        case 9:
            return f"{numero[:5]}-{numero[5:]}"
        case 8:
            return f"{numero[:4]}-{numero[4:]}"
        case _:
            return numero


def parecer_incompleto(numero: str) -> bool:
    """Curto demais para ser um telefone valido. A tela marca; nao corrige."""
    return len(numero) < TAMANHO_MINIMO
