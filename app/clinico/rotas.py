from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

# Excecao consciente a fronteira de modulo: clinico importa auth.models.Clinica so
# para ler o nome no cabecalho do PDF. Se auth ganhar um service.clinica(id),
# troque por ele. Anotado aqui para nao virar precedente.
from app.auth.models import Clinica, Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.service import arvore, convenios
from app.clinico.prontuario import gerar as gerar_prontuario
from app.clinico.service import (
    anamnese,
    estado_do_odontograma,
    estado_vazio,
    historico,
    responder,
)
from app.pacientes.service import obter as obter_paciente
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/odontograma", response_class=HTMLResponse)
def em_branco(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """A boca em branco, sem paciente nenhum.

    E o fluxo de quem esta com a pessoa na cadeira: marca o dente e o tratamento
    primeiro, diz de quem e no fim. Nada daqui vai para o banco enquanto o
    atendimento nao for concluido — quem grava e /api/atendimento.
    """
    return templates.TemplateResponse(
        request,
        "odontograma.html",
        {
            "aba": "odontograma",
            "rascunho": True,
            "estado": estado_vazio(),
            "catalogo": arvore(sessao, clinica_id=usuario.clinica_id),
            "convenios": convenios(sessao, clinica_id=usuario.clinica_id),
            "historico": [],
        },
    )


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
            "rascunho": False,
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


@router.get("/prontuario/{paciente_id}.pdf")
def prontuario_pdf(
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    clinica = sessao.get(Clinica, usuario.clinica_id)
    try:
        conteudo = gerar_prontuario(
            sessao,
            clinica_id=usuario.clinica_id,
            paciente_id=paciente_id,
            clinica_nome=clinica.nome if clinica else "BDDente",
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="prontuario-{paciente_id}.pdf"'
        },
    )
