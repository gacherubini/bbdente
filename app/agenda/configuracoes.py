"""A tela de Configuracoes: a conexao, a chave geral e o texto da mensagem.

**Nao e aba do menu.** O menu lateral e a lista das coisas que ela faz com
paciente; configuracao e usada duas vezes por ano, quando o WhatsApp cai. E
configuracao nao se acha pelo menu, se acha pelo problema: o caminho principal e
a agenda mostrar o aviso e levar direto para ca. Sendo o aviso o caminho, o item
de menu seria redundante e so custaria atencao dos sete que importam.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.agenda.lembretes import (
    parede,
    previsao,
    rodar,
    ultimo_disparo,
    ultimos_envios,
)
from app.agenda.mensagem import (
    VARIAVEIS_PERMITIDAS,
    ContextoDaMensagem,
    ModeloInvalido,
    renderizar,
)
from app.agenda.service import (
    configuracao_de,
    modelo_da_vespera,
    salvar_configuracao,
    salvar_modelo,
)
from app.agenda.tarefas import provedor_atual
from app.agenda.whatsapp import EstadoDaConexao, Provedor
from app.agenda.whatsapp.fake import ProvedorFake
from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()

# A previa e feita com gente que nao existe. Previa e tela, e tela com nome de
# paciente vira print no grupo da familia.
EXEMPLO = ContextoDaMensagem(
    primeiro_nome="Fulana",
    nome="FULANA DE EXEMPLO",
    dia="quinta-feira, 3 de setembro",
    dia_relativo="amanhã",
    hora="14:00",
    clinica="Consultório",
    # Nome proprio, e nao "a dentista": o texto semeado diz "com a {dentista}",
    # e a previa sairia "com a a dentista".
    dentista="Dra. Fulana",
    endereco="Rua do Consultório, 100",
    telefone_clinica="(51) 3333-3333",
)

MOTIVOS = {
    "sem_permissao": "sem permissão de WhatsApp",
    "marcado_em_cima": "marcado depois da hora de avisar",
    "sem_numero": "sem número aproveitável",
    "avulso_recusou": "pediu para não receber",
    "numero_suspeito": "número suspeito",
    "teto_diario": "passou do teto do dia",
}


def _inteiro(bruto: str, padrao: int, minimo: int, maximo: int) -> int:
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        return padrao
    return valor if minimo <= valor <= maximo else padrao


def _tela(
    request: Request,
    sessao: Session,
    usuario: Usuario,
    provedor: Provedor,
    *,
    erro: str | None = None,
    texto: str | None = None,
) -> HTMLResponse:
    clinica_id = usuario.clinica_id
    configuracao = configuracao_de(sessao, clinica_id=clinica_id)
    modelo = modelo_da_vespera(sessao, clinica_id=clinica_id)
    agora = datetime.now()

    linhas = previsao(sessao, clinica_id=clinica_id, agora=agora)
    ultimo = ultimo_disparo(sessao, clinica_id=clinica_id)

    em_edicao = modelo.texto if texto is None else texto
    try:
        previa = renderizar(em_edicao, EXEMPLO)
    except ModeloInvalido as problema:
        previa = f"(o texto tem um erro: {problema})"

    return templates.TemplateResponse(
        request,
        "configuracoes.html",
        {
            "aba": "configuracoes",
            "configuracao": configuracao,
            "texto": em_edicao,
            "previa": previa,
            "variaveis": sorted(VARIAVEIS_PERMITIDAS),
            "erro": erro,
            "estado": provedor.estado().value,
            "conectado": provedor.estado() is EstadoDaConexao.CONECTADO,
            # Enquanto quem "envia" e o de mentira, a tela nao pode dizer
            # "conectado": ela estaria afirmando uma conexao que nao existe, e e
            # justamente essa a coisa que ela vai conferir quando desconfiar.
            "simulado": isinstance(provedor, ProvedorFake),
            "vao_receber": [linha for linha in linhas if linha.recebe],
            "nao_recebem": [linha for linha in linhas if not linha.recebe],
            "motivos": MOTIVOS,
            # So informacao. A faixa vermelha de "48h sem disparo" saiu junto
            # com o cron externo: o relogio mora dentro do app agora, entao
            # "o relogio parou" e a mesma coisa que "o app caiu" — e disso o
            # healthcheck do Fly ja cuida. Mantida, ela ficaria vermelha todo
            # feriado prolongado, e alarme que grita a toa se aprende a ignorar.
            "ultimo_envio": parede(ultimo) if ultimo else None,
            "envios": ultimos_envios(sessao, clinica_id=clinica_id),
            "hoje": date.today(),
        },
        status_code=200,
    )


@router.get("/configuracoes", response_class=HTMLResponse)
def tela(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
    provedor: Provedor = Depends(provedor_atual),
) -> HTMLResponse:
    return _tela(request, sessao, usuario, provedor)


@router.post("/configuracoes")
def gravar(
    request: Request,
    lembrete_ativo: str = Form(""),
    lembrete_horas_antes: str = Form(""),
    lembrete_teto_diario: str = Form(""),
    endereco: str = Form(""),
    telefone_clinica: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
    provedor: Provedor = Depends(provedor_atual),
):
    """A chave geral e os ajustes do lembrete.

    Nao ha mais "hora do disparo" para gravar: a hora de cada mensagem e a hora
    da consulta da paciente, menos a antecedencia. A antecedencia virou o unico
    controle de tempo da tela.
    """
    salvar_configuracao(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        ativo=lembrete_ativo == "1",
        horas_antes=_inteiro(lembrete_horas_antes, 24, 1, 168),
        teto_diario=_inteiro(lembrete_teto_diario, 20, 1, 200),
        endereco=endereco,
        telefone_clinica=telefone_clinica,
    )
    sessao.commit()
    return RedirectResponse("/configuracoes", status_code=303)


@router.post("/configuracoes/modelo")
def gravar_modelo(
    request: Request,
    texto: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
    provedor: Provedor = Depends(provedor_atual),
):
    try:
        salvar_modelo(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            texto=texto,
        )
    except ModeloInvalido as problema:
        return _tela(
            request, sessao, usuario, provedor, erro=str(problema), texto=texto
        )

    sessao.commit()
    return RedirectResponse("/configuracoes", status_code=303)


@router.post("/configuracoes/enviar-agora")
def enviar_agora(
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
    provedor: Provedor = Depends(provedor_atual),
):
    """O cinto de seguranca de quando o relogio falha.

    Chama exatamente o mesmo `rodar()` do relogio automatico — a mesma funcao,
    nao uma copia parecida — e e idempotente por construcao: clicar duas vezes
    nao manda duas vezes. E justamente por isso que este botao pode existir sem
    medo.

    Ele NAO adianta lembrete: manda o que ja venceu, e o que ainda nao venceu
    continua esperando a hora da paciente.
    """
    rodar(
        sessao,
        clinica_id=usuario.clinica_id,
        agora=datetime.now(),
        provedor=provedor,
    )
    return RedirectResponse("/configuracoes", status_code=303)
