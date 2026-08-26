"""Limpeza dos campos de texto e data vindos do Dentalis.

O extrato ja normalizou as datas para 'YYYY-MM-DD'; o que sobra aqui e decidir o
que fazer com as impossiveis. A regra e sempre a mesma: preserva e marca.
"""

from datetime import date

ANO_MINIMO = 1900
ANO_MAXIMO = 2035  # o Dentalis parou em 2024; nada legitimo passa disso


def limpar(valor: str | None) -> str | None:
    """Tira espacos das pontas. String vazia vira None."""
    if valor is None:
        return None
    limpo = valor.strip()
    return limpo or None


def data_legada(valor: str | None) -> tuple[date | None, str | None]:
    """Le uma data do extrato. Devolve (data, motivo_de_revisao).

    Data impossivel e devolvida assim mesmo, marcada — nunca apagada nem chutada.
    """
    bruto = limpar(valor)
    if bruto is None:
        return None, None
    try:
        lida = date.fromisoformat(bruto)
    except ValueError:
        return None, "data_ilegivel"
    if not ANO_MINIMO <= lida.year <= ANO_MAXIMO:
        return lida, "data_suspeita"
    return lida, None
