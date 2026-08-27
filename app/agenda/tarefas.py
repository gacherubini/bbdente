"""O endpoint que o relogio chama.

Quem dispara nao tem sessao nem cookie: e maquina. Autenticado por um segredo em
cabecalho, comparado com `hmac.compare_digest` — comparacao de string comum
vaza o tamanho do prefixo acertado no tempo de resposta.

**Token errado responde 404, nunca 401.** Um 401 confirmaria que o endereco
existe; este endpoint nao se anuncia.
"""

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.agenda.lembretes import rodar
from app.agenda.whatsapp import Provedor
from app.agenda.whatsapp.fake import ProvedorFake
from app.config import config
from app.shared.db import obter_sessao

router = APIRouter()


def provedor_atual() -> Provedor:
    """Quem manda a mensagem de verdade.

    Enquanto a Task 17 nao entra, e o de mentira: o encanamento inteiro roda e
    fica testado sem uma mensagem real e sem o chip novo existir.
    """
    return ProvedorFake()


def _conferir(token: str | None) -> None:
    esperado = config.tarefas_token
    if not esperado or not hmac.compare_digest(token or "", esperado):
        raise HTTPException(status_code=404, detail="Not Found")


@router.post("/tarefas/lembretes")
def rodar_lembretes(
    x_tarefa_token: str | None = Header(default=None),
    sessao: Session = Depends(obter_sessao),
    provedor: Provedor = Depends(provedor_atual),
):
    """Uma batida do relogio, pedida de fora.

    Quem bate de verdade e o laco dentro do app (`agenda/relogio.py`), de 15 em
    15 minutos. Este endpoint e o gatilho de emergencia: serve para forcar uma
    passada sem esperar, e para conferir de fora que o encanamento responde.

    `POST` e nao `GET` para que um crawler nao dispare a agenda inteira. E o
    corpo da resposta so tem numeros: ele pode ir para o log de um servico de
    terceiro, e nome de paciente nao passeia por la.

    E idempotente por construcao (o `UNIQUE` do lembrete), entao pode ser chamado
    dez vezes seguidas sem mandar nada duas vezes.
    """
    _conferir(x_tarefa_token)

    # Relogio de parede da clinica: o container roda com TZ=America/Sao_Paulo, e
    # e por isso que `datetime.now()` sem fuso e o certo aqui (§4 do plano).
    resumo = rodar(
        sessao,
        clinica_id=config.clinica_id_padrao,
        agora=datetime.now(),
        provedor=provedor,
    )
    return {
        "reservados": resumo.reservados,
        "descartados": resumo.descartados,
        "enviados": resumo.enviados,
        "expirados": resumo.expirados,
        "falhados": resumo.falhados,
        "cancelados": resumo.cancelados,
        "esperando": resumo.esperando,
    }
