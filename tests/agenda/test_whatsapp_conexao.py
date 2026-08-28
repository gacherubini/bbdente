"""Conectar e desconectar o WhatsApp pela tela (Task 18).

Três coisas estão sendo provadas aqui, e a primeira é a que não pode falhar
nunca: **nenhuma credencial de WhatsApp entra no banco do BDDente.** A sessão
mora dentro da Evolution, que é quem tem disco para ela. O que o BDDente guarda
é o que já aparece na tela — um estado, um número e uma hora.

As outras duas: desconectar é ato de gente e vai para a auditoria (sem o
conteúdo, que não existe); e a agenda avisa quando a conexão cai, lendo do banco
e não da rede — ela é a tela mais aberta do sistema e não depende do lembrete
para carregar.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.agenda import service
from app.agenda.tarefas import provedor_atual
from app.agenda.whatsapp import EstadoDaConexao
from app.agenda.whatsapp.evolution import ProvedorEvolution
from app.agenda.whatsapp.fake import ProvedorFake
from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.shared.db import obter_sessao


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="Consultório Dra. Kátia")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa-12", nome="K"
    )
    service.configuracao_de(sessao, clinica_id=clinica.id)
    sessao.flush()
    return {"clinica": clinica, "usuario": usuario}


@pytest.fixture
def provedor():
    return ProvedorFake()


def _evolution(resposta):
    """Um provedor de verdade com a rede trocada por uma função. Nenhum teste
    desta suíte abre socket."""
    return ProvedorEvolution(
        instancia="bddente",
        cliente=httpx.Client(
            base_url="http://bddente-whatsapp.internal:8080",
            transport=httpx.MockTransport(resposta),
        ),
    )


@pytest.fixture
def cliente(sessao, cenario, provedor):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    app.dependency_overrides[provedor_atual] = lambda: provedor
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


# --- a credencial nunca entra aqui -------------------------------------------

def test_nenhuma_coluna_do_banco_guarda_credencial_de_whatsapp(engine_teste):
    """Contrato de schema, e o mais importante do arquivo.

    A sessão do Baileys é um segredo que dá acesso à conta pessoal da mãe do dono
    do projeto. Ela vive na Evolution. Se um dia alguém acrescentar uma coluna
    para "guardar a sessão aqui, é mais prático", este teste reprova antes de o
    segredo existir em dois lugares.
    """
    suspeitas = ("sessao", "session", "credencial", "token", "qr", "creds")
    inspetor = inspect(engine_teste)
    for tabela in inspetor.get_table_names():
        for coluna in inspetor.get_columns(tabela):
            nome = coluna["name"].lower()
            if not nome.startswith("whatsapp") and "whatsapp" not in nome:
                continue
            assert not any(s in nome for s in suspeitas), f"{tabela}.{nome}"


def test_o_que_o_banco_guarda_da_conexao_e_so_estado_numero_e_hora(sessao, cenario):
    service.anotar_conexao(
        sessao,
        clinica_id=cenario["clinica"].id,
        estado=EstadoDaConexao.CONECTADO.value,
        numero="5551999990000",
    )
    sessao.flush()
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    assert configuracao.whatsapp_estado == "CONECTADO"
    assert configuracao.whatsapp_numero == "5551999990000"
    assert configuracao.whatsapp_visto_em is not None


def test_o_qr_nunca_e_gravado(cliente, sessao, cenario):
    """O QR é um convite de pareamento que vale segundos. Mostrar é o trabalho
    dele; guardar não serve para nada e cria um segredo a mais para vazar."""
    resposta = cliente.get("/configuracoes/whatsapp/qr")
    imagem = resposta.json()["imagem"]
    assert imagem  # o de mentira devolve um PNG mínimo

    guardado = sessao.execute(
        text("select * from configuracao_clinica where clinica_id = :c"),
        {"c": cenario["clinica"].id},
    ).mappings().one()
    assert imagem not in json.dumps(dict(guardado), default=str)


def test_a_auditoria_da_desconexao_nao_leva_payload(cliente, sessao, cenario):
    cliente.post("/configuracoes/whatsapp/desconectar")

    linha = (
        sessao.query(Auditoria)
        .filter_by(entidade="whatsapp", acao="DESCONECTAR")
        .one()
    )
    assert linha.usuario_id == cenario["usuario"].id
    assert linha.dados_depois == {"desconectado": True}
    # Uma linha que diz o fato e nada do conteúdo. Não há sessão para guardar, e
    # se houvesse seria justamente o que não podia ir para a auditoria.
    assert "sessao" not in json.dumps(linha.dados_depois or {})


# --- conectar e desconectar --------------------------------------------------

def test_pedir_o_qr_devolve_a_imagem_e_o_estado(cliente, provedor):
    corpo = cliente.get("/configuracoes/whatsapp/qr").json()
    assert corpo["estado"] == "AGUARDANDO_QR"
    assert corpo["conectado"] is False
    assert corpo["imagem"].startswith("data:image/")
    assert provedor.pareamentos == 1


def test_pedir_o_qr_de_novo_pede_de_novo_ao_provedor(cliente, provedor):
    """"Renova sozinho" é isto: o QR do WhatsApp expira em segundos, então
    renovar é perguntar outra vez. Não há cache no meio."""
    cliente.get("/configuracoes/whatsapp/qr")
    cliente.get("/configuracoes/whatsapp/qr")
    assert provedor.pareamentos == 2


def test_desconectar_derruba_a_sessao_e_volta_para_a_tela(cliente, provedor, sessao, cenario):
    resposta = cliente.post("/configuracoes/whatsapp/desconectar")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/configuracoes"
    assert provedor.desconexoes == 1

    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    assert configuracao.whatsapp_estado == "DESCONECTADO"


def test_o_estado_fica_anotado_so_de_abrir_a_tela(cliente, sessao, cenario):
    """A tela de Configurações é a única que pode pagar uma chamada de rede — e
    o que ela descobre é o que deixa a agenda avisar depois sem pagar nada."""
    cliente.get("/configuracoes")
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    assert configuracao.whatsapp_estado == "CONECTADO"
    assert configuracao.whatsapp_numero == "5551999990000"


def test_a_tela_mostra_o_numero_conectado(sessao, cenario):
    """Precisa de um provedor de verdade: com o de mentira a tela diz "nenhum
    WhatsApp conectado", e é o que ela deve dizer — afirmar uma conexão que não
    existe é justamente a coisa que ela vai conferir aqui quando desconfiar.

    Quem corre o risco de perder o próprio WhatsApp tem direito de ver na tela
    qual número está correndo esse risco.
    """
    provedor = _evolution(
        lambda pedido: httpx.Response(
            200,
            json=[
                {
                    "name": "bddente",
                    "connectionStatus": "open",
                    "ownerJid": "5551999998888:12@s.whatsapp.net",
                }
            ],
        )
    )
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    app.dependency_overrides[provedor_atual] = lambda: provedor
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        html = c.get("/configuracoes").text

    assert "5551999998888" in html
    # O sufixo do aparelho vinculado (`:12`) não interessa a ninguém na tela.
    assert "5551999998888:12" not in html
    assert "conectado" in html.lower()


def test_a_tela_nao_diz_conectado_para_sessao_sem_dono(sessao, cenario):
    """A regressão de 28/08/2026, no lugar onde ela apareceu.

    A Evolution ficou dois dias devolvendo `open` para um socket morto — ela
    grava o estado em memória ANTES de tentar escrever o dono, e o passo que
    escreve o dono foi o que estourou. A tela dizia "conectado", sem número
    nenhum ao lado, enquanto nenhum lembrete tinha como sair.

    **Sessão sem dono não é sessão**: ninguém leu o QR. A tela tem que oferecer
    Conectar, e não repetir a mentira que ela existe justamente para desmentir.
    """
    provedor = _evolution(
        lambda pedido: httpx.Response(
            200,
            json=[{"name": "bddente", "connectionStatus": "open", "ownerJid": None}],
        )
    )
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    app.dependency_overrides[provedor_atual] = lambda: provedor
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        html = c.get("/configuracoes").text

    assert "<b>conectado</b>" not in html.lower()
    assert "aguardando qr" in html.lower()
    # O botão oferece Conectar, não "Ler QR de novo" — não há QR lido para reler.
    assert "Ler QR de novo" not in html

    # E o que fica anotado é o que a agenda vai mostrar depois sem pagar rede.
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    assert configuracao.whatsapp_estado != "CONECTADO"


def test_sem_sessao_ninguem_pede_qr_nem_desconecta(sessao, provedor):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    app.dependency_overrides[provedor_atual] = lambda: provedor
    with TestClient(app, follow_redirects=False) as c:
        assert c.get("/configuracoes/whatsapp/qr").status_code == 303
        assert c.post("/configuracoes/whatsapp/desconectar").status_code == 303
    assert provedor.pareamentos == 0
    assert provedor.desconexoes == 0


# --- a faixa na agenda -------------------------------------------------------

def _agenda(cliente):
    return cliente.get("/agenda").text


def test_a_agenda_avisa_quando_a_conexao_caiu(cliente, sessao, cenario):
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    configuracao.lembrete_ativo = True
    service.anotar_conexao(
        sessao,
        clinica_id=cenario["clinica"].id,
        estado=EstadoDaConexao.DESCONECTADO.value,
    )
    sessao.flush()

    html = _agenda(cliente)
    assert "WhatsApp desconectou" in html
    assert "/configuracoes" in html


def test_a_agenda_nao_avisa_quando_esta_conectado(cliente, sessao, cenario):
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    configuracao.lembrete_ativo = True
    service.anotar_conexao(
        sessao,
        clinica_id=cenario["clinica"].id,
        estado=EstadoDaConexao.CONECTADO.value,
    )
    sessao.flush()

    assert "WhatsApp desconectou" not in _agenda(cliente)


def test_estado_nunca_visto_nao_vira_faixa(cliente, sessao, cenario):
    """NULO significa "ninguém nunca perguntou", e não "caiu". Alarme por falta
    de informação é alarme que grita à toa — e alarme que grita à toa se aprende
    a ignorar."""
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    configuracao.lembrete_ativo = True
    configuracao.whatsapp_estado = None
    sessao.flush()

    assert "WhatsApp desconectou" not in _agenda(cliente)


def test_com_o_lembrete_desligado_a_conexao_nao_vira_faixa(cliente, sessao, cenario):
    """Desligado, ninguém está esperando mensagem nenhuma — a conexão caída é
    irrelevante, e a linha amarela de "desligado" já diz o que importa. Duas
    faixas empilhadas dizendo coisas diferentes é como se para de ler faixa."""
    configuracao = service.configuracao_de(sessao, clinica_id=cenario["clinica"].id)
    configuracao.lembrete_ativo = False
    service.anotar_conexao(
        sessao,
        clinica_id=cenario["clinica"].id,
        estado=EstadoDaConexao.DESCONECTADO.value,
    )
    sessao.flush()

    html = _agenda(cliente)
    assert "WhatsApp desconectou" not in html
    assert "lembretes de WhatsApp desligados" in html


def test_a_agenda_nao_fala_com_o_provedor(cliente, sessao, cenario, provedor):
    """O contrato que sustenta a faixa: a agenda LÊ o último estado conhecido, e
    não pergunta a ninguém. Uma Evolution travada não pode deixar lenta a tela
    que ela usa o dia inteiro — a agenda não depende do lembrete para funcionar,
    nem para carregar."""

    class Explode:
        def estado(self):
            raise AssertionError("a agenda falou com o provedor")

        def conexao(self):
            raise AssertionError("a agenda falou com o provedor")

        def enviar(self, **kwargs):
            raise AssertionError("a agenda falou com o provedor")

        def parear(self):
            raise AssertionError("a agenda falou com o provedor")

        def desconectar(self):
            raise AssertionError("a agenda falou com o provedor")

    cliente.app.dependency_overrides[provedor_atual] = Explode
    assert cliente.get("/agenda").status_code == 200
    assert cliente.get("/agenda?vista=mes").status_code == 200


def test_o_extrato_mostra_a_hora_da_parede_da_clinica(cliente, sessao, cenario):
    """A regressão de 28/08/2026: a MESMA tela mostrava o MESMO envio em dois
    horários, 14:49 em cima e 17:49 embaixo.

    O `ultimo_envio` do topo passava por `parede()`; a tabela de baixo pegava o
    `enviado_em` cru do ORM e o formatava no template. As colunas são
    `timestamptz` e voltam em UTC, enquanto o consultório vive em UTC-3 — três
    horas de diferença, e a tela desmentindo a si mesma.

    Não dá para o template decidir fuso. Quem lê do banco converte, e é por isso
    que `ultimos_envios` passou a devolver a hora já pronta.
    """
    from datetime import UTC, date, datetime, time

    from app.agenda.lembretes import ultimos_envios
    from app.agenda.models import Lembrete, SituacaoLembrete, TipoLembrete
    from app.pacientes import service as pacientes

    paciente = pacientes.criar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome="MARIA SILVA",
        telefone="51999998888",
    )
    agendamento = service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        dia=date(2026, 8, 29),
        inicio=time(14, 0),
        paciente_id=paciente.id,
    )

    # 17:49 em UTC é 14:49 no relógio da parede do consultório.
    sessao.add(
        Lembrete(
            clinica_id=cenario["clinica"].id,
            agendamento_id=agendamento.id,
            tipo=TipoLembrete.VESPERA,
            situacao=SituacaoLembrete.ENVIADO,
            numero="5551999998888",
            agendado_para=datetime(2026, 8, 28, 17, 49, tzinfo=UTC),
            enviado_em=datetime(2026, 8, 28, 17, 49, tzinfo=UTC),
        )
    )
    sessao.flush()

    linha = ultimos_envios(sessao, clinica_id=cenario["clinica"].id)[0]
    assert linha.quando.hour == 14
    assert linha.quando.minute == 49

    html = cliente.get("/configuracoes").text
    assert "28/08 14:49" in html
    assert "28/08 17:49" not in html
