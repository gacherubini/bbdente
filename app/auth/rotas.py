from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.models import Clinica, Usuario
from app.auth.senha import TAMANHO_MINIMO_SENHA
from app.auth.service import SenhaRecusada, autenticar, renomear, trocar_senha
from app.auth.sessao import NOME_COOKIE, assinar, usuario_atual
from app.config import config
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


def _com_cookie(destino: str, usuario: Usuario) -> RedirectResponse:
    resposta = RedirectResponse(destino, status_code=303)
    resposta.set_cookie(
        NOME_COOKIE,
        assinar(usuario),
        httponly=True,
        samesite="lax",
        secure=config.cookie_seguro,
        max_age=config.sessao_horas * 3600,
    )
    return resposta


@router.get("/login", response_class=HTMLResponse)
def tela_de_login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@router.post("/login")
def entrar(
    request: Request,
    email: str = Form(""),
    senha: str = Form(""),
    sessao: Session = Depends(obter_sessao),
):
    usuario = autenticar(sessao, email, senha)
    if usuario is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "Email ou senha nao conferem."},
            status_code=200,
        )
    registrar(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        acao="ENTRAR",
        entidade="sessao",
        entidade_id=usuario.id,
        ip=request.client.host if request.client else None,
    )
    sessao.commit()
    return _com_cookie("/pacientes", usuario)


@router.post("/logout")
def sair():
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(NOME_COOKIE)
    return resposta


# --- perfil ----------------------------------------------------------------


def _tela_de_perfil(
    request: Request,
    sessao: Session,
    usuario: Usuario,
    *,
    erro_nome: str | None = None,
    erro_senha: str | None = None,
    recado: str | None = None,
    status: int = 200,
):
    # Clinica e do proprio modulo auth: ler o model aqui nao atravessa fronteira.
    clinica = sessao.get(Clinica, usuario.clinica_id)
    return templates.TemplateResponse(
        request,
        "perfil.html",
        {
            "aba": "perfil",
            "clinica": clinica,
            "minimo_senha": TAMANHO_MINIMO_SENHA,
            "erro_nome": erro_nome,
            "erro_senha": erro_senha,
            "recado": recado,
        },
        status_code=status,
    )


@router.get("/perfil", response_class=HTMLResponse)
def tela_de_perfil(
    request: Request,
    sessao: Session = Depends(obter_sessao),
    usuario: Usuario = Depends(usuario_atual),
):
    recado = request.query_params.get("ok")
    return _tela_de_perfil(request, sessao, usuario, recado=recado)


@router.post("/perfil")
def mudar_nome(
    request: Request,
    nome: str = Form(""),
    sessao: Session = Depends(obter_sessao),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        renomear(sessao, usuario, nome=nome)
    except ValueError as erro:
        sessao.rollback()
        return _tela_de_perfil(request, sessao, usuario, erro_nome=str(erro))
    sessao.commit()
    return RedirectResponse("/perfil?ok=nome", status_code=303)


@router.post("/perfil/senha")
def mudar_senha(
    request: Request,
    atual: str = Form(""),
    nova: str = Form(""),
    repetida: str = Form(""),
    sessao: Session = Depends(obter_sessao),
    usuario: Usuario = Depends(usuario_atual),
):
    try:
        trocar_senha(sessao, usuario, atual=atual, nova=nova, repetida=repetida)
    except SenhaRecusada as erro:
        sessao.rollback()
        return _tela_de_perfil(request, sessao, usuario, erro_senha=str(erro))
    sessao.commit()
    # A marca da senha mudou, entao TODO cookie emitido antes morreu — inclusive o
    # desta aba. Reemitir aqui e o que deixa quem trocou continuar trabalhando
    # enquanto derruba as outras sessoes.
    return _com_cookie("/perfil?ok=senha", usuario)
