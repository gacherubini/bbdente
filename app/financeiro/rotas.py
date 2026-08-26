"""A tela do Financeiro.

Os dados dos graficos vao embutidos na pagina, como no odontograma: a tela ja
nasce pronta, sem uma segunda ida ao servidor so para desenhar.
"""

import calendar
from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.financeiro.models import Parcela
from app.financeiro.service import (
    LIMITE_DE_COBRANCA,
    RecebimentoInvalido,
    a_receber,
    anos_com_movimento,
    producao_por_categoria,
    producao_por_convenio,
    producao_por_dia,
    quitar,
    recebido_por_mes,
    registrar_recebimento,
    resumo,
)
from app.pacientes.service import nomes_de
from app.shared.db import obter_sessao
from app.shared.formato import ValorInvalido, moeda, para_decimal
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
            "cobranca_truncada": len(linhas) == LIMITE_DE_COBRANCA,
            "limite_de_cobranca": LIMITE_DE_COBRANCA,
            "graficos": graficos,
        },
    )


FORMAS = ["Dinheiro", "Pix", "Cartão", "Cheque", "Boleto", "Transferência"]


def _tela_de_recebimento(
    request: Request,
    sessao: Session,
    clinica_id: int,
    *,
    paciente_id: int | None,
    parcela: Parcela | None,
    dados: dict[str, str],
    erro: str | None = None,
) -> HTMLResponse:
    alvo = parcela.paciente_id if parcela is not None else paciente_id
    nomes = nomes_de(sessao, clinica_id=clinica_id, paciente_ids=[alvo] if alvo else [])
    if alvo is None or alvo not in nomes:
        raise HTTPException(status_code=404, detail="paciente nao encontrado")
    return templates.TemplateResponse(
        request,
        "recebimento.html",
        {
            "aba": "financeiro",
            "paciente_id": alvo,
            "paciente": nomes[alvo],
            "parcela": parcela,
            "formas": FORMAS,
            "dados": dados,
            "erro": erro,
        },
        status_code=200,
    )


def _parcela(sessao: Session, clinica_id: int, parcela_id: int) -> Parcela:
    parcela = sessao.scalars(
        select(Parcela).where(
            Parcela.id == parcela_id,
            Parcela.clinica_id == clinica_id,
            Parcela.excluido_em.is_(None),
        )
    ).first()
    if parcela is None:
        raise HTTPException(status_code=404, detail="parcela nao encontrada")
    return parcela


@router.get("/financeiro/recebimento", response_class=HTMLResponse)
def tela_de_recebimento(
    request: Request,
    paciente_id: int | None = Query(None),
    parcela_id: int | None = Query(None),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    parcela = (
        _parcela(sessao, usuario.clinica_id, parcela_id) if parcela_id else None
    )
    return _tela_de_recebimento(
        request,
        sessao,
        usuario.clinica_id,
        paciente_id=paciente_id,
        parcela=parcela,
        dados={
            # Quitar uma parcela ja vem com o saldo preenchido: quase sempre e o
            # valor que a pessoa esta pagando.
            "valor": moeda(parcela.saldo) if parcela is not None else "",
            "data": date.today().isoformat(),
            "forma": "",
            "observacao": "",
        },
    )


@router.post("/financeiro/recebimento")
def gravar_recebimento(
    request: Request,
    paciente_id: str = Form(""),
    parcela_id: str = Form(""),
    valor: str = Form(""),
    data: str = Form(""),
    forma: str = Form(""),
    observacao: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    if not paciente_id.strip() and not parcela_id.strip():
        raise HTTPException(
            status_code=422, detail="diga de quem e o recebimento"
        )

    parcela = (
        _parcela(sessao, usuario.clinica_id, int(parcela_id)) if parcela_id.strip()
        else None
    )
    dados = {"valor": valor, "data": data, "forma": forma, "observacao": observacao}

    def formulario(mensagem: str) -> HTMLResponse:
        return _tela_de_recebimento(
            request,
            sessao,
            usuario.clinica_id,
            paciente_id=int(paciente_id) if paciente_id.strip() else None,
            parcela=parcela,
            dados=dados,
            erro=mensagem,
        )

    try:
        quantia = para_decimal(valor)
        quando = date.fromisoformat(data) if data.strip() else date.today()
    except ValorInvalido as erro:
        return formulario(str(erro))
    except ValueError:
        return formulario("Data inválida.")

    try:
        if parcela is not None:
            alvo = quitar(
                sessao,
                clinica_id=usuario.clinica_id,
                usuario_id=usuario.id,
                parcela_id=parcela.id,
                valor=quantia,
                quando=quando,
                forma=forma.strip() or None,
                observacao=observacao.strip() or None,
            )
        else:
            alvo = registrar_recebimento(
                sessao,
                clinica_id=usuario.clinica_id,
                usuario_id=usuario.id,
                paciente_id=int(paciente_id),
                valor=quantia,
                quando=quando,
                forma=forma.strip() or None,
                observacao=observacao.strip() or None,
            )
    except RecebimentoInvalido as erro:
        return formulario(str(erro))

    sessao.commit()
    return RedirectResponse(f"/odontograma/{alvo.paciente_id}", status_code=303)
