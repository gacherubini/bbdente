"""O provedor que fala com o WhatsApp de verdade — sem tocar a rede uma vez.

Todo teste daqui usa um transporte de mentira do httpx. Isso não é conveniência:
é o contrato da Task 17. Uma suíte que abre socket falha no avião, falha no CI
sem saída para a internet e, pior, um dia manda mensagem para alguém.

O que está sendo provado é sempre a mesma coisa por ângulos diferentes: **erro do
provedor vira `Envio(ok=False)`, nunca exceção.** Uma paciente com número ruim não
pode impedir as outras sete de receberem, e o `despachar` não tem `try` em volta
da chamada de rede — a barreira mora aqui dentro.
"""

from datetime import date, datetime, time

import httpx
import pytest

from app.agenda import lembretes, service
from app.agenda.models import Lembrete, SituacaoLembrete
from app.agenda.tarefas import provedor_atual
from app.agenda.whatsapp import EstadoDaConexao
from app.agenda.whatsapp.evolution import ProvedorEvolution
from app.agenda.whatsapp.fake import ProvedorFake
from app.auth.models import Clinica, Usuario
from app.pacientes import service as pacientes

CHAVE = "chave-secreta-de-teste"
URL = "http://bddente-whatsapp.internal:8080"


def _provedor(resposta, *, instancia="bddente"):
    """Um ProvedorEvolution com a rede trocada por uma função.

    `resposta` recebe o `httpx.Request` e devolve um `httpx.Response` — ou levanta,
    que é como se simula a rede caindo.
    """
    cliente = httpx.Client(
        base_url=URL,
        transport=httpx.MockTransport(resposta),
        headers={"apikey": CHAVE},
        timeout=httpx.Timeout(10.0),
    )
    return ProvedorEvolution(instancia=instancia, cliente=cliente)


def _ok(corpo, status=200):
    return lambda pedido: httpx.Response(status, json=corpo)


DONO = "5551999998888:12@s.whatsapp.net"


def _linha(**campos):
    """Uma linha do `fetchInstances`, como a Evolution devolve: uma lista."""
    base = {"name": "bddente", "connectionStatus": "open", "ownerJid": DONO}
    return _ok([{**base, **campos}])


# --- a escolha do provedor ---------------------------------------------------

def test_o_padrao_e_o_de_mentira():
    """Ninguém liga o WhatsApp de verdade por esquecimento de configurar."""
    assert isinstance(provedor_atual(), ProvedorFake)


def test_a_configuracao_escolhe_o_provedor(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "whatsapp_provedor", "evolution")
    monkeypatch.setattr(config, "evolution_url", URL)
    monkeypatch.setattr(config, "evolution_api_key", CHAVE)

    assert isinstance(provedor_atual(), ProvedorEvolution)


def test_provedor_desconhecido_cai_no_de_mentira(monkeypatch):
    """Errar o nome da variável não pode ligar nem derrubar nada."""
    from app.config import config

    monkeypatch.setattr(config, "whatsapp_provedor", "evoluton")
    assert isinstance(provedor_atual(), ProvedorFake)


def test_evolution_sem_chave_nao_sobe(monkeypatch):
    """Sem `AUTHENTICATION_API_KEY` a instância aceitaria qualquer um. Se
    alguém pedir `evolution` sem o segredo, é engano — e engano de segredo
    ausente vira o de mentira, não uma conexão aberta."""
    from app.config import config

    monkeypatch.setattr(config, "whatsapp_provedor", "evolution")
    monkeypatch.setattr(config, "evolution_api_key", "")
    assert isinstance(provedor_atual(), ProvedorFake)


# --- estado ------------------------------------------------------------------

@pytest.mark.parametrize(
    "estado_evolution,esperado",
    [
        ("open", EstadoDaConexao.CONECTADO),
        ("connecting", EstadoDaConexao.AGUARDANDO_QR),
        ("close", EstadoDaConexao.DESCONECTADO),
        ("qualquer-coisa-nova", EstadoDaConexao.DESCONECTADO),
    ],
)
def test_o_estado_traduz_o_vocabulario_da_evolution(estado_evolution, esperado):
    """Com dono no lugar — sem ele, `open` não é conexão, e isso tem teste próprio
    lá embaixo."""
    provedor = _provedor(_linha(connectionStatus=estado_evolution))
    assert provedor.estado() is esperado


def test_rede_caida_e_desconectado_e_nao_excecao():
    def cai(pedido):
        raise httpx.ConnectError("sem rota", request=pedido)

    assert _provedor(cai).estado() is EstadoDaConexao.DESCONECTADO


def test_resposta_sem_json_e_desconectado():
    provedor = _provedor(lambda pedido: httpx.Response(200, text="<html>opa</html>"))
    assert provedor.estado() is EstadoDaConexao.DESCONECTADO


def test_o_estado_pergunta_pela_instancia_certa():
    vistos = []

    def anotar(pedido):
        vistos.append(str(pedido.url))
        return httpx.Response(200, json=[{"connectionStatus": "open", "ownerJid": DONO}])

    _provedor(anotar, instancia="katia").estado()
    assert vistos == [f"{URL}/instance/fetchInstances?instanceName=katia"]


# --- envio -------------------------------------------------------------------

def test_envio_bem_sucedido_devolve_o_id_externo():
    provedor = _provedor(_ok({"key": {"id": "3EB0C767D"}}, status=201))
    envio = provedor.enviar(numero="5551999998888", texto="Oi Maria!")
    assert envio.ok
    assert envio.id_externo == "3EB0C767D"
    assert envio.erro is None


def test_o_envio_manda_numero_e_texto_para_a_rota_certa():
    vistos = []

    def anotar(pedido):
        import json

        vistos.append((str(pedido.url), json.loads(pedido.content)))
        return httpx.Response(201, json={"key": {"id": "x"}})

    _provedor(anotar, instancia="katia").enviar(numero="5551999998888", texto="Oi!")
    url, corpo = vistos[0]
    assert url == f"{URL}/message/sendText/katia"
    assert corpo["number"] == "5551999998888"
    assert corpo["text"] == "Oi!"


def test_o_envio_leva_a_chave_no_cabecalho():
    vistos = []

    def anotar(pedido):
        vistos.append(pedido.headers.get("apikey"))
        return httpx.Response(201, json={"key": {"id": "x"}})

    _provedor(anotar).enviar(numero="5551999998888", texto="Oi!")
    assert vistos == [CHAVE]


def test_rede_caida_no_envio_vira_envio_com_erro():
    def cai(pedido):
        raise httpx.ConnectError("sem rota", request=pedido)

    envio = _provedor(cai).enviar(numero="5551999998888", texto="Oi!")
    assert envio.ok is False
    assert envio.erro


def test_timeout_no_envio_vira_envio_com_erro():
    def demora(pedido):
        raise httpx.ReadTimeout("demorou", request=pedido)

    envio = _provedor(demora).enviar(numero="5551999998888", texto="Oi!")
    assert envio.ok is False
    assert "tempo" in envio.erro.lower() or "timeout" in envio.erro.lower()


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 502])
def test_status_de_erro_vira_envio_com_erro(status):
    provedor = _provedor(_ok({"message": "deu ruim"}, status=status))
    envio = provedor.enviar(numero="5551999998888", texto="Oi!")
    assert envio.ok is False
    assert str(status) in envio.erro


def test_resposta_sem_json_no_envio_vira_envio_com_erro():
    provedor = _provedor(lambda pedido: httpx.Response(201, text="nao e json"))
    envio = provedor.enviar(numero="5551999998888", texto="Oi!")
    assert envio.ok is False


def test_o_erro_nunca_carrega_a_chave_da_api():
    """O motivo vai para `lembrete.motivo`, para o log e para a tela. Segredo
    que passeia por esses três não é mais segredo."""
    provedor = _provedor(_ok({"apikey": CHAVE, "message": "invalido"}, status=401))
    envio = provedor.enviar(numero="5551999998888", texto="Oi!")
    assert CHAVE not in (envio.erro or "")


def test_o_motivo_cabe_na_coluna():
    """`lembrete.motivo` é curto. Um HTML de 40 KB de proxy quebrado não pode
    derrubar o gravamento do próprio erro."""
    provedor = _provedor(lambda pedido: httpx.Response(502, text="x" * 40_000))
    envio = provedor.enviar(numero="5551999998888", texto="Oi!")
    assert envio.ok is False
    assert len(envio.erro) <= 120


# --- toda chamada tem prazo --------------------------------------------------

def test_o_cliente_nasce_com_timeout_explicito():
    """Sem prazo, uma Evolution travada segura o relógio para sempre — e o
    relógio é uma thread só. A batida seguinte nunca chega."""
    provedor = ProvedorEvolution.de_configuracao(
        url=URL, api_key=CHAVE, instancia="bddente", timeout_s=7.5
    )
    assert provedor.cliente.timeout.connect == 7.5
    assert provedor.cliente.timeout.read == 7.5
    assert provedor.cliente.timeout.write == 7.5
    assert provedor.cliente.timeout.pool == 7.5


# --- integrado com o despacho ------------------------------------------------

CONSULTA = date(2026, 9, 1)
AGORA = datetime(2026, 8, 31, 14, 0)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="Consultório Dra. Kátia")
    sessao.add(clinica)
    sessao.flush()
    usuario = Usuario(
        clinica_id=clinica.id, nome="Dra. Kátia", email="k@l", senha_hash="x"
    )
    sessao.add(usuario)
    sessao.flush()
    configuracao = service.configuracao_de(sessao, clinica_id=clinica.id)
    configuracao.lembrete_ativo = True
    configuracao.endereco = "Rua X, 100"
    configuracao.telefone_clinica = "(51) 3333-3333"
    service.modelo_da_vespera(sessao, clinica_id=clinica.id)
    sessao.flush()
    return {"clinica": clinica, "usuario": usuario}


def _marcar(sessao, cenario, nome, telefone):
    paciente = pacientes.criar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome=nome,
        telefone=telefone,
    )
    pacientes.definir_consentimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=paciente.id,
        aceita=True,
    )
    return service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        dia=CONSULTA,
        inicio=time(14, 0),
        paciente_id=paciente.id,
    )


def _rodar(sessao, cenario, provedor):
    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=AGORA)
    return lembretes.despachar(
        sessao,
        clinica_id=cenario["clinica"].id,
        agora=AGORA,
        provedor=provedor,
        pausar=lambda: None,
    )


def test_a_rede_caindo_deixa_falhou_e_nao_derruba_o_disparo(sessao, cenario):
    _marcar(sessao, cenario, "MARIA SILVA", "51999998888")

    # A conexão está de pé; é o envio que cai no meio. É o caso diferente de
    # "desconectado": aqui a mensagem PODE ter chegado, e é por isso que fica
    # FALHOU e ninguém reenvia sozinho.
    def cai_no_envio(pedido):
        if "fetchInstances" in str(pedido.url):
            return httpx.Response(200, json=[{"connectionStatus": "open", "ownerJid": DONO}])
        raise httpx.ConnectError("sem rota", request=pedido)

    resumo = _rodar(sessao, cenario, _provedor(cai_no_envio))

    assert resumo.falhados == 1
    assert resumo.enviados == 0
    lembrete = sessao.query(Lembrete).one()
    assert lembrete.situacao is SituacaoLembrete.FALHOU
    assert lembrete.motivo != "desconectado"
    assert lembrete.tentativas == 1


def test_uma_falha_de_rede_no_meio_nao_impede_as_seguintes(sessao, cenario):
    for indice in range(3):
        _marcar(sessao, cenario, f"PACIENTE {indice}", f"5199999{indice}888")

    chamadas = {"n": 0}

    def falha_na_segunda(pedido):
        if "fetchInstances" in str(pedido.url):
            return httpx.Response(200, json=[{"connectionStatus": "open", "ownerJid": DONO}])
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise httpx.ConnectError("sem rota", request=pedido)
        return httpx.Response(201, json={"key": {"id": f"id-{chamadas['n']}"}})

    resumo = _rodar(sessao, cenario, _provedor(falha_na_segunda))

    assert resumo.enviados == 2
    assert resumo.falhados == 1


def test_desconectado_nao_tenta_enviar(sessao, cenario):
    """Task 18: sem sessão de WhatsApp, tudo vira FALHOU/desconectado e nenhuma
    chamada de envio sai — insistir com o socket caído é o padrão que queima o
    número."""
    _marcar(sessao, cenario, "MARIA SILVA", "51999998888")

    envios = {"n": 0}

    def responder(pedido):
        if "fetchInstances" in str(pedido.url):
            return httpx.Response(200, json=[{"connectionStatus": "close", "ownerJid": None}])
        envios["n"] += 1
        return httpx.Response(201, json={"key": {"id": "x"}})

    resumo = _rodar(sessao, cenario, _provedor(responder))

    assert envios["n"] == 0
    assert resumo.enviados == 0
    assert resumo.falhados == 1
    assert sessao.query(Lembrete).one().motivo == "desconectado"


# --- a instância nasce sozinha ----------------------------------------------
#
# A Evolution sobe vazia: até alguém criar uma instância, `/instance/connect`
# responde 404 para sempre. Sem isto, o botão "Conectar" mostraria um erro que
# ninguém consegue resolver pela tela — e o passo que falta seria um `curl`
# escondido num documento, feito uma vez e esquecido no dia em que a Evolution
# for recriada. O caminho de recuperação tem de caber no mesmo clique.

QR = "iVBORw0KGgoAAAANSUhEUg"

# O que a Evolution responde quando a instância não existe.
NAO_EXISTE = {"status": 404, "error": "Not Found", "response": {"message": ["Instance"]}}


def test_a_instancia_nasce_no_primeiro_conectar():
    pedidos = []

    def responder(pedido):
        pedidos.append((pedido.method, str(pedido.url)))
        if pedido.method == "POST":
            return httpx.Response(201, json={"qrcode": {"base64": QR}})
        return httpx.Response(404, json=NAO_EXISTE)

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.AGUARDANDO_QR
    assert conexao.imagem.startswith("data:image/png;base64,")
    assert ("POST", f"{URL}/instance/create") in pedidos


def test_a_instancia_criada_leva_o_nome_configurado():
    """O nome vem da configuração, e não de uma constante: é ele que amarra o
    BDDente à instância certa quando houver mais de uma na mesma Evolution."""
    import json

    corpos = []

    def responder(pedido):
        if pedido.method == "POST":
            corpos.append(json.loads(pedido.content))
            return httpx.Response(201, json={"qrcode": {"base64": QR}})
        return httpx.Response(404, json=NAO_EXISTE)

    _provedor(responder, instancia="katia").parear()

    assert corpos[0]["instanceName"] == "katia"
    assert corpos[0]["integration"] == "WHATSAPP-BAILEYS"


def test_instancia_que_ja_existe_nao_e_criada_de_novo():
    """Criar por cima derrubaria a sessão de quem já está conectada."""
    metodos = []

    def responder(pedido):
        metodos.append(pedido.method)
        return httpx.Response(200, json={"base64": QR})

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.AGUARDANDO_QR
    assert "POST" not in metodos


def test_criacao_sem_qr_no_corpo_pede_o_qr_de_novo():
    """Nem toda versão devolve o QR junto da criação. Se não vier, a instância
    já existe — e pedir de novo é o caminho normal, não um erro."""
    gets = {"n": 0}

    def responder(pedido):
        if pedido.method == "POST":
            return httpx.Response(201, json={"instance": {"instanceName": "bddente"}})
        gets["n"] += 1
        if gets["n"] == 1:
            return httpx.Response(404, json=NAO_EXISTE)
        return httpx.Response(200, json={"base64": QR})

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.AGUARDANDO_QR
    assert conexao.imagem.endswith(QR)
    assert gets["n"] == 2


def test_falha_ao_criar_a_instancia_vira_erro_na_tela_e_nao_excecao():
    def responder(pedido):
        if pedido.method == "POST":
            return httpx.Response(500, json={"message": "deu ruim"})
        return httpx.Response(404, json=NAO_EXISTE)

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.DESCONECTADO
    assert conexao.erro
    assert conexao.imagem is None


def test_rede_caida_na_criacao_vira_erro_na_tela():
    def responder(pedido):
        if pedido.method == "POST":
            raise httpx.ConnectError("sem rota", request=pedido)
        return httpx.Response(404, json=NAO_EXISTE)

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.DESCONECTADO
    assert conexao.erro


def test_so_o_conectar_cria_instancia():
    """Contrato: envio e leitura de estado nunca criam nada. Criar instância é
    consequência de alguém clicar em Conectar, com o celular na mão — nunca de
    um relógio batendo às 21h contra uma Evolution que foi recriada vazia."""
    urls = []

    def responder(pedido):
        urls.append(str(pedido.url))
        return httpx.Response(404, json=NAO_EXISTE)

    provedor = _provedor(responder)
    provedor.estado()
    provedor.conexao()
    provedor.enviar(numero="5551999998888", texto="Oi!")

    assert not any("/instance/create" in url for url in urls)


# --- a conexão: só é conexão quando tem dono ---------------------------------
#
# O `connectionState` da Evolution lê uma variável em MEMÓRIA, e essa variável
# mente. Em 28/08/2026 a instância desta clínica ficou presa em "open" com o
# socket morto: o Baileys emitiu `connection: 'open'` sem `client.user`, a
# Evolution gravou `stateConnection = {state: 'open'}` e só ENTÃO estourou em
# `this.client.user.id` — antes de persistir qualquer coisa. A tela passou dois
# dias dizendo "conectado" para uma sessão que não existia.
#
# Por isso a conexão passou a ser lida do `fetchInstances`, que vem do Postgres
# da Evolution, e por isso ela exige `ownerJid`: o `connectionStatus` do schema
# dela nasce `open` por padrão (`@default(open)`), então "open" sozinho não prova
# nada. **Sessão sem dono não é sessão** — ninguém leu o QR.

def test_open_sem_dono_nao_e_conectado():
    """O caso exato do 28/08: `open` gravado antes do crash, sem dono nenhum."""
    conexao = _provedor(_linha(ownerJid=None)).conexao()
    assert conexao.estado is not EstadoDaConexao.CONECTADO
    assert conexao.estado is EstadoDaConexao.AGUARDANDO_QR
    assert conexao.numero is None


def test_o_estado_tambem_exige_dono():
    """É o `estado()` que libera o disparo. Se ele acreditar no `open` vazio, o
    relógio das 21h tenta mandar para sete pacientes por um socket morto."""
    assert _provedor(_linha(ownerJid=None)).estado() is not EstadoDaConexao.CONECTADO


def test_open_com_dono_e_conectado_e_traz_o_numero():
    conexao = _provedor(_linha()).conexao()
    assert conexao.estado is EstadoDaConexao.CONECTADO
    # O sufixo do aparelho vinculado (`:12`) não interessa a ninguém na tela.
    assert conexao.numero == "5551999998888"


def test_a_conexao_le_do_banco_da_evolution_e_nao_da_memoria():
    vistos = []

    def anotar(pedido):
        vistos.append(str(pedido.url))
        return httpx.Response(200, json=[{"connectionStatus": "open", "ownerJid": DONO}])

    _provedor(anotar, instancia="katia").conexao()
    assert vistos == [f"{URL}/instance/fetchInstances?instanceName=katia"]


def test_instancia_que_nao_existe_e_desconectado():
    """A Evolution recriada vazia responde 404. Isso é 'não dá para enviar',
    não uma exceção — e o conserto é o mesmo clique de Conectar de sempre."""
    conexao = _provedor(_ok({"status": 404, "error": "Not Found"}, status=404)).conexao()
    assert conexao.estado is EstadoDaConexao.DESCONECTADO


def test_lista_vazia_e_desconectado():
    assert _provedor(_ok([])).conexao().estado is EstadoDaConexao.DESCONECTADO


def test_conectar_nao_acredita_no_ja_conectado_sem_dono():
    """A mesma mentira, na outra porta — e foi por esta que a dentista passou.

    `/instance/connect` responde "já está conectada" lendo a MESMA variável em
    memória do `connectionState`. Com ela presa em `open`, clicar em Conectar
    devolvia "conectado" e QR nenhum: não havia como sair, porque o único botão
    que consertaria já achava que estava tudo bem.

    Então `parear` confere no banco da Evolution antes de acreditar. Sem dono,
    derruba a sessão fantasma e pede o QR de novo — o mesmo conserto automático
    que ele já fazia para a instância que não existe. Quem chega aqui é gente com
    o celular na mão, e o caminho de recuperação tem de ser o clique de sempre.
    """
    urls = []

    def responder(pedido):
        url = str(pedido.url)
        urls.append(f"{pedido.method} {url}")
        if "fetchInstances" in url:
            return httpx.Response(200, json=[{"connectionStatus": "open", "ownerJid": None}])
        if "/instance/logout/" in url:
            return httpx.Response(200, json={"status": "SUCCESS"})
        # `/instance/connect`, mentindo que já está conectada.
        if not any("/instance/logout/" in visto for visto in urls):
            return httpx.Response(200, json={"instance": {"state": "open"}})
        return httpx.Response(200, json={"base64": QR})

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.AGUARDANDO_QR
    assert conexao.imagem.endswith(QR)
    assert any("DELETE" in visto and "/instance/logout/" in visto for visto in urls)


def test_conectar_respeita_o_ja_conectado_de_verdade():
    """A trava não pode virar um logout gratuito: com dono no banco, a sessão é
    real e derrubá-la obrigaria a dentista a ler o QR à toa."""
    urls = []

    def responder(pedido):
        urls.append(str(pedido.url))
        if "fetchInstances" in str(pedido.url):
            return httpx.Response(200, json=[{"connectionStatus": "open", "ownerJid": DONO}])
        return httpx.Response(200, json={"instance": {"state": "open"}})

    conexao = _provedor(responder).parear()

    assert conexao.estado is EstadoDaConexao.CONECTADO
    assert conexao.numero == "5551999998888"
    assert not any("logout" in url for url in urls)


def test_conectar_nao_derruba_sessao_real_no_meio_da_reconexao():
    """A trava tem um gatilho estreito de propósito: **dono nenhum no banco**.

    Derrubar é apagar credencial. A Evolution põe `open` na memória e só grava o
    banco depois de ir buscar a foto do perfil — nessa janela o banco ainda diz
    `connecting`, mas o `ownerJid` de um pareamento anterior está lá, e a sessão
    é real. Derrubar ali custaria à dentista um QR novo por nada.
    """
    urls = []

    def responder(pedido):
        urls.append(str(pedido.url))
        if "fetchInstances" in str(pedido.url):
            return httpx.Response(
                200, json=[{"connectionStatus": "connecting", "ownerJid": DONO}]
            )
        return httpx.Response(200, json={"instance": {"state": "open"}})

    conexao = _provedor(responder).parear()

    assert not any("logout" in url for url in urls)
    assert conexao.numero == "5551999998888"
