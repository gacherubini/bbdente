from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.catalogo.service import (
    CodigoRepetido,
    arvore,
    definir_preco,
    precos_por_procedimento,
    salvar_procedimento,
    validar_procedimento,
)
from app.shared.db import obter_sessao
from app.shared.formato import ValorInvalido, para_decimal
from app.shared.tipos import Escopo, Regiao
from app.templates import templates

router = APIRouter()


def _categorias(sessao: Session, clinica_id: int) -> list[Categoria]:
    return list(
        sessao.scalars(
            select(Categoria)
            .where(Categoria.clinica_id == clinica_id)
            .order_by(Categoria.ordem)
        )
    )


def _convenios(sessao: Session, clinica_id: int) -> list[Convenio]:
    return list(
        sessao.scalars(
            select(Convenio)
            .where(Convenio.clinica_id == clinica_id)
            .order_by(Convenio.codigo)
        )
    )


def _contexto(sessao: Session, clinica_id: int, erro: str | None = None) -> dict:
    return {
        "aba": "tratamentos",
        "catalogo": arvore(sessao, clinica_id=clinica_id),
        # Fora da arvore de proposito: ela vira JSON no painel do odontograma, e
        # Decimal nao atravessa o `tojson`.
        "precos": precos_por_procedimento(sessao, clinica_id=clinica_id),
        "categorias": _categorias(sessao, clinica_id),
        "convenios": _convenios(sessao, clinica_id),
        "escopos": list(Escopo),
        "regioes": list(Regiao),
        "erro": erro,
    }


def _obter(sessao: Session, clinica_id: int, procedimento_id: int) -> Procedimento:
    procedimento = sessao.scalars(
        select(Procedimento).where(
            Procedimento.id == procedimento_id, Procedimento.clinica_id == clinica_id
        )
    ).first()
    if procedimento is None:
        raise HTTPException(status_code=404, detail="tratamento nao encontrado")
    return procedimento


@router.get("/tratamentos", response_class=HTMLResponse)
def listar(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    return templates.TemplateResponse(
        request, "tratamentos.html", _contexto(sessao, usuario.clinica_id)
    )


def _precos_digitados(
    convenio_ids: list[str], valores: list[str]
) -> list[tuple[int, Decimal]]:
    """Os campos de preco da tela de edicao, um por convenio, lidos de uma vez.

    Campo vazio e "nao mexer": apagar preco nao existe, o historico precisa dele.

    Converte tudo antes de devolver — um valor invalido no ultimo convenio nao
    pode deixar os primeiros ja gravados.
    """
    return [
        (int(convenio_id), para_decimal(valor))
        for convenio_id, valor in zip(convenio_ids, valores, strict=False)
        if convenio_id.strip() and valor.strip()
    ]


def _gravar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    procedimento_id: int | None,
    codigo: str,
    nome: str,
    categoria_id: int,
    escopo_sugerido: Escopo,
    regiao: list[str],
    ativo: bool,
    convenio_id: str,
    valor: str,
    preco_convenio_id: list[str] | None = None,
    preco_valor: list[str] | None = None,
) -> None:
    """Grava tratamento e, se veio valor, a vigencia de preco.

    Sao duas portas de entrada de preco: o par `convenio_id`/`valor` da tela de
    cadastro (um preco de cada vez, para o tratamento que acabou de nascer) e os
    campos `preco_convenio_id`/`preco_valor` da tela de edicao, que trazem um por
    convenio. Quem decide o que vira linha nova e `definir_preco`: valor igual ao
    que ja vale nao grava nada.

    Confere tudo ANTES de escrever a primeira linha. Assim o caminho do erro nao
    precisa de `rollback` — e `rollback` aqui jogaria fora tambem o que a
    transacao ja tinha dentro.
    """
    validar_procedimento(
        sessao,
        clinica_id=clinica_id,
        procedimento_id=procedimento_id,
        codigo=codigo,
        nome=nome,
    )
    novo_preco = para_decimal(valor) if convenio_id and valor.strip() else None
    novos_precos = _precos_digitados(preco_convenio_id or [], preco_valor or [])

    procedimento = salvar_procedimento(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        procedimento_id=procedimento_id,
        codigo=codigo,
        nome=nome,
        categoria_id=categoria_id,
        escopo_sugerido=escopo_sugerido,
        regioes_sugeridas=[Regiao(v) for v in regiao],
        ativo=ativo,
    )
    if novo_preco is not None:
        definir_preco(
            sessao,
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            procedimento_id=procedimento.id,
            convenio_id=int(convenio_id),
            valor=novo_preco,
        )
    for convenio, preco in novos_precos:
        # `definir_preco` devolve a vigencia atual sem gravar quando o valor nao
        # mudou: salvar o formulario sem mexer nos precos nao cria linha nenhuma.
        definir_preco(
            sessao,
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            procedimento_id=procedimento.id,
            convenio_id=convenio,
            valor=preco,
        )


@router.post("/tratamentos")
def salvar(
    request: Request,
    procedimento_id: str = Form(""),
    codigo: str = Form(...),
    nome: str = Form(...),
    categoria_id: int = Form(...),
    escopo_sugerido: Escopo = Form(...),
    # list[Regiao] direto em Form nao funciona de forma confiavel; convertemos a mao.
    regiao: list[str] = Form([]),
    convenio_id: str = Form(""),
    valor: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        _gravar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            procedimento_id=int(procedimento_id) if procedimento_id else None,
            codigo=codigo,
            nome=nome,
            categoria_id=categoria_id,
            escopo_sugerido=escopo_sugerido,
            regiao=regiao,
            ativo=True,
            convenio_id=convenio_id,
            valor=valor,
        )
    except (CodigoRepetido, ValorInvalido, ValueError) as erro:
        return templates.TemplateResponse(
            request,
            "tratamentos.html",
            _contexto(sessao, usuario.clinica_id, erro=str(erro)),
            status_code=200,
        )

    sessao.commit()
    return RedirectResponse("/tratamentos", status_code=303)


def _tela_de_edicao(
    request: Request,
    sessao: Session,
    clinica_id: int,
    procedimento: Procedimento,
    erro: str | None = None,
) -> HTMLResponse:
    vigentes = precos_por_procedimento(sessao, clinica_id=clinica_id).get(
        procedimento.id, []
    )
    return templates.TemplateResponse(
        request,
        "tratamento_editar.html",
        {
            "aba": "tratamentos",
            "procedimento": procedimento,
            # Por convenio, para a tela desenhar um campo por convenio da clinica
            # — inclusive os que ainda nao tem preco, que abrem vazios.
            "precos": {linha["convenio_id"]: linha["valor"] for linha in vigentes},
            "categorias": _categorias(sessao, clinica_id),
            "convenios": _convenios(sessao, clinica_id),
            "escopos": list(Escopo),
            "regioes": list(Regiao),
            "erro": erro,
        },
        status_code=200,
    )


@router.get("/tratamentos/{procedimento_id}", response_class=HTMLResponse)
def editar(
    request: Request,
    procedimento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    procedimento = _obter(sessao, usuario.clinica_id, procedimento_id)
    return _tela_de_edicao(request, sessao, usuario.clinica_id, procedimento)


@router.post("/tratamentos/{procedimento_id}")
def atualizar(
    request: Request,
    procedimento_id: int,
    codigo: str = Form(...),
    nome: str = Form(...),
    categoria_id: int = Form(...),
    escopo_sugerido: Escopo = Form(...),
    regiao: list[str] = Form([]),
    # Checkbox desmarcado nao e enviado pelo navegador: ausente significa inativo.
    ativo: str = Form(""),
    convenio_id: str = Form(""),
    valor: str = Form(""),
    # Um campo de preco por convenio: dois campos repetidos, casados pela ordem
    # em que o navegador os manda. list[...] direto em Form nao converte tipo de
    # forma confiavel; convertemos a mao, como ja e feito com `regiao`.
    preco_convenio_id: list[str] = Form([]),
    preco_valor: list[str] = Form([]),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    procedimento = _obter(sessao, usuario.clinica_id, procedimento_id)
    try:
        _gravar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            procedimento_id=procedimento.id,
            codigo=codigo,
            nome=nome,
            categoria_id=categoria_id,
            escopo_sugerido=escopo_sugerido,
            regiao=regiao,
            ativo=bool(ativo),
            convenio_id=convenio_id,
            valor=valor,
            preco_convenio_id=preco_convenio_id,
            preco_valor=preco_valor,
        )
    except (CodigoRepetido, ValorInvalido, ValueError) as erro:
        # Nada foi escrito: a tela mostra o tratamento como esta guardado, e o
        # erro explica por que nao mudou.
        return _tela_de_edicao(
            request, sessao, usuario.clinica_id, procedimento, erro=str(erro)
        )

    sessao.commit()
    return RedirectResponse("/tratamentos", status_code=303)
