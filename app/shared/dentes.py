"""Notacao FDI e anatomia basica dos 32 dentes permanentes.

A ordem das tuplas abaixo e a ordem da tela, esquerda para direita, e e a mesma
ordem do indice sequencial 1..32 do Dentalis. Essa coincidencia e o unico motivo
pelo qual a conversao de/para o legado e uma indexacao simples.
"""

from enum import StrEnum

from app.shared.tipos import Regiao

FDI_SUPERIOR: tuple[int, ...] = (18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28)
FDI_INFERIOR: tuple[int, ...] = (48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38)
TODOS_FDI: tuple[int, ...] = FDI_SUPERIOR + FDI_INFERIOR

_INDICE_POR_FDI: dict[int, int] = {fdi: i + 1 for i, fdi in enumerate(TODOS_FDI)}


def e_fdi_valido(fdi: object) -> bool:
    return isinstance(fdi, int) and not isinstance(fdi, bool) and fdi in _INDICE_POR_FDI


def fdi_de_indice_legado(indice: int) -> int:
    """Converte o indice sequencial 1..32 da tela do Dentalis para FDI."""
    if not 1 <= indice <= 32:
        raise ValueError(f"indice de dente legado fora de 1..32: {indice!r}")
    return TODOS_FDI[indice - 1]


def indice_legado_de_fdi(fdi: int) -> int:
    """Converte FDI para o indice sequencial 1..32 do Dentalis."""
    if not e_fdi_valido(fdi):
        raise ValueError(f"nao e um dente FDI permanente: {fdi!r}")
    return _INDICE_POR_FDI[fdi]


def quadrante(fdi: int) -> int:
    """1 = superior direito, 2 = superior esquerdo, 3 = inferior esquerdo, 4 = inferior direito."""
    if not e_fdi_valido(fdi):
        raise ValueError(f"nao e um dente FDI permanente: {fdi!r}")
    return fdi // 10


def posicao_no_quadrante(fdi: int) -> int:
    """1 = incisivo central, ate 8 = terceiro molar (siso)."""
    if not e_fdi_valido(fdi):
        raise ValueError(f"nao e um dente FDI permanente: {fdi!r}")
    return fdi % 10


def e_anterior(fdi: int) -> bool:
    """Incisivos e caninos. Neles a face de corte chama incisal, nao oclusal."""
    return posicao_no_quadrante(fdi) <= 3


def numero_de_raizes(fdi: int) -> int:
    """Anatomia padrao: molar superior 3, molar inferior 2, primeiro pre-molar
    superior 2, todo o resto 1."""
    posicao = posicao_no_quadrante(fdi)
    superior = quadrante(fdi) in (1, 2)
    if posicao >= 6:
        return 3 if superior else 2
    if posicao == 4 and superior:
        return 2
    return 1


def canais_do_dente(fdi: int) -> tuple[Regiao, ...]:
    """As regioes de raiz que existem neste dente, em ordem mesial -> distal."""
    match numero_de_raizes(fdi):
        case 1:
            return (Regiao.CANAL_CENTRAL,)
        case 2:
            return (Regiao.CANAL_MESIAL, Regiao.CANAL_DISTAL)
        case _:
            return (Regiao.CANAL_MESIAL, Regiao.CANAL_CENTRAL, Regiao.CANAL_DISTAL)


_ROTULOS: dict[Regiao, str] = {
    Regiao.MESIAL: "Mesial",
    Regiao.DISTAL: "Distal",
    Regiao.VESTIBULAR: "Vestibular",
    Regiao.LINGUAL: "Lingual",
    Regiao.OCLUSAL: "Oclusal",
    Regiao.CANAL_MESIAL: "Canal mesial",
    Regiao.CANAL_CENTRAL: "Canal central",
    Regiao.CANAL_DISTAL: "Canal distal",
}


def rotulo_regiao(regiao: Regiao, fdi: int) -> str:
    """Nome que a tela mostra. O dado gravado e sempre OCLUSAL; 'Incisal' e derivado."""
    if regiao is Regiao.OCLUSAL and e_anterior(fdi):
        return "Incisal"
    return _ROTULOS[regiao]


class Parede(StrEnum):
    """Os quatro lados do quadrado que desenha um dente na tela."""

    CIMA = "CIMA"
    BAIXO = "BAIXO"
    ESQUERDA = "ESQUERDA"
    DIREITA = "DIREITA"


def arcada_superior(fdi: int) -> bool:
    return quadrante(fdi) in (1, 2)


def _mesial_a_direita_na_tela(fdi: int) -> bool:
    """A tela e espelhada na linha media (entre 11 e 21, e entre 41 e 31).

    Quadrantes 1 e 4 sao desenhados na metade ESQUERDA; para eles a linha media
    fica a direita, entao a parede da direita e a mesial. Quadrantes 2 e 3, o
    contrario.
    """
    return quadrante(fdi) in (1, 4)


def paredes_do_dente(fdi: int) -> dict[Parede, Regiao]:
    """Qual regiao cada lado do desenho representa.

    Esta funcao existe para que a regra de espelhamento NAO fique no JavaScript:
    ela e testada aqui e viaja pronta no JSON.
    """
    vestibular_em_cima = arcada_superior(fdi)
    mesial_a_direita = _mesial_a_direita_na_tela(fdi)
    return {
        Parede.CIMA: Regiao.VESTIBULAR if vestibular_em_cima else Regiao.LINGUAL,
        Parede.BAIXO: Regiao.LINGUAL if vestibular_em_cima else Regiao.VESTIBULAR,
        Parede.DIREITA: Regiao.MESIAL if mesial_a_direita else Regiao.DISTAL,
        Parede.ESQUERDA: Regiao.DISTAL if mesial_a_direita else Regiao.MESIAL,
    }


def canais_em_ordem_de_tela(fdi: int) -> tuple[Regiao, ...]:
    """Os canais da esquerda para a direita no desenho.

    canais_do_dente() devolve em ordem anatomica (mesial -> distal); aqui a ordem
    e a da tela, que inverte nos quadrantes 2 e 3.
    """
    canais = canais_do_dente(fdi)
    return canais if not _mesial_a_direita_na_tela(fdi) else tuple(reversed(canais))
