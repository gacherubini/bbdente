import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def cliente_logado(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    sessao.add(
        Paciente(
            clinica_id=clinica.id, codigo_legado="0001/PT",
            nome="Claudia Moreira Sant'Ana",
            revisar_motivo=["data_suspeita", "telefone_incompleto"],
        )
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def test_a_tela_lista_o_paciente(cliente_logado):
    resposta = cliente_logado.get("/pacientes?filtro=todos")
    assert resposta.status_code == 200
    # O apostrofo sai escapado: o autoescape do Jinja2 esta ligado, e e assim que
    # tem de ser. Procurar o literal cru testaria a ausencia de protecao contra XSS.
    assert "Claudia Moreira Sant&#39;Ana" in resposta.text


def test_a_busca_e_o_primeiro_campo_da_tela(cliente_logado):
    """E o que ela faz o dia inteiro; nao pode estar escondido atras de um menu."""
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert html.index('class="busca"') < html.index("<table")


def test_dado_suspeito_aparece_marcado_nao_escondido(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'class="aviso"' in html


def test_a_tela_marca_a_aba_pacientes_como_ativa(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'href="/pacientes" class="ativo"' in html


def test_os_quatro_filtros_aparecem(cliente_logado):
    html = cliente_logado.get("/pacientes").text
    for rotulo in ("Ativos", "Com pendência", "Com tratamento a fazer", "Todos"):
        assert rotulo in html


def test_cada_linha_leva_para_o_odontograma(cliente_logado, sessao):
    paciente = sessao.query(Paciente).one()
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert f'/odontograma/{paciente.id}' in html


def test_filtro_invalido_cai_no_padrao_em_vez_de_dar_erro(cliente_logado):
    assert cliente_logado.get("/pacientes?filtro=inventado").status_code == 200


def test_a_lista_nao_diz_mais_em_aberto(cliente_logado):
    """Depois que o financeiro chegou, existem DOIS numeros diferentes: o
    tratamento planejado e nao feito ('a fazer') e o tratamento feito e nao pago
    ('a receber'). Chamar os dois de 'em aberto' faria a Dra. Katia ler um pelo
    outro."""
    html = cliente_logado.get("/pacientes").text
    assert "Em aberto" not in html
    assert "A fazer" in html


# --- escolher a ordem ----------------------------------------------------------


def test_a_tela_oferece_as_tres_ordens(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'name="ordem"' in html
    for valor in ("alfabetica", "atendimento", "cadastro"):
        assert f'value="{valor}"' in html


def test_a_ordem_escolhida_vem_marcada_ao_reabrir(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos&ordem=atendimento").text
    assert 'value="atendimento" selected' in html


def test_ordem_inventada_cai_no_padrao_em_vez_de_dar_erro(cliente_logado):
    """URL editada a mao nao derruba a tela — mesma regra do filtro."""
    resposta = cliente_logado.get("/pacientes?ordem=por-cor-favorita&filtro=todos")
    assert resposta.status_code == 200
    assert 'value="alfabetica" selected' in resposta.text


def test_trocar_de_filtro_nao_perde_a_ordem_escolhida(cliente_logado):
    """Os links de filtro tem de carregar a ordem junto, senao a escolha some no
    primeiro clique."""
    html = cliente_logado.get("/pacientes?filtro=todos&ordem=cadastro").text
    assert "ordem=cadastro" in html


def test_buscar_nao_perde_a_ordem_escolhida(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos&ordem=cadastro").text
    assert '<input type="hidden" name="ordem" value="cadastro">' in html


def test_por_cadastro_a_coluna_mostra_a_data_que_esta_ordenando(cliente_logado):
    """Ordenar por um campo invisivel deixa a lista sem explicacao na tela."""
    html = cliente_logado.get("/pacientes?filtro=todos&ordem=cadastro").text
    assert "Cadastrado em" in html
    assert "Último atendimento" not in html


def test_nas_outras_ordens_a_coluna_continua_a_de_sempre(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos&ordem=atendimento").text
    assert "Último atendimento" in html
    assert "Cadastrado em" not in html
