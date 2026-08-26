"""Decodificador do campo POSDENTE do Dentalis.

POSDENTE nao e um codigo de face: e a coordenada de um caractere na tela do
terminal original, em dois campos de 2 chars alinhados a direita.

    POSDENTE = [ Y (chars 0-1) ][ X (chars 2-3) ]      ex.: "1467" -> Y=14, X=67

Cada dente ocupa uma celula de 5 colunas. Dentro dela, a posicao relativa ao
centro diz qual regiao foi tratada (ver o desenho no plano de implementacao,
Task 4). Validado contra os 44.812 lancamentos reais: 29.350 caem em REGIOES,
7.638 em BOCA, 7.824 em DENTE, com 1 unico registro corrompido.
"""

from dataclasses import dataclass, field

from app.shared.dentes import fdi_de_indice_legado, quadrante
from app.shared.tipos import Escopo, Regiao

SENTINELA_BOCA = "8888"
SENTINELA_DENTE = "9999"

_DENTE_ZERADO = frozenset({"", "0", "00"})
_QUADRANTES_COM_MESIAL_A_DIREITA = frozenset({1, 4})


@dataclass(frozen=True, slots=True)
class Alvo:
    """Para onde um lancamento legado aponta, ja traduzido para o dominio novo."""

    escopo: Escopo
    fdi: int | None
    regiao: Regiao | None
    motivos: tuple[str, ...] = field(default=())


def centro_da_celula(indice_legado: int) -> tuple[int, int]:
    """Coordenada (x, y) do centro da celula de tela deste dente."""
    x = ((indice_legado - 1) % 16) * 5 + 2
    y = 9 if indice_legado <= 16 else 14
    return x, y


def _proximal(dx: int, fdi: int, *, canal: bool) -> Regiao:
    """Mesial e distal dependem do quadrante: a tela e espelhada na linha media.

    Nos quadrantes 1 e 4 a linha media fica a direita na tela, entao andar para a
    direita (dx > 0) aproxima da linha media, ou seja, e mesial. Nos quadrantes
    2 e 3 e o contrario.
    """
    mesial_a_direita = quadrante(fdi) in _QUADRANTES_COM_MESIAL_A_DIREITA
    e_mesial = (dx > 0) if mesial_a_direita else (dx < 0)
    if canal:
        return Regiao.CANAL_MESIAL if e_mesial else Regiao.CANAL_DISTAL
    return Regiao.MESIAL if e_mesial else Regiao.DISTAL


def _regiao_do_deslocamento(dx: int, ndy: int, fdi: int) -> Regiao | None:
    """Traduz o deslocamento dentro da celula. None = posicao desconhecida.

    ndy ja vem normalizado: positivo aponta para a raiz nas duas fileiras.
    """
    if ndy == -1 and dx == 0:
        return Regiao.LINGUAL
    if ndy == 0:
        if dx == 0:
            return Regiao.OCLUSAL
        if dx in (-1, 1):
            return _proximal(dx, fdi, canal=False)
        return None
    if ndy == 1 and dx == 0:
        return Regiao.VESTIBULAR
    if ndy in (2, 3):  # linha da raiz e linha dos canais colapsam nas 3 regioes de raiz
        if dx == 0:
            return Regiao.CANAL_CENTRAL
        if dx in (-2, 2):
            return _proximal(dx, fdi, canal=True)
    return None


def decodificar(numdente: str, posdente: str) -> Alvo:
    """Traduz o par (NUMDENTE, POSDENTE) do Dentalis para escopo + dente + regiao."""
    dente_bruto = (numdente or "").strip()
    # NAO fazer strip no posdente: as duas metades sao alinhadas a direita e o
    # espaco a esquerda faz parte do alinhamento. " 947" e Y=9, X=47.
    pos = (posdente or "").ljust(4)[:4]
    pos_limpo = pos.strip()

    if pos_limpo == SENTINELA_BOCA:
        motivos = () if dente_bruto in _DENTE_ZERADO else ("boca_com_dente_preenchido",)
        return Alvo(Escopo.BOCA, None, None, motivos)

    if dente_bruto in _DENTE_ZERADO:
        return Alvo(Escopo.BOCA, None, None, ("dente_zerado_sem_sentinela",))

    try:
        indice = int(dente_bruto)
        fdi = fdi_de_indice_legado(indice)
    except ValueError:
        return Alvo(Escopo.BOCA, None, None, ("indice_de_dente_invalido",))

    if pos_limpo == SENTINELA_DENTE:
        return Alvo(Escopo.DENTE, fdi, None, ())

    try:
        y, x = int(pos[0:2]), int(pos[2:4])
    except ValueError:
        return Alvo(Escopo.DENTE, fdi, None, ("posdente_ilegivel",))
    if y < 0 or x < 0:
        return Alvo(Escopo.DENTE, fdi, None, ("posdente_ilegivel",))

    xc, yc = centro_da_celula(indice)
    dx = x - xc
    # normaliza para que + aponte sempre para a raiz: na fileira superior a raiz
    # fica em cima (y menor), na inferior fica embaixo (y maior)
    ndy = (yc - y) if indice <= 16 else (y - yc)

    regiao = _regiao_do_deslocamento(dx, ndy, fdi)
    if regiao is None:
        return Alvo(Escopo.DENTE, fdi, None, ("posdente_fora_da_grade",))
    return Alvo(Escopo.REGIOES, fdi, regiao, ())
