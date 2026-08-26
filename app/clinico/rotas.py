from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.service import arvore
from app.clinico.service import anamnese, estado_do_odontograma, historico, responder
from app.pacientes.service import obter as obter_paciente
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


@router.get("/anamnese/{paciente_id}", response_class=HTMLResponse)
def tela_anamnese(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    paciente = obter_paciente(
        sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
    )
    if paciente is None:
        raise HTTPException(status_code=404, detail="paciente nao encontrado")
    return templates.TemplateResponse(
        request,
        "anamnese.html",
        {
            "aba": "odontograma",
            "paciente": paciente,
            "itens": anamnese(
                sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
            ),
        },
    )


@router.post("/anamnese/{paciente_id}")
async def gravar_anamnese(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    formulario = await request.form()
    respostas = {
        int(chave.removeprefix("pergunta_")): str(valor)
        for chave, valor in formulario.items()
        if chave.startswith("pergunta_")
    }
    responder(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        paciente_id=paciente_id,
        respostas=respostas,
    )
    sessao.commit()
    return RedirectResponse(f"/anamnese/{paciente_id}", status_code=303)
