"""A tela da agenda.

Uma rota so com duas vistas — semana e mes montam o mesmo `Periodo`, entao
duas rotas seriam a mesma tela escrita duas vezes.

Tudo por formulario, com 303 de volta: funciona sem JavaScript, o botao
"voltar" nao reenvia o POST, e nao ha endpoint JSON novo. O unico JSON que a
tela consome (`/api/pacientes`) ja existe.
"""

from datetime import date, time

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.agenda.models import (
    DURACAO_MAXIMA_MIN,
    DURACAO_MINIMA_MIN,
    DURACAO_PADRAO_MIN,
    SituacaoAgendamento,
)
from app.agenda.service import (
    NaoEncontrado,
    PacienteDeOutraClinica,
    SemDono,
    configuracao_de,
    conflitos_de,
    excluir,
    grade,
    marcar,
    mes_de,
    mudar_situacao,
    obter,
    remarcar,
    semana_de,
)
from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.pacientes.service import contatos_de
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()

DIAS_DA_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
# Duracoes a um clique. Sao as tres do consultorio; qualquer outra se digita.
DURACOES = [30, 60, 90]


def _dia(bruto: str | None) -> date:
    """A data da URL nunca derruba a tela: o que nao for data vira hoje.

    URL e coisa que se edita, se encurta e se manda por WhatsApp pela metade.
    """
    try:
        return date.fromisoformat(bruto or "")
    except ValueError:
        return date.today()


def _hora(bruto: str | None) -> time | None:
    try:
        return time.fromisoformat(bruto or "")
    except ValueError:
        return None


def _duracao(bruto: str | None) -> int:
    try:
        valor = int(bruto or DURACAO_PADRAO_MIN)
    except ValueError:
        return DURACAO_PADRAO_MIN
    if DURACAO_MINIMA_MIN <= valor <= DURACAO_MAXIMA_MIN:
        return valor
    return DURACAO_PADRAO_MIN


def _paciente_id(bruto: str | None) -> int | None:
    try:
        return int(bruto) if bruto else None
    except ValueError:
        return None


@router.get("/agenda", response_class=HTMLResponse)
def tela(
    request: Request,
    vista: str = Query("semana"),
    dia: str = Query(""),
    conflito: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
) -> HTMLResponse:
    escolhido = _dia(dia)
    # Vista inventada cai na semana em vez de dar erro: e a que responde a
    # pergunta do telefone ("onde eu encaixo ela?").
    de_mes = vista == "mes"
    periodo = mes_de(escolhido) if de_mes else semana_de(escolhido)
    montada = grade(sessao, clinica_id=usuario.clinica_id, periodo=periodo)

    return templates.TemplateResponse(
        request,
        "agenda_mes.html" if de_mes else "agenda_semana.html",
        {
            "aba": "agenda",
            "vista": "mes" if de_mes else "semana",
            "dia": escolhido,
            "hoje": date.today(),
            "grade": montada,
            "periodo": periodo,
            "dias_da_semana": DIAS_DA_SEMANA,
            "meses": MESES,
            "nome_do_mes": MESES[escolhido.month - 1],
            "anterior": _vizinho(escolhido, de_mes, -1),
            "proximo": _vizinho(escolhido, de_mes, +1),
            "conflito": conflito,
            # Silencio que parece funcionamento e a pior forma de desligar: ela
            # confiaria que a paciente foi avisada, e a paciente nao foi.
            "lembrete_ativo": configuracao_de(
                sessao, clinica_id=usuario.clinica_id
            ).lembrete_ativo,
        },
    )


def _vizinho(dia: date, de_mes: bool, sentido: int) -> date:
    if not de_mes:
        return date.fromordinal(dia.toordinal() + 7 * sentido)
    total = dia.year * 12 + (dia.month - 1) + sentido
    ano, mes = divmod(total, 12)
    return date(ano, mes + 1, 1)


@router.get("/agenda/novo", response_class=HTMLResponse)
def formulario_novo(
    request: Request,
    dia: str = Query(""),
    hora: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
) -> HTMLResponse:
    """Ja vem preenchido pelo clique na celula: o dia e a hora sao a metade do
    formulario, e sao os dois campos que mais custam para digitar no telefone."""
    return _formulario(request, dados=_vazio(dia, hora))


def _vazio(dia: str, hora: str) -> dict:
    escolhida = _hora(hora)
    return {
        "id": None,
        "paciente_id": "",
        "nome": "",
        "telefone": "",
        "dia": _dia(dia).isoformat(),
        "inicio": escolhida.strftime("%H:%M") if escolhida else "09:00",
        "duracao_min": str(DURACAO_PADRAO_MIN),
        "observacao": "",
    }


def _formulario(
    request: Request, *, dados: dict, erro: str | None = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "agenda_editar.html",
        {"aba": "agenda", "dados": dados, "erro": erro, "duracoes": DURACOES},
        status_code=200,
    )


def _voltar(dia: date, conflitos: int = 0) -> RedirectResponse:
    """Sempre para a semana do dia gravado — a tela que responde "e agora?"."""
    destino = f"/agenda?dia={dia.isoformat()}"
    if conflitos:
        destino += f"&conflito={conflitos}"
    return RedirectResponse(destino, status_code=303)


@router.post("/agenda")
def gravar(
    request: Request,
    paciente_id: str = Form(""),
    nome: str = Form(""),
    telefone: str = Form(""),
    dia: str = Form(""),
    inicio: str = Form(""),
    duracao_min: str = Form(str(DURACAO_PADRAO_MIN)),
    observacao: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Marca. O campo de busca E o campo de nome: com `paciente_id` grava a
    paciente da base, sem ele grava o que ela digitou como horario avulso."""
    dados = {
        "id": None,
        "paciente_id": paciente_id,
        "nome": nome,
        "telefone": telefone,
        "dia": dia,
        "inicio": inicio,
        "duracao_min": duracao_min,
        "observacao": observacao,
    }
    quando = _hora(inicio)
    if quando is None:
        return _formulario(request, dados=dados, erro="Hora inválida — use 09:00.")

    try:
        agendamento = marcar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            paciente_id=_paciente_id(paciente_id),
            nome_avulso=nome,
            telefone_avulso=telefone,
            dia=_dia(dia),
            inicio=quando,
            duracao_min=_duracao(duracao_min),
            observacao=observacao,
        )
    except SemDono:
        return _formulario(
            request, dados=dados, erro="Escreva o nome de quem vem — nem que seja só o primeiro."
        )
    except PacienteDeOutraClinica as erro:
        raise HTTPException(status_code=404, detail="paciente nao encontrado") from erro

    sessao.commit()
    # Conflito nunca bloqueia: o horario ja esta gravado quando o aviso aparece.
    return _voltar(agendamento.dia, len(conflitos_de(sessao, agendamento=agendamento)))


@router.get("/agenda/{agendamento_id}", response_class=HTMLResponse)
def formulario_editar(
    request: Request,
    agendamento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
) -> HTMLResponse:
    agendamento = obter(
        sessao, clinica_id=usuario.clinica_id, agendamento_id=agendamento_id
    )
    if agendamento is None:
        raise HTTPException(status_code=404, detail="horario nao encontrado")

    nome = agendamento.nome_avulso or ""
    telefone = agendamento.telefone_avulso or ""
    if agendamento.paciente_id is not None:
        contato = contatos_de(
            sessao,
            clinica_id=usuario.clinica_id,
            paciente_ids=[agendamento.paciente_id],
        ).get(agendamento.paciente_id)
        if contato:
            nome, telefone = contato.nome, contato.telefone or ""

    return _formulario(
        request,
        dados={
            "id": agendamento.id,
            "paciente_id": agendamento.paciente_id or "",
            "nome": nome,
            "telefone": telefone,
            "dia": agendamento.dia.isoformat(),
            "inicio": agendamento.inicio.strftime("%H:%M"),
            "duracao_min": str(agendamento.duracao_min),
            "observacao": agendamento.observacao or "",
        },
    )


@router.post("/agenda/{agendamento_id}")
def gravar_edicao(
    request: Request,
    agendamento_id: int,
    dia: str = Form(""),
    inicio: str = Form(""),
    duracao_min: str = Form(str(DURACAO_PADRAO_MIN)),
    observacao: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Remarcar e mudar a anotacao. Quem vem nao muda aqui: trocar a pessoa de um
    horario e desmarcar um e marcar outro, e a auditoria tem de mostrar isso."""
    quando = _hora(inicio)
    if quando is None:
        raise HTTPException(status_code=400, detail="hora invalida")
    try:
        agendamento = remarcar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            agendamento_id=agendamento_id,
            dia=_dia(dia),
            inicio=quando,
            duracao_min=_duracao(duracao_min),
            observacao=observacao,
        )
    except NaoEncontrado as erro:
        raise HTTPException(status_code=404, detail="horario nao encontrado") from erro

    sessao.commit()
    return _voltar(agendamento.dia, len(conflitos_de(sessao, agendamento=agendamento)))


@router.post("/agenda/{agendamento_id}/situacao")
def mudar(
    agendamento_id: int,
    situacao: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        escolhida = SituacaoAgendamento(situacao)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail="situacao invalida") from erro

    try:
        agendamento = mudar_situacao(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            agendamento_id=agendamento_id,
            situacao=escolhida,
        )
    except NaoEncontrado as erro:
        raise HTTPException(status_code=404, detail="horario nao encontrado") from erro

    sessao.commit()
    return _voltar(agendamento.dia)


@router.post("/agenda/{agendamento_id}/excluir")
def apagar(
    agendamento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Foi engano. Quem desmarcou usa a situacao — o horario continua na tela."""
    try:
        agendamento = excluir(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            agendamento_id=agendamento_id,
        )
    except NaoEncontrado as erro:
        raise HTTPException(status_code=404, detail="horario nao encontrado") from erro

    sessao.commit()
    return _voltar(agendamento.dia)
