"""Sessao em cookie assinado. Sem tabela de sessao: um usuario so, uma clinica.

O cookie carrega duas coisas: quem e (`u`) e a marca da senha em vigor quando ele
foi emitido (`v`). A marca e conferida a cada pedido, e e o que faz trocar a senha
derrubar as sessoes antigas sem precisar de tabela de sessao.
"""

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.senha import impressao
from app.config import config
from app.shared.db import obter_sessao

NOME_COOKIE = "bddente_sessao"
SALT = "bddente-sessao-v1"
MAX_IDADE_SEGUNDOS = config.sessao_horas * 3600

_serializador = URLSafeTimedSerializer(config.secret_key, salt=SALT)


def assinar(usuario: Usuario) -> str:
    return _serializador.dumps({"u": usuario.id, "v": impressao(usuario.senha_hash)})


def ler(token: str) -> tuple[int, str] | None:
    """(id do usuario, marca da senha) — ou None se o token nao presta.

    Token sem marca e token de antes desta mudanca: recusado, e a pessoa entra de
    novo. Aceitar seria manter aberto exatamente o buraco que a marca fecha.
    """
    try:
        dados = _serializador.loads(token, max_age=MAX_IDADE_SEGUNDOS)
    except (BadSignature, SignatureExpired, TypeError):
        return None
    if not isinstance(dados, dict):
        return None
    identificador, marca = dados.get("u"), dados.get("v")
    if not isinstance(identificador, int) or not isinstance(marca, str):
        return None
    return identificador, marca


class PrecisaLogar(HTTPException):
    """Levantada quando nao ha sessao valida. O handler em main.py devolve um
    redirect para /login."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail="sessao ausente ou expirada")


def usuario_atual(request: Request, sessao: Session = Depends(obter_sessao)) -> Usuario:
    cracha = ler(request.cookies.get(NOME_COOKIE, ""))
    if cracha is None:
        raise PrecisaLogar()
    usuario_id, marca = cracha
    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise PrecisaLogar()
    if impressao(usuario.senha_hash) != marca:
        raise PrecisaLogar()
    # O layout mostra em nome de quem se esta gravando, em toda tela. Guardar aqui
    # e o que permite ao template ler isso sem que cada rota tenha de repassar o
    # usuario — e sem que alguem esqueca de repassar em uma delas.
    request.state.usuario = usuario
    return usuario


def redirecionar_para_login(request: Request, exc: Exception) -> RedirectResponse:
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(NOME_COOKIE)
    return resposta
