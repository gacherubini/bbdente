"""Vocabulario do dominio clinico. Estes valores vao para o banco como enum nativo."""

from enum import StrEnum


class Escopo(StrEnum):
    """Onde o tratamento acontece."""

    BOCA = "BOCA"        # consulta, limpeza, protese removivel — sem dente
    DENTE = "DENTE"      # extracao, coroa, radiografia — dente inteiro
    REGIOES = "REGIOES"  # restauracao, canal — uma ou mais regioes marcadas


class Regiao(StrEnum):
    """As 8 regioes de um dente. As 5 primeiras sao coroa; as 3 ultimas, raiz."""

    MESIAL = "MESIAL"
    DISTAL = "DISTAL"
    VESTIBULAR = "VESTIBULAR"
    LINGUAL = "LINGUAL"
    OCLUSAL = "OCLUSAL"  # exibida como "Incisal" nos dentes anteriores — ver shared/dentes.py
    CANAL_MESIAL = "CANAL_MESIAL"
    CANAL_CENTRAL = "CANAL_CENTRAL"
    CANAL_DISTAL = "CANAL_DISTAL"


REGIOES_COROA = frozenset(
    {Regiao.MESIAL, Regiao.DISTAL, Regiao.VESTIBULAR, Regiao.LINGUAL, Regiao.OCLUSAL}
)
REGIOES_RAIZ = frozenset({Regiao.CANAL_MESIAL, Regiao.CANAL_CENTRAL, Regiao.CANAL_DISTAL})


class StatusLancamento(StrEnum):
    PLANEJADO = "PLANEJADO"
    REALIZADO = "REALIZADO"


class TipoCondicao(StrEnum):
    """Estado pre-existente do dente. Sem preco, sem status."""

    AUSENTE = "AUSENTE"
    RESTAURACAO_ANTERIOR = "RESTAURACAO_ANTERIOR"
    COROA = "COROA"
    IMPLANTE = "IMPLANTE"
    OUTRO = "OUTRO"  # os 309 codigos legados caem aqui ate serem traduzidos
