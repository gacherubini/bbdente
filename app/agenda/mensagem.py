"""O texto que sai para a paciente, e a barreira do que nunca entra nele.

Dado de saude e dado pessoal sensivel, e mensagem de WhatsApp e lida na tela de
bloqueio, no onibus, pelo marido, pela chefe. **"Consulta amanha as 14h" e um
compromisso; "canal no dente 36 amanha as 14h" e prontuario exposto na
notificacao do celular.**

A barreira e dupla e nenhuma das duas metades e decorativa:

1. **O tipo.** `renderizar()` recebe `ContextoDaMensagem`, um dataclass congelado
   de nove campos de texto — NUNCA um `dict`. Um `dict` deixaria alguem escrever
   `**vars(agendamento)` em 2027 e passar no review. Nao havendo campo, nao ha
   caminho.
2. **A allowlist positiva**, derivada dos campos do dataclass. Positiva, nunca
   negativa: lista do que e proibido esquece o campo criado depois.

Este modulo nao importa `models` de modulo nenhum, e ha teste que falha se
importar.
"""

import re
from dataclasses import dataclass, fields
from datetime import date, datetime, time

# Sem `locale`: locale e estado global do processo, depende de o sistema ter o
# pt_BR instalado e ja quebrou deploy de gente demais. Sao doze palavras.
DIAS_DA_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

_MARCADOR = re.compile(r"\{([a-z_]+)\}")


def _tem_chave_solta(texto: str) -> bool:
    """Uma chave que nao forma marcador — erro de digitacao dela.

    Tira os marcadores validos e ve o que sobrou. Regex com look-behind de
    largura variavel nao existe em Python, e a subtracao e mais facil de ler do
    que a alternativa que existiria.
    """
    sobra = _MARCADOR.sub("", texto)
    return "{" in sobra or "}" in sobra


class ModeloInvalido(ValueError):
    """O texto nao pode virar mensagem. Ninguem recebe."""


@dataclass(frozen=True)
class ContextoDaMensagem:
    """O UNICO caminho por onde dado chega numa mensagem de WhatsApp.

    Sao nove campos, todos texto, todos de agenda ou de clinica. Dado clinico
    (tratamento, dente, regiao, anamnese), dinheiro e documento NAO tem campo
    aqui e por isso nao tem como chegar la — inclusive `agendamento.observacao`,
    que e texto livre e e ONDE A INFORMACAO CLINICA VAZA: e la que vai estar
    escrito "canal 36" ou "avaliar extracao". Util na tela, proibida na mensagem.

    Dinheiro fica de fora por um segundo motivo alem da LGPD: mensagem com valor
    e cobranca, e cobranca por WhatsApp tem regra e custo de reputacao proprios.

    **Se voce veio aqui para acrescentar um campo, este paragrafo e o motivo de
    nao acrescentar.**
    """

    primeiro_nome: str
    nome: str
    dia: str
    dia_relativo: str
    hora: str
    clinica: str
    dentista: str
    endereco: str
    telefone_clinica: str


VARIAVEIS_PERMITIDAS = frozenset(campo.name for campo in fields(ContextoDaMensagem))


def validar(texto: str) -> list[str]:
    """As variaveis desconhecidas do texto, na ordem em que aparecem.

    Serve para a tela recusar o modelo NA ENTRADA, que e onde o erro custa menos
    — e e a unica barreira que impede alguem de escrever `{observacao}` achando
    que vai funcionar.
    """
    vistas: list[str] = []
    for nome in _MARCADOR.findall(texto):
        if nome not in VARIAVEIS_PERMITIDAS and nome not in vistas:
            vistas.append(nome)
    return vistas


def renderizar(texto: str, contexto: ContextoDaMensagem) -> str:
    """O texto com as variaveis trocadas, ou `ModeloInvalido`.

    Variavel desconhecida NAO vira mensagem, e variavel valida com valor vazio
    tambem nao: "Te espero em , amanha" e tao quebrado quanto "Ola
    {primeiro_nome}". Uma regra so, facil de testar e facil de lembrar.

    A clinica e a cara que aparece na mensagem — mandar texto quebrado e a
    assinatura do robo malfeito.
    """
    desconhecidas = validar(texto)
    if desconhecidas:
        raise ModeloInvalido(
            "não existe a variável " + ", ".join(desconhecidas)
        )
    if _tem_chave_solta(texto):
        raise ModeloInvalido("há uma chave { ou } sozinha no texto")

    valores = {campo.name: getattr(contexto, campo.name) for campo in fields(contexto)}
    usadas = set(_MARCADOR.findall(texto))
    vazias = sorted(nome for nome in usadas if not (valores[nome] or "").strip())
    if vazias:
        raise ModeloInvalido("sem valor para " + ", ".join(vazias))

    return _MARCADOR.sub(lambda achado: valores[achado.group(1)], texto)


def de_agendamento(
    *,
    nome: str,
    dia: date,
    inicio: time,
    agora: datetime,
    clinica: str,
    dentista: str,
    endereco: str,
    telefone_clinica: str,
) -> ContextoDaMensagem:
    """A unica fabrica de contexto.

    Recebe os campos de que precisa, **nunca o objeto `Agendamento` inteiro**: um
    objeto na assinatura convida a `**vars(...)` no futuro, e e assim que a
    observacao do horario chegaria na mensagem.

    `agora` entra por parametro porque `dia_relativo` e a distancia REAL no
    momento do envio, e nao a intencao de ontem — e o que faz um lembrete
    atrasado dizer "hoje" em vez de mentir "amanha".
    """
    nome = (nome or "").strip()
    return ContextoDaMensagem(
        # Capitalizado porque os 5.559 cadastros migrados do Dentalis estao TODOS
        # em maiuscula, e "Oi MARIA!" numa mensagem soa como grito — ou como
        # cobranca de banco, que e o que o lembrete nao pode parecer. O nome
        # completo, quando ela usar `{nome}`, sai como esta no cadastro.
        primeiro_nome=nome.split(" ")[0].capitalize() if nome else "",
        nome=nome,
        dia=f"{DIAS_DA_SEMANA[dia.weekday()]}, {dia.day} de {MESES[dia.month - 1]}",
        dia_relativo="hoje" if dia == agora.date() else "amanhã",
        hora=inicio.strftime("%H:%M"),
        clinica=clinica,
        dentista=dentista,
        endereco=endereco,
        telefone_clinica=telefone_clinica,
    )
