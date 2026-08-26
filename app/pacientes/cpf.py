"""CPF do paciente: guardar, formatar e desconfiar — nunca recusar.

O campo existe desde a migracao (veio do ARQCLIEN como texto livre, muitos em
branco). A regua aqui e a mesma de `telefone.py`: o que parece errado entra
marcado em `revisar_motivo`, para a recepcao conferir com a pessoa depois.
"""

import re

_NAO_DIGITO = re.compile(r"\D")

TAMANHO = 11


def so_digitos(bruto: str | None) -> str:
    """'529.982.247-25' -> '52998224725'."""
    if not bruto:
        return ""
    return _NAO_DIGITO.sub("", bruto)


def formatar(numero: str | None) -> str:
    """Formata para leitura. Devolve como veio quando nao reconhece o formato —
    nunca inventa digito para fazer caber."""
    digitos = so_digitos(numero)
    if len(digitos) != TAMANHO:
        return (numero or "").strip()
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _digito(digitos: str, peso_inicial: int) -> str:
    soma = sum(int(d) * (peso_inicial - i) for i, d in enumerate(digitos))
    resto = (soma * 10) % 11
    return "0" if resto == 10 else str(resto)


def parecer_invalido(bruto: str | None) -> bool:
    """Confere o digito verificador. Campo vazio NAO e suspeito: 30 anos de
    cadastro sem CPF estao no banco, e nao informar continua legitimo."""
    digitos = so_digitos(bruto)
    if not digitos:
        return False
    if len(digitos) != TAMANHO:
        return True
    # '111.111.111-11' fecha na conta e mesmo assim nao existe.
    if digitos == digitos[0] * TAMANHO:
        return True
    primeiro = _digito(digitos[:9], 10)
    segundo = _digito(digitos[:9] + primeiro, 11)
    return digitos[9:] != primeiro + segundo
