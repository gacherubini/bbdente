from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.pacientes.service import Filtro, buscar, contagens
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/pacientes", response_class=HTMLResponse)
def listar(
    request: Request,
    q: str = Query(""),
    filtro: str = Query(Filtro.ATIVOS.value),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        escolhido = Filtro(filtro)
    except ValueError:
        escolhido = Filtro.ATIVOS  # filtro inventado na URL nao derruba a tela

    return templates.TemplateResponse(
        request,
        "pacientes.html",
        {
            "aba": "pacientes",
            "termo": q,
            "filtro": escolhido,
            "filtros": list(Filtro),
            "linhas": buscar(
                sessao, clinica_id=usuario.clinica_id, termo=q, filtro=escolhido
            ),
            "numeros": contagens(sessao, clinica_id=usuario.clinica_id),
        },
    )
