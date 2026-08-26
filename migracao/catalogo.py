"""Migra categorias, convenios, procedimentos e precos.

O ponto nao obvio: `escopo_sugerido` e `regioes_sugeridas` nao sao configuracao —
sao calculados a partir das 44.812 ocorrencias reais. O palpite inicial da tela e
literalmente o habito da Dra. Katia nos ultimos 30 anos.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.shared.tipos import Escopo, Regiao
from migracao.extrato import Extrato
from migracao.posdente import decodificar
from migracao.texto import limpar

# ARQESPE tem 13 linhas; '00 Todas as Intervencoes' e um filtro de tela.
CODIGO_CATEGORIA_FILTRO = "00"
CATEGORIA_PADRAO = "11"  # "Outros Servicos"
VIGENCIA_INICIAL = date(2024, 6, 26)  # ultimo dia de uso do Dentalis
# Uma regiao entra na sugestao se aparece em pelo menos 15% das ocorrencias do
# procedimento; no maximo 3, da mais frequente para a menos.
LIMIAR_SUGESTAO = 0.15
MAXIMO_REGIOES_SUGERIDAS = 3


@dataclass
class ResultadoCatalogo:
    categorias: int = 0
    convenios: int = 0
    procedimentos: int = 0
    precos: int = 0


def calcular_sugestoes(extrato: Extrato) -> dict[str, tuple[Escopo, list[Regiao]]]:
    """Para cada CODSERV, o escopo dominante e as regioes mais usadas no historico."""
    escopos: defaultdict[str, Counter] = defaultdict(Counter)
    regioes: defaultdict[str, Counter] = defaultdict(Counter)

    for linha in extrato.linhas("ARQDENTE"):
        codigo = (linha["CODSERV"] or "").strip()
        if not codigo:
            continue
        alvo = decodificar(linha["NUMDENTE"], linha["POSDENTE"])
        escopos[codigo][alvo.escopo] += 1
        if alvo.regiao is not None:
            regioes[codigo][alvo.regiao] += 1

    sugestoes: dict[str, tuple[Escopo, list[Regiao]]] = {}
    for codigo, contagem in escopos.items():
        escopo = contagem.most_common(1)[0][0]
        if escopo is not Escopo.REGIOES:
            sugestoes[codigo] = (escopo, [])
            continue
        total = sum(regioes[codigo].values())
        escolhidas = [
            regiao
            for regiao, n in regioes[codigo].most_common(MAXIMO_REGIOES_SUGERIDAS)
            if total and n / total >= LIMIAR_SUGESTAO
        ]
        # Um procedimento com escopo REGIOES sem nenhuma regiao acima do limiar
        # ainda precisa de um palpite: fica com a mais frequente.
        if not escolhidas and regioes[codigo]:
            escolhidas = [regioes[codigo].most_common(1)[0][0]]
        sugestoes[codigo] = (Escopo.REGIOES, escolhidas)
    return sugestoes


def _migrar_categorias(sessao: Session, extrato: Extrato, clinica_id: int) -> int:
    existentes = {
        c.codigo: c
        for c in sessao.scalars(select(Categoria).where(Categoria.clinica_id == clinica_id))
    }
    n = 0
    for linha in extrato.linhas("ARQESPE"):
        codigo = (limpar(linha["CODIGO"]) or "").zfill(2)
        if codigo == CODIGO_CATEGORIA_FILTRO:
            continue
        nome = limpar(linha["NOME"]) or f"Categoria {codigo}"
        if codigo in existentes:
            existentes[codigo].nome = nome
        else:
            sessao.add(
                Categoria(
                    clinica_id=clinica_id, codigo=codigo, nome=nome, ordem=int(codigo)
                )
            )
        n += 1
    sessao.flush()
    return n


def _migrar_convenios(sessao: Session, extrato: Extrato, clinica_id: int) -> int:
    existentes = {
        c.codigo: c
        for c in sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
    }
    n = 0
    for linha in extrato.linhas("TABELAS"):
        codigo = (limpar(linha["CODCONV"]) or "").zfill(3)
        # 003 a 006 nao tem nome no legado. Rotulo provisorio, visivelmente provisorio.
        nome = limpar(linha["NOMCONV"]) or f"Convenio {codigo}"
        if codigo in existentes:
            existentes[codigo].nome = nome
        else:
            sessao.add(Convenio(clinica_id=clinica_id, codigo=codigo, nome=nome))
        n += 1
    sessao.flush()
    return n


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoCatalogo:
    resultado = ResultadoCatalogo()
    resultado.categorias = _migrar_categorias(sessao, extrato, clinica_id)
    resultado.convenios = _migrar_convenios(sessao, extrato, clinica_id)

    categorias = {
        c.codigo: c.id
        for c in sessao.scalars(select(Categoria).where(Categoria.clinica_id == clinica_id))
    }
    convenios = {
        c.codigo: c.id
        for c in sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
    }
    sugestoes = calcular_sugestoes(extrato)

    procedimentos = {
        p.codigo: p
        for p in sessao.scalars(
            select(Procedimento).where(Procedimento.clinica_id == clinica_id)
        )
    }
    # V_PROCEDIMENTO consolida os 51 arquivos ARQSE### em 612 pares convenio x
    # procedimento, com 477 CODSERV distintos.
    pares = extrato.consultar(
        "SELECT CODCONV, CODSERV, DESCRICAO FROM V_PROCEDIMENTO ORDER BY CODSERV, CODCONV"
    )

    precos_existentes = {
        (p.procedimento_id, p.convenio_id) for p in sessao.scalars(select(Preco))
    }

    for par in pares:
        codigo = (limpar(par["CODSERV"]) or "").strip()
        descricao = limpar(par["DESCRICAO"]) or f"Procedimento {codigo}"
        cod_conv = (limpar(par["CODCONV"]) or "").zfill(3)

        procedimento = procedimentos.get(codigo)
        if procedimento is None:
            escopo, regioes = sugestoes.get(codigo, (Escopo.DENTE, []))
            especialidade = _especialidade_de(extrato, codigo)
            procedimento = Procedimento(
                clinica_id=clinica_id,
                codigo=codigo,
                nome=descricao,
                categoria_id=categorias.get(especialidade, categorias[CATEGORIA_PADRAO]),
                escopo_sugerido=escopo,
                regioes_sugeridas=regioes,
                duracao_min=_duracao_de(extrato, codigo),
            )
            sessao.add(procedimento)
            sessao.flush()
            procedimentos[codigo] = procedimento
            resultado.procedimentos += 1

        convenio_id = convenios.get(cod_conv)
        if convenio_id is None:
            continue
        if (procedimento.id, convenio_id) in precos_existentes:
            resultado.precos += 1
            continue
        sessao.add(
            Preco(
                procedimento_id=procedimento.id,
                convenio_id=convenio_id,
                valor=Decimal(str(_valor_de(extrato, cod_conv, codigo))),
                vigente_desde=VIGENCIA_INICIAL,
            )
        )
        precos_existentes.add((procedimento.id, convenio_id))
        resultado.precos += 1

    sessao.flush()
    if resultado.procedimentos == 0:
        # segunda execucao: nada novo criado, mas o total tem de continuar batendo
        resultado.procedimentos = sessao.query(Procedimento).count()
    return resultado


_CACHE_DETALHE: dict[tuple[str, str], dict] = {}


def _detalhe(extrato: Extrato, cod_conv: str, cod_serv: str) -> dict:
    """Le a linha crua do ARQSE### daquele convenio. Cacheia: sao 612 consultas."""
    chave = (cod_conv, cod_serv)
    if chave not in _CACHE_DETALHE:
        tabela = f"ARQSE{cod_conv}"
        linhas = extrato.consultar(
            f'SELECT * FROM "{tabela}" WHERE TRIM(CODSERV) = ?', (cod_serv,)  # noqa: S608
        )
        _CACHE_DETALHE[chave] = dict(linhas[0]) if linhas else {}
    return _CACHE_DETALHE[chave]


def _especialidade_de(extrato: Extrato, cod_serv: str) -> str:
    """A categoria vem do catalogo PARTICULAR (001), o mais completo."""
    valor = _detalhe(extrato, "001", cod_serv).get("ESPECIA")
    codigo = (limpar(str(valor)) if valor is not None else None) or CATEGORIA_PADRAO
    return codigo.zfill(2)


def _duracao_de(extrato: Extrato, cod_serv: str) -> int | None:
    valor = _detalhe(extrato, "001", cod_serv).get("TEMPO")
    try:
        minutos = int(float(valor))
    except (TypeError, ValueError):
        return None
    return minutos or None


def _valor_de(extrato: Extrato, cod_conv: str, cod_serv: str) -> float:
    valor = _detalhe(extrato, cod_conv, cod_serv).get("VALOCZ")
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0
