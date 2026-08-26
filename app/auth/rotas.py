from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.service import autenticar
from app.auth.sessao import NOME_COOKIE, assinar
from app.config import config
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


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
    resposta = RedirectResponse("/pacientes", status_code=303)
    resposta.set_cookie(
        NOME_COOKIE,
        assinar(usuario.id),
        httponly=True,
        samesite="lax",
        secure=config.cookie_seguro,
        max_age=config.sessao_horas * 3600,
    )
    return resposta


@router.post("/logout")
def sair():
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(NOME_COOKIE)
    return resposta
