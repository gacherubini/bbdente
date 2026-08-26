"""A tela do Financeiro.

Os dados dos graficos vao embutidos na pagina, como no odontograma: a tela ja
nasce pronta, sem uma segunda ida ao servidor so para desenhar.
"""

import calendar
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.financeiro.service import (
    a_receber,
    anos_com_movimento,
    producao_por_categoria,
    producao_por_convenio,
    producao_por_dia,
    recebido_por_mes,
    resumo,
)
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# A lista de cobranca abre nos ultimos dois anos. Sao R$ 3,4 milhoes em aberto
# acumulados desde 1996 — uma lista que comeca la nunca chega no que da para
# cobrar hoje.
MESES_DE_COBRANCA = 24


def _inteiro(bruto: str, padrao: int, minimo: int, maximo: int) -> int:
    """Numero vindo da URL nunca derruba a tela: fora da faixa, vale o padrao."""
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        return padrao
    return valor if minimo <= valor <= maximo else padrao


def _recuar(quando: date, meses: int) -> date:
    total = quando.year * 12 + (quando.month - 1) - meses
    ano, mes = divmod(total, 12)
    dia = min(quando.day, calendar.monthrange(ano, mes + 1)[1])
    return date(ano, mes + 1, dia)


@router.get("/financeiro", response_class=HTMLResponse)
def tela(
    request: Request,
    ano: str = Query(""),
    mes: str = Query(""),
    cobranca: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    hoje = date.today()
    ano_escolhido = _inteiro(ano, hoje.year, 1995, hoje.year)
    mes_escolhido = _inteiro(mes, hoje.month, 1, 12)
    ultimo_dia = calendar.monthrange(ano_escolhido, mes_escolhido)[1]
    de = date(ano_escolhido, mes_escolhido, 1)
    ate = date(ano_escolhido, mes_escolhido, ultimo_dia)

    numeros = resumo(sessao, clinica_id=usuario.clinica_id, de=de, ate=ate)
    tudo = cobranca == "tudo"
    linhas = a_receber(
        sessao,
        clinica_id=usuario.clinica_id,
        ate=hoje,
        desde=date(1900, 1, 1) if tudo else _recuar(hoje, MESES_DE_COBRANCA),
    )

    graficos = {
        "recebido_por_mes": [
            str(v) for v in recebido_por_mes(
                sessao, clinica_id=usuario.clinica_id, ano=ano_escolhido
            )
        ],
        "recebido_ano_anterior": [
            str(v) for v in recebido_por_mes(
                sessao, clinica_id=usuario.clinica_id, ano=ano_escolhido - 1
            )
        ],
        "tratamentos_por_dia": producao_por_dia(
            sessao, clinica_id=usuario.clinica_id, ano=ano_escolhido, mes=mes_escolhido
        ),
        "por_categoria": [
            [nome, str(valor)]
            for nome, valor in producao_por_categoria(
                sessao, clinica_id=usuario.clinica_id, de=de, ate=ate
            )
        ],
        "por_convenio": [
            [nome, str(valor)]
            for nome, valor in producao_por_convenio(
                sessao, clinica_id=usuario.clinica_id, de=de, ate=ate
            )
        ],
        "meses": [m[:3] for m in MESES],
        "ano": ano_escolhido,
    }

    return templates.TemplateResponse(
        request,
        "financeiro.html",
        {
            "aba": "financeiro",
            "ano": ano_escolhido,
            "mes": mes_escolhido,
            "nome_do_mes": MESES[mes_escolhido - 1],
            "meses": MESES,
            "anos": anos_com_movimento(sessao, clinica_id=usuario.clinica_id),
            "numeros": numeros,
            # Mes vazio nao e erro: e o estado real de quem acabou de migrar o
            # historico e ainda nao lancou nada no mes corrente.
            "vazio": numeros.recebido == 0
            and numeros.produzido == 0
            and numeros.tratamentos == 0,
            "cobranca": linhas,
            "cobranca_completa": tudo,
            "graficos": graficos,
        },
    )
