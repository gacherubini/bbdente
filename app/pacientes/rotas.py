from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual

# Convenio pertence ao catalogo: pedimos a lista pela service dele, nunca pelo model.
from app.catalogo.service import convenios
from app.pacientes.service import Filtro, buscar, contagens, criar, semelhantes
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/pacientes", response_class=HTMLResponse)
def listar(
    request: Request,
    q: str = Query(""),
    filtro: str = Query(Filtro.ATIVOS.value),
    escolher: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        escolhido = Filtro(filtro)
    except ValueError:
        escolhido = Filtro.ATIVOS  # filtro inventado na URL nao derruba a tela

    # Chegando pelo menu "Odontograma" sem paciente, a lista e um passo do odontograma:
    # a aba fica marcada la para o clique dar retorno visivel.
    veio_do_odontograma = escolher == "odontograma"

    return templates.TemplateResponse(
        request,
        "pacientes.html",
        {
            "aba": "odontograma" if veio_do_odontograma else "pacientes",
            "escolher_paciente": veio_do_odontograma,
            "termo": q,
            "filtro": escolhido,
            "filtros": list(Filtro),
            "linhas": buscar(
                sessao, clinica_id=usuario.clinica_id, termo=q, filtro=escolhido
            ),
            "numeros": contagens(sessao, clinica_id=usuario.clinica_id),
        },
    )


def _formulario(
    request: Request,
    sessao: Session,
    clinica_id: int,
    dados: dict[str, str],
    *,
    erro: str | None = None,
    parecidos: list | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "paciente_novo.html",
        {
            "aba": "pacientes",
            "dados": dados,
            "erro": erro,
            "parecidos": parecidos or [],
            "convenios": convenios(sessao, clinica_id=clinica_id),
        },
        status_code=200,
    )


@router.get("/pacientes/novo", response_class=HTMLResponse)
def novo(
    request: Request,
    nome: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """O nome ja vem preenchido com o termo que a busca nao achou."""
    dados = {"nome": nome, "telefone": "", "nascimento": "", "convenio_id": ""}
    return _formulario(request, sessao, usuario.clinica_id, dados)


@router.post("/pacientes/novo")
def cadastrar(
    request: Request,
    nome: str = Form(""),
    telefone: str = Form(""),
    nascimento: str = Form(""),
    convenio_id: str = Form(""),
    confirmar: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    dados = {
        "nome": nome,
        "telefone": telefone,
        "nascimento": nascimento,
        "convenio_id": convenio_id,
    }
    def formulario(**kw) -> HTMLResponse:
        return _formulario(request, sessao, usuario.clinica_id, dados, **kw)

    if not nome.strip():
        return formulario(erro="Digite o nome do paciente.")

    try:
        nasceu = date.fromisoformat(nascimento) if nascimento.strip() else None
    except ValueError:
        return formulario(erro="Data de nascimento inválida.")

    # Duplicata em base de 30 anos e o erro caro. Avisamos ANTES de gravar; quem
    # cadastra decide, porque so ela sabe se sao duas pessoas ou a mesma.
    if confirmar != "1":
        parecidos = semelhantes(sessao, clinica_id=usuario.clinica_id, nome=nome)
        if parecidos:
            return formulario(parecidos=parecidos)

    try:
        paciente = criar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            nome=nome,
            telefone=telefone.strip() or None,
            nascimento=nasceu,
            convenio_id=int(convenio_id) if convenio_id.strip() else None,
        )
    except ValueError as erro:
        sessao.rollback()
        return formulario(erro=str(erro))

    sessao.commit()
    # Quem cadastra esta com a pessoa na frente: o proximo passo e o odontograma.
    return RedirectResponse(f"/odontograma/{paciente.id}", status_code=303)
