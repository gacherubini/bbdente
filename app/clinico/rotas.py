from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.service import arvore
from app.clinico.service import estado_do_odontograma, historico
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/odontograma")
def sem_paciente():
    """Sem paciente escolhido nao ha o que desenhar: volta para a busca."""
    return RedirectResponse("/pacientes", status_code=303)


@router.get("/odontograma/{paciente_id}", response_class=HTMLResponse)
def tela(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        estado = estado_do_odontograma(
            sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    return templates.TemplateResponse(
        request,
        "odontograma.html",
        {
            "aba": "odontograma",
            "estado": estado,
            "catalogo": arvore(sessao, clinica_id=usuario.clinica_id),
            "historico": historico(
                sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
            ),
        },
    )
