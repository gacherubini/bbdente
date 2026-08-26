"""Sessao em cookie assinado. Sem tabela de sessao: um usuario so, uma clinica."""

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.config import config
from app.shared.db import obter_sessao

NOME_COOKIE = "bddente_sessao"
SALT = "bddente-sessao-v1"
MAX_IDADE_SEGUNDOS = config.sessao_horas * 3600

_serializador = URLSafeTimedSerializer(config.secret_key, salt=SALT)


def assinar(usuario_id: int) -> str:
    return _serializador.dumps({"u": usuario_id})


def ler(token: str) -> int | None:
    try:
        dados = _serializador.loads(token, max_age=MAX_IDADE_SEGUNDOS)
    except (BadSignature, SignatureExpired, TypeError):
        return None
    identificador = dados.get("u") if isinstance(dados, dict) else None
    return identificador if isinstance(identificador, int) else None


class PrecisaLogar(HTTPException):
    """Levantada quando nao ha sessao valida. O handler em main.py devolve um
    redirect para /login."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail="sessao ausente ou expirada")


def usuario_atual(request: Request, sessao: Session = Depends(obter_sessao)) -> Usuario:
    token = request.cookies.get(NOME_COOKIE, "")
    usuario_id = ler(token)
    if usuario_id is None:
        raise PrecisaLogar()
    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise PrecisaLogar()
    return usuario


def redirecionar_para_login(request: Request, exc: Exception) -> RedirectResponse:
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(NOME_COOKIE)
    return resposta
