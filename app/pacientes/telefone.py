"""Telefones do Dentalis vinham todos num campo unico de texto livre, por exemplo
'32671690/99684152 /84257133'. Aqui separamos e formatamos — sempre guardando o
campo cru em PacienteTelefone.numero_original, caso a separacao erre."""

import re

# Separam numeros: barra, ponto-e-virgula, virgula, espaco em branco e qualquer
# palavra ("OU", "TIA:", "CASA"). Hifen e parenteses NAO separam — sao formatacao
# dentro do numero ('3269-3124', '(051)2238110').
_SEPARADORES = re.compile(r"[/;,]|\s+|[^\W\d_]+")
_NAO_DIGITO = re.compile(r"\D")

TAMANHO_MINIMO = 8  # fixo local sem DDD
TAMANHO_MAXIMO = 11  # celular com DDD; nada legitimo passa disso


def separar(bruto: str | None) -> list[str]:
    """Quebra o campo unico em numeros individuais, so com digitos.

    O que sobrar sem sentido (ramal solto, pedaco de anotacao) sai como esta e a
    migracao marca o cadastro — o campo cru fica em numero_original.
    """
    if not bruto:
        return []
    numeros = []
    for pedaco in _SEPARADORES.split(bruto):
        digitos = _NAO_DIGITO.sub("", pedaco)
        if digitos:
            numeros.append(digitos)
    return _juntar_ddd(numeros)


def _juntar_ddd(numeros: list[str]) -> list[str]:
    """'51 36535051' e '(55) 33133087' sao um numero com DDD, nao dois numeros.

    So junta 2 ou 3 digitos seguidos de um numero completo de 7 a 9 — 7 porque os
    numeros antigos de Porto Alegre tinham 7 digitos ('051 6531900'). Ramal depois
    de um numero inteiro ('2218799 ramal 268') nao se encaixa e continua separado,
    para aparecer marcado em vez de virar um numero errado que parece certo.
    """
    juntos: list[str] = []
    i = 0
    while i < len(numeros):
        atual = numeros[i]
        seguinte = numeros[i + 1] if i + 1 < len(numeros) else None
        if 2 <= len(atual) <= 3 and seguinte is not None and 7 <= len(seguinte) <= 9:
            juntos.append(atual + seguinte)
            i += 2
        else:
            juntos.append(atual)
            i += 1
    return juntos


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


def parecer_longo(numero: str) -> bool:
    """Digitos demais para um numero so — em geral dois numeros colados por hifen
    no campo antigo ('32484554-84055454'). A tela marca; nao corta pela metade."""
    return len(numero) > TAMANHO_MAXIMO
