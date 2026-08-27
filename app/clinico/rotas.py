from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

# Fronteira de modulo: a agenda so pela service dela.
from app.agenda.service import obter as obter_agendamento

# Excecao consciente a fronteira de modulo: clinico importa auth.models.Clinica so
# para ler o nome no cabecalho do PDF. Se auth ganhar um service.clinica(id),
# troque por ele. Anotado aqui para nao virar precedente.
from app.auth.models import Clinica, Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.service import arvore, convenio_particular, convenios
from app.clinico.prontuario import gerar as gerar_prontuario
from app.clinico.service import (
    anamnese,
    atendimentos_do_dia,
    atendimentos_do_paciente,
    estado_do_odontograma,
    estado_vazio,
    planejados_do_dia,
    responder,
)
from app.pacientes.service import nomes_de
from app.pacientes.service import obter as obter_paciente
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


def _horario_avulso(sessao: Session, *, clinica_id: int, bruto: str) -> dict | None:
    """O horario da agenda de onde veio o clique, se houver um utilizavel.

    So horario SEM paciente interessa: quem ja tem cadastro vai direto para o
    odontograma dela, e nao passa por aqui.
    """
    try:
        agendamento_id = int(bruto)
    except (TypeError, ValueError):
        return None
    marcado = obter_agendamento(
        sessao, clinica_id=clinica_id, agendamento_id=agendamento_id
    )
    if marcado is None or marcado.paciente_id is not None:
        return None
    return {
        "id": marcado.id,
        "nome": marcado.nome_avulso or "",
        "telefone": marcado.telefone_avulso or "",
        "hora": marcado.inicio.strftime("%H:%M"),
        "dia": marcado.dia,
    }


@router.get("/odontograma", response_class=HTMLResponse)
def em_branco(
    request: Request,
    agendamento: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """A boca em branco, sem paciente nenhum.

    E o fluxo de quem esta com a pessoa na cadeira: marca o dente e o tratamento
    primeiro, diz de quem e no fim. Nada daqui vai para o banco enquanto o
    atendimento nao for concluido — quem grava e /api/atendimento.

    `?agendamento=` vem do botao "atender" de um horario avulso da agenda: a tela
    ja sabe o nome e o telefone que foram anotados ao telefone, para ninguem
    digitar de novo. Horario invalido nao e erro — abre a boca em branco de
    sempre, porque o atendimento importa mais que a agenda.
    """
    marcado = _horario_avulso(sessao, clinica_id=usuario.clinica_id, bruto=agendamento)
    return templates.TemplateResponse(
        request,
        "odontograma.html",
        {
            "aba": "odontograma",
            "rascunho": True,
            "agendamento": marcado,
            "estado": estado_vazio(),
            # Sem paciente ainda, entao sem convenio: o preco que aparece no
            # painel e o do PARTICULAR, que e o caso comum. A dentista corrige o
            # valor na hora se for outro.
            "catalogo": arvore(
                sessao,
                clinica_id=usuario.clinica_id,
                convenio_id=convenio_particular(sessao, clinica_id=usuario.clinica_id),
            ),
            "convenios": convenios(sessao, clinica_id=usuario.clinica_id),
            "hoje": date.today(),
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

    # O preco depende do convenio da paciente: o painel abre com o valor certo
    # para ela, nao com a tabela do particular. Pela service, nunca pelo model.
    paciente = obter_paciente(
        sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
    )
    return templates.TemplateResponse(
        request,
        "odontograma.html",
        {
            "aba": "odontograma",
            "rascunho": False,
            "estado": estado,
            "catalogo": arvore(
                sessao,
                clinica_id=usuario.clinica_id,
                convenio_id=(
                    paciente.convenio_id
                    if paciente is not None and paciente.convenio_id
                    else convenio_particular(sessao, clinica_id=usuario.clinica_id)
                ),
            ),
            "hoje": date.today(),
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
    feitos = atendimentos_do_dia(sessao, clinica_id=usuario.clinica_id, dia=escolhido)
    planejados = planejados_do_dia(
        sessao, clinica_id=usuario.clinica_id, dia=escolhido
    )
    # Fronteira de modulo: o nome do paciente vem pela service dele, numa consulta
    # so para as duas listas juntas. `clinico` nunca faz JOIN em `paciente`.
    nomes = nomes_de(
        sessao,
        clinica_id=usuario.clinica_id,
        paciente_ids=[g["paciente_id"] for g in feitos + planejados],
    )
    for grupo in feitos + planejados:
        grupo["nome"] = nomes.get(grupo["paciente_id"], "—")
    feitos.sort(key=lambda grupo: grupo["nome"])
    planejados.sort(key=lambda grupo: grupo["nome"])

    return templates.TemplateResponse(
        request,
        "atendimentos.html",
        {
            "aba": "atendimentos",
            "dia": escolhido,
            "dia_da_semana": DIAS[escolhido.weekday()],
            "hoje": date.today(),
            "grupos": feitos,
            "planejados": planejados,
            # Os numeros do topo sao do que foi FEITO. O planejado tem o subtotal
            # dele no cabecalho do proprio bloco.
            "pacientes": len(feitos),
            "tratamentos": sum(grupo["quantos"] for grupo in feitos),
            "total": sum((grupo["total"] for grupo in feitos), Decimal("0.00")),
            "planejados_tratamentos": sum(g["quantos"] for g in planejados),
            "planejados_total": sum(
                (g["total"] for g in planejados), Decimal("0.00")
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
