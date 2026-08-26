"""Fronteira publica do modulo catalogo."""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.shared.tipos import Escopo, Regiao


def nomes_de_convenio(
    sessao: Session, *, clinica_id: int, convenio_ids: Iterable[int]
) -> dict[int, str]:
    """Uma consulta para a lista inteira. Outros modulos guardam convenio_id e
    perguntam o nome aqui — nunca fazem JOIN na tabela convenio."""
    ids = list(convenio_ids)
    if not ids:
        return {}
    return {
        c.id: c.nome
        for c in sessao.scalars(
            select(Convenio).where(
                Convenio.clinica_id == clinica_id, Convenio.id.in_(ids)
            )
        )
    }


def convenios(sessao: Session, *, clinica_id: int) -> list[tuple[int, str]]:
    """Todos os convenios da clinica, na ordem do codigo — e o que a tela de
    cadastro usa para montar o select. Devolve pares (id, nome) para quem chama
    nao precisar do modelo Convenio, que nao atravessa a fronteira do modulo."""
    return [
        (c.id, c.nome)
        for c in sessao.scalars(
            select(Convenio)
            .where(Convenio.clinica_id == clinica_id)
            .order_by(Convenio.codigo, Convenio.nome)
        )
    ]


def arvore(sessao: Session, *, clinica_id: int) -> list[dict]:
    """Catalogo agrupado por categoria, na ordem da tela. Alimenta o painel de
    lancamento e a tela de tratamentos."""
    categorias = list(
        sessao.scalars(
            select(Categoria)
            .where(Categoria.clinica_id == clinica_id)
            .order_by(Categoria.ordem, Categoria.nome)
        )
    )
    procedimentos = list(
        sessao.scalars(
            select(Procedimento)
            .where(Procedimento.clinica_id == clinica_id, Procedimento.ativo.is_(True))
            .order_by(Procedimento.nome)
        )
    )
    por_categoria: dict[int, list[dict]] = {}
    for p in procedimentos:
        por_categoria.setdefault(p.categoria_id, []).append(
            {
                "id": p.id,
                "codigo": p.codigo,
                "nome": p.nome,
                "escopo_sugerido": p.escopo_sugerido.value,
                "regioes_sugeridas": [r.value for r in (p.regioes_sugeridas or [])],
                "duracao_min": p.duracao_min,
            }
        )
    return [
        {
            "id": c.id,
            "codigo": c.codigo,
            "nome": c.nome,
            "procedimentos": por_categoria.get(c.id, []),
        }
        for c in categorias
        if por_categoria.get(c.id)
    ]


def precos_por_procedimento(
    sessao: Session, *, clinica_id: int, em: date | None = None
) -> dict[int, list[dict]]:
    """O preco vigente de cada procedimento em cada convenio, numa consulta so.

    Sao 612 pares procedimento x convenio no banco real: perguntar preco por
    linha da tela seriam 612 idas ao banco para desenhar uma pagina.

    `DISTINCT ON` do Postgres resolve "a linha mais recente de cada par" sem
    subconsulta: a ordenacao comeca pelo par e termina pela vigencia, entao a
    primeira linha de cada grupo e a que vale.

    Procedimento sem tabela de preco simplesmente nao aparece no resultado — quem
    chama decide como dizer isso na tela. 'Sem tabela' nao e 'de graca'.
    """
    quando = em or date.today()
    linhas = sessao.execute(
        select(Preco.procedimento_id, Convenio.nome, Convenio.codigo, Preco.valor)
        .join(Procedimento, Preco.procedimento_id == Procedimento.id)
        .join(Convenio, Preco.convenio_id == Convenio.id)
        .where(
            Procedimento.clinica_id == clinica_id,
            Convenio.clinica_id == clinica_id,
            Preco.vigente_desde <= quando,
        )
        .distinct(Preco.procedimento_id, Preco.convenio_id)
        .order_by(
            Preco.procedimento_id,
            Preco.convenio_id,
            Preco.vigente_desde.desc(),
            Preco.id.desc(),
        )
    ).all()

    tabela: dict[int, list[dict]] = {}
    for procedimento_id, convenio, codigo, valor in linhas:
        tabela.setdefault(procedimento_id, []).append(
            {"convenio": convenio, "codigo": codigo, "valor": valor}
        )
    # O particular e o codigo '001' e cai naturalmente em primeiro na ordem do
    # codigo, que e a mesma ordem do select de convenios da tela.
    for lista in tabela.values():
        lista.sort(key=lambda linha: (linha["codigo"], linha["convenio"]))
    return tabela


class CodigoRepetido(ValueError):
    """Ja existe outro tratamento com este codigo nesta clinica."""


def salvar_procedimento(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    procedimento_id: int | None = None,
    codigo: str,
    nome: str,
    categoria_id: int,
    escopo_sugerido: Escopo,
    regioes_sugeridas: "list[Regiao]",
    duracao_min: int | None = None,
    ativo: bool = True,
) -> Procedimento:
    codigo = codigo.strip()
    conflito = sessao.scalars(
        select(Procedimento).where(
            Procedimento.clinica_id == clinica_id, Procedimento.codigo == codigo
        )
    ).first()
    if conflito is not None and conflito.id != procedimento_id:
        raise CodigoRepetido(f"o codigo {codigo} ja e usado por '{conflito.nome}'")

    if procedimento_id is None:
        procedimento = Procedimento(clinica_id=clinica_id, codigo=codigo)
        sessao.add(procedimento)
        acao, antes = "CRIAR", None
    else:
        procedimento = sessao.scalars(
            select(Procedimento).where(
                Procedimento.id == procedimento_id,
                Procedimento.clinica_id == clinica_id,
            )
        ).one()
        acao = "ATUALIZAR"
        antes = {
            "codigo": procedimento.codigo,
            "nome": procedimento.nome,
            "escopo_sugerido": procedimento.escopo_sugerido.value,
        }

    procedimento.codigo = codigo
    procedimento.nome = nome.strip()
    procedimento.categoria_id = categoria_id
    procedimento.escopo_sugerido = escopo_sugerido
    procedimento.regioes_sugeridas = list(regioes_sugeridas)
    procedimento.duracao_min = duracao_min
    procedimento.ativo = ativo
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao=acao,
        entidade="procedimento",
        entidade_id=procedimento.id,
        antes=antes,
        depois={
            "codigo": codigo,
            "nome": procedimento.nome,
            "escopo_sugerido": escopo_sugerido.value,
            "ativo": ativo,
        },
    )
    return procedimento


def definir_preco(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    procedimento_id: int,
    convenio_id: int,
    valor: Decimal,
    vigente_desde: date | None = None,
) -> Preco:
    """Cria uma nova vigencia. O preco antigo NUNCA e sobrescrito: um lancamento
    de 2015 foi cobrado ao preco de 2015, e o extrato tem de continuar explicavel."""
    preco = Preco(
        procedimento_id=procedimento_id,
        convenio_id=convenio_id,
        valor=Decimal(valor).quantize(Decimal("0.01")),
        vigente_desde=vigente_desde or date.today(),
    )
    sessao.add(preco)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="CRIAR",
        entidade="preco",
        entidade_id=preco.id,
        depois={
            "procedimento_id": procedimento_id,
            "convenio_id": convenio_id,
            "valor": str(preco.valor),
        },
    )
    return preco


def preco_de(
    sessao: Session, *, procedimento_id: int, convenio_id: int, em: date | None = None
) -> Decimal | None:
    """O preco vigente na data pedida (hoje, por padrao)."""
    quando = em or date.today()
    preco = sessao.scalars(
        select(Preco)
        .where(
            Preco.procedimento_id == procedimento_id,
            Preco.convenio_id == convenio_id,
            Preco.vigente_desde <= quando,
        )
        .order_by(Preco.vigente_desde.desc(), Preco.id.desc())
    ).first()
    return preco.valor if preco else None
