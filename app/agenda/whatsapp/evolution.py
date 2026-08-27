"""O provedor que fala com o WhatsApp de verdade, pela Evolution API.

A Evolution roda como um **app separado no Fly**, e o BDDente fala com ela pela
rede privada (`http://bddente-whatsapp.internal:8080`) — nunca pela internet.
Isso importa: a Evolution nao tem login, so uma chave em cabecalho, e um endereco
publico dela seria uma porta para o WhatsApp da dentista. O `Dockerfile` daqui
fica inalterado de proposito; Baileys e Node, e Node nao entra nesta imagem.

**A regra inteira deste modulo cabe numa frase: nada aqui levanta excecao.**
Todo erro — rede caida, prazo estourado, 500 do outro lado, resposta que nao e
JSON — vira `Envio(ok=False, erro=...)`. O `despachar` nao tem `try` em volta da
chamada de rede, e nao deveria ter: uma paciente com numero ruim nao pode impedir
as outras sete de receberem.
"""

import logging

import httpx

from app.agenda.whatsapp import Conexao, Envio, EstadoDaConexao

registro = logging.getLogger(__name__)

# `lembrete.motivo` e curto, e o motivo passeia por tela, log e banco. Um HTML de
# 40 KB de proxy quebrado nao pode derrubar o gravamento do proprio erro.
TAMANHO_DO_MOTIVO = 120

# O vocabulario da Evolution, traduzido para o nosso. Estado desconhecido cai em
# DESCONECTADO por escolha: numa duvida entre "acho que da para enviar" e "acho
# que nao da", a resposta segura e a que nao manda mensagem.
ESTADOS = {
    "open": EstadoDaConexao.CONECTADO,
    "connecting": EstadoDaConexao.AGUARDANDO_QR,
    "close": EstadoDaConexao.DESCONECTADO,
}


def _curto(texto: str) -> str:
    texto = " ".join(str(texto).split())
    return texto[:TAMANHO_DO_MOTIVO]


def _numero_de(instancia: dict) -> str | None:
    """O numero conectado sai do JID (`5551999998888@s.whatsapp.net`).

    So os digitos antes do `@` e do `:` — o sufixo depois dos dois pontos e o
    numero do aparelho vinculado, que nao interessa a ninguem na tela.
    """
    jid = instancia.get("ownerJid") or instancia.get("owner") or ""
    numero = str(jid).split("@", 1)[0].split(":", 1)[0]
    return numero or None


def _qr_ou_erro(imagem: str | None) -> Conexao:
    """O QR vira data URI; a falta dele vira erro de tela, nunca excecao."""
    if not imagem:
        return Conexao(
            estado=EstadoDaConexao.DESCONECTADO, erro="resposta que não entendi"
        )
    if not imagem.startswith("data:"):
        imagem = f"data:image/png;base64,{imagem}"
    return Conexao(estado=EstadoDaConexao.AGUARDANDO_QR, imagem=imagem)


class ProvedorEvolution:
    """Uma instancia da Evolution, falando por um `httpx.Client` injetado.

    O cliente vem de fora para que o teste troque a rede por uma funcao — e e por
    isso que nenhum teste da suite abre socket.
    """

    def __init__(self, *, instancia: str, cliente: httpx.Client) -> None:
        self.instancia = instancia
        self.cliente = cliente

    @classmethod
    def de_configuracao(
        cls, *, url: str, api_key: str, instancia: str, timeout_s: float
    ) -> "ProvedorEvolution":
        """O unico lugar que monta o cliente de verdade.

        `httpx.Timeout(t)` poe o mesmo prazo em conectar, ler, escrever e esperar
        conexao no pool. Sem prazo, uma Evolution travada segura o relogio para
        sempre — e o relogio e uma thread so, entao a batida seguinte nunca chega
        e ninguem mais e avisado, em silencio.
        """
        return cls(
            instancia=instancia,
            cliente=httpx.Client(
                base_url=url.rstrip("/"),
                headers={"apikey": api_key, "Content-Type": "application/json"},
                timeout=httpx.Timeout(timeout_s),
            ),
        )

    def estado(self) -> EstadoDaConexao:
        try:
            resposta = self.cliente.get(f"/instance/connectionState/{self.instancia}")
            resposta.raise_for_status()
            bruto = resposta.json()["instance"]["state"]
        except Exception as problema:  # noqa: BLE001 — ver o docstring do modulo
            registro.warning("nao consegui ler o estado da Evolution: %s", _curto(problema))
            return EstadoDaConexao.DESCONECTADO
        return ESTADOS.get(bruto, EstadoDaConexao.DESCONECTADO)

    def conexao(self) -> Conexao:
        """O estado com o numero junto, para a tela dizer "Conectado como (51)...".

        Quem corre o risco de perder o proprio WhatsApp tem direito de ver na tela
        qual numero esta correndo esse risco. E o numero conectado nao vem daqui de
        dentro: vem da Evolution, que e quem sabe qual celular leu o QR.
        """
        try:
            resposta = self.cliente.get(f"/instance/connectionState/{self.instancia}")
            resposta.raise_for_status()
            instancia = resposta.json()["instance"]
        except Exception as problema:  # noqa: BLE001 — ver o docstring do modulo
            registro.warning("nao consegui ler o estado da Evolution: %s", _curto(problema))
            return Conexao(
                estado=EstadoDaConexao.DESCONECTADO,
                erro="não consegui falar com o WhatsApp",
            )

        estado = ESTADOS.get(instancia.get("state"), EstadoDaConexao.DESCONECTADO)
        return Conexao(estado=estado, numero=_numero_de(instancia))

    def parear(self) -> Conexao:
        """Pede um QR novo. E o unico caminho para (re)conectar.

        Chamado de novo enquanto a tela esta aberta: o QR do WhatsApp expira em
        segundos, entao "renova sozinho" e simplesmente perguntar de novo.

        **E o unico metodo que cria instancia**, e so quando ela nao existe. A
        Evolution sobe vazia: recem-instalada, ou recriada depois de um acidente
        com o volume, ela responde 404 a tudo ate alguem criar uma instancia.
        Se este botao apenas mostrasse o erro, o passo que falta seria um `curl`
        escondido num documento — feito uma vez, esquecido no dia em que a
        Evolution voltar vazia, com a dentista olhando uma tela que so diz que
        deu errado. Aqui, o caminho de recuperacao e o mesmo clique de sempre.

        Criar so no `parear` tambem e uma decisao: quem chega aqui e gente com o
        celular na mao. O relogio das 21h, se topar com uma Evolution vazia,
        falha e aparece na tela — nao inventa uma instancia sem sessao para
        depois nao conseguir enviar do mesmo jeito.
        """
        conexao = self._pedir_qr()
        if conexao is not None:
            return conexao

        # 404: a instancia nao existe la. Cria e tenta de novo.
        conexao = self._criar_instancia()
        if conexao is not None:
            return conexao

        return self._pedir_qr() or Conexao(
            estado=EstadoDaConexao.DESCONECTADO,
            erro="não consegui criar a conexão do WhatsApp",
        )

    def _pedir_qr(self) -> Conexao | None:
        """O QR, ou `None` quando a instancia ainda nao existe (404).

        `None` e a unica coisa que o `parear` trata de forma diferente: e a
        diferenca entre "deu erro" e "ainda nao existe", e so a segunda tem
        conserto automatico.
        """
        try:
            resposta = self.cliente.get(f"/instance/connect/{self.instancia}")
            if resposta.status_code == 404:
                return None
            resposta.raise_for_status()
            corpo = resposta.json()
        except Exception as problema:  # noqa: BLE001 — ver o docstring do modulo
            registro.warning("nao consegui pedir o QR: %s", _curto(problema))
            return Conexao(
                estado=EstadoDaConexao.DESCONECTADO, erro="não consegui pedir o QR"
            )

        # Ja conectada, a Evolution responde o estado em vez de um QR — e nao ha
        # QR nenhum para mostrar, o que e a resposta certa e nao um erro.
        if corpo.get("instance"):
            return Conexao(
                estado=ESTADOS.get(
                    corpo["instance"].get("state"), EstadoDaConexao.DESCONECTADO
                ),
                numero=_numero_de(corpo["instance"]),
            )

        return _qr_ou_erro(corpo.get("base64"))

    def _criar_instancia(self) -> Conexao | None:
        """Cria a instancia. Devolve o QR se ele vier junto, `None` se nao vier.

        `None` aqui nao e falha: e "criou, mas sem QR no corpo" — o QR se pede
        na chamada seguinte. Quem falha de verdade devolve `Conexao` com erro.
        """
        registro.info("criando a instancia %s na Evolution", self.instancia)
        try:
            resposta = self.cliente.post(
                "/instance/create",
                json={
                    "instanceName": self.instancia,
                    # Baileys explicito. O padrao da Evolution ja mudou de versao
                    # para versao, e a escolha entre Baileys e API oficial e a
                    # decisao mais cara deste modulo — ela nao pode depender de
                    # qual imagem subiu.
                    "integration": "WHATSAPP-BAILEYS",
                    "qrcode": True,
                },
            )
            resposta.raise_for_status()
            corpo = resposta.json()
        except Exception as problema:  # noqa: BLE001 — ver o docstring do modulo
            registro.warning("nao consegui criar a instancia: %s", _curto(problema))
            return Conexao(
                estado=EstadoDaConexao.DESCONECTADO,
                erro="não consegui criar a conexão do WhatsApp",
            )

        imagem = (corpo.get("qrcode") or {}).get("base64")
        return _qr_ou_erro(imagem) if imagem else None

    def desconectar(self) -> bool:
        """Derruba a sessao e joga a credencial fora, na Evolution.

        **E o unico lugar do sistema onde apagar e o certo**, e a excecao esta
        anotada: a regra do `excluido_em` protege dado de paciente, e credencial
        revogada nao e dado de paciente — e lixo que so serve para vazar.
        """
        try:
            resposta = self.cliente.delete(f"/instance/logout/{self.instancia}")
            resposta.raise_for_status()
        except Exception as problema:  # noqa: BLE001 — ver o docstring do modulo
            registro.warning("nao consegui desconectar: %s", _curto(problema))
            return False
        return True

    def enviar(self, *, numero: str, texto: str) -> Envio:
        try:
            resposta = self.cliente.post(
                f"/message/sendText/{self.instancia}",
                json={"number": numero, "text": texto},
            )
        except httpx.TimeoutException:
            # Prazo estourado e o caso ambiguo de verdade: pode ter chegado. Fica
            # FALHOU e ninguem reenvia sozinho — no maximo uma vez, nunca ao menos
            # uma vez. Uma pessoa decide, olhando a tela.
            return Envio(ok=False, erro="tempo esgotado falando com o WhatsApp")
        except httpx.HTTPError as problema:
            return Envio(ok=False, erro=_curto(f"rede: {type(problema).__name__}"))

        if resposta.status_code >= 400:
            # O corpo do erro fica de fora de proposito: ele pode devolver a
            # propria chave num eco de cabecalho, e este texto vai para
            # `lembrete.motivo`, para o log e para a tela. Segredo que passeia
            # por esses tres nao e mais segredo.
            return Envio(ok=False, erro=f"o WhatsApp respondeu {resposta.status_code}")

        try:
            id_externo = resposta.json()["key"]["id"]
        except Exception:  # noqa: BLE001 — resposta estranha nao e envio confirmado
            return Envio(ok=False, erro="resposta que nao entendi")

        return Envio(ok=True, id_externo=str(id_externo))
