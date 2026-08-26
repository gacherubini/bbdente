from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.models import Categoria, Convenio
from app.catalogo.service import (
    CodigoRepetido,
    arvore,
    definir_preco,
    precos_por_procedimento,
    salvar_procedimento,
)
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao
from app.templates import templates

router = APIRouter()


def _contexto(sessao: Session, clinica_id: int, erro: str | None = None) -> dict:
    return {
        "aba": "tratamentos",
        "catalogo": arvore(sessao, clinica_id=clinica_id),
        # Fora da arvore de proposito: ela vira JSON no painel do odontograma,
        # e Decimal nao atravessa `tojson`.
        "precos": precos_por_procedimento(sessao, clinica_id=clinica_id),
        "categorias": list(
            sessao.scalars(
                select(Categoria)
                .where(Categoria.clinica_id == clinica_id)
                .order_by(Categoria.ordem)
            )
        ),
        "convenios": list(
            sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
        ),
        "escopos": list(Escopo),
        "regioes": list(Regiao),
        "erro": erro,
    }


@router.get("/tratamentos", response_class=HTMLResponse)
def listar(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    return templates.TemplateResponse(
        request, "tratamentos.html", _contexto(sessao, usuario.clinica_id)
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
        procedimento = salvar_procedimento(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            procedimento_id=int(procedimento_id) if procedimento_id else None,
            codigo=codigo,
            nome=nome,
            categoria_id=categoria_id,
            escopo_sugerido=escopo_sugerido,
            regioes_sugeridas=[Regiao(valor) for valor in regiao],
        )
        if convenio_id and valor:
            definir_preco(
                sessao,
                clinica_id=usuario.clinica_id,
                usuario_id=usuario.id,
                procedimento_id=procedimento.id,
                convenio_id=int(convenio_id),
                valor=Decimal(valor.replace(".", "").replace(",", ".")),
            )
    except (CodigoRepetido, InvalidOperation, ValueError) as erro:
        sessao.rollback()
        return templates.TemplateResponse(
            request,
            "tratamentos.html",
            _contexto(sessao, usuario.clinica_id, erro=str(erro)),
            status_code=200,
        )

    sessao.commit()
    return RedirectResponse("/tratamentos", status_code=303)
