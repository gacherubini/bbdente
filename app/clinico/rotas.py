from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
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
    atendimentos_do_dia,
    atendimentos_do_paciente,
    estado_do_odontograma,
    estado_vazio,
    responder,
)
from app.pacientes.service import nomes_de
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
            "atendimentos": [],
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
            "atendimentos": atendimentos_do_paciente(
                sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
            ),
        },
    )


DIAS = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _dia(bruto: str) -> date:
    """Data vinda da URL nunca derruba a tela: o que nao for uma data vale hoje.

    Mesma regra do `_inteiro()` do financeiro. Quem digita na barra de endereco
    erra, e uma tela em branco com 500 nao ensina nada a quem esta atendendo.
    """
    try:
        return date.fromisoformat(bruto)
    except (TypeError, ValueError):
        return date.today()


@router.get("/atendimentos", response_class=HTMLResponse)
def tela_atendimentos(
    request: Request,
    dia: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """O movimento do dia: quem foi atendido e o que foi feito em cada um.

    So o que FOI FEITO. Tratamento planejado para hoje e agenda, e agenda nao
    existe neste sistema — quem planeja para uma data ve isso no odontograma do
    paciente, nao aqui.
    """
    escolhido = _dia(dia)
    grupos = atendimentos_do_dia(
        sessao, clinica_id=usuario.clinica_id, dia=escolhido
    )
    # Fronteira de modulo: o nome do paciente vem pela service dele, numa consulta
    # so para a lista inteira. `clinico` nunca faz JOIN em `paciente`.
    nomes = nomes_de(
        sessao,
        clinica_id=usuario.clinica_id,
        paciente_ids=[grupo["paciente_id"] for grupo in grupos],
    )
    for grupo in grupos:
        grupo["nome"] = nomes.get(grupo["paciente_id"], "—")
    grupos.sort(key=lambda grupo: grupo["nome"])

    return templates.TemplateResponse(
        request,
        "atendimentos.html",
        {
            "aba": "atendimentos",
            "dia": escolhido,
            "dia_da_semana": DIAS[escolhido.weekday()],
            "hoje": date.today(),
            "grupos": grupos,
            "pacientes": len(grupos),
            "tratamentos": sum(grupo["quantos"] for grupo in grupos),
            "total": sum((grupo["total"] for grupo in grupos), Decimal("0.00")),
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
