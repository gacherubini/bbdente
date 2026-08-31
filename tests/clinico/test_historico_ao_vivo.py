"""O historico e a contagem do dia mudam sem recarregar a pagina.

Ate 31/08/2026, lancar um tratamento repintava o desenho e mais nada: a linha nova
so aparecia no historico depois de um F5, e o cabecalho do dia continuava dizendo
"1 tratamento · R$ 100,00" com dois tratamentos gravados. Quem estava com a
paciente na cadeira recarregava a tela a cada lancamento para conferir.

Quem soma continua sendo o servidor. O JavaScript pede as linhas de novo e troca o
`<tbody>` — refazer a soma no navegador seria a mesma regra escrita em dois
lugares, e um dia elas discordam.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.service import lancar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

HISTORICO_JS = Path("app/static/historico.js")
PAINEL_JS = Path("app/static/painel.js")
PAINEL = Path("app/templates/_painel_lancamento.html")
ATENDIMENTOS_JS = Path("app/static/atendimentos.js")


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=clinica.id, nome="Amanda")
    vazia = Paciente(clinica_id=clinica.id, nome="Sem nada ainda")
    sessao.add_all([procedimento, paciente, vazia])
    sessao.flush()
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=procedimento.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL], status=StatusLancamento.REALIZADO,
        data=date(2026, 5, 10), valor=Decimal("100.00"),
    )
    sessao.flush()
    return {
        "clinica": clinica, "usuario": usuario, "paciente": paciente,
        "vazia": vazia, "procedimento": procedimento, "lancamento": lancamento,
    }


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def lancar_outro(cliente, cenario, **extra) -> None:
    corpo = {
        "paciente_id": cenario["paciente"].id,
        "procedimento_id": cenario["procedimento"].id,
        "escopo": "REGIOES", "dente": 26, "regioes": ["DISTAL"],
        "status": "REALIZADO", "data": "2026-05-10", "valor": "50.00",
    }
    corpo.update(extra)
    resposta = cliente.post("/api/lancamento", json=corpo)
    assert resposta.status_code == 201, resposta.text


# --- o pedaco que o JavaScript troca -------------------------------------------


def test_o_historico_vem_sozinho_sem_a_pagina_em_volta(cliente, cenario):
    """E um pedaco para trocar dentro da tabela, nao uma tela: sem <html>, sem menu."""
    resposta = cliente.get(f"/odontograma/{cenario['paciente'].id}/historico")
    assert resposta.status_code == 200
    corpo = resposta.text
    assert f'data-lancamento="{cenario["lancamento"].id}"' in corpo
    assert "<html" not in corpo.lower()


def test_lancar_muda_a_contagem_do_dia(cliente, cenario):
    """O sintoma que abriu isto: dois tratamentos e o cabecalho dizendo um."""
    antes = cliente.get(f"/odontograma/{cenario['paciente'].id}/historico").text
    assert "1 tratamento" in antes
    assert "R$ 100,00" in antes

    lancar_outro(cliente, cenario)

    depois = cliente.get(f"/odontograma/{cenario['paciente'].id}/historico").text
    assert "2 tratamentos" in depois
    assert "R$ 150,00" in depois


def test_excluir_muda_a_contagem_do_dia(cliente, cenario):
    lancar_outro(cliente, cenario)
    cliente.delete(f"/api/lancamento/{cenario['lancamento'].id}")
    depois = cliente.get(f"/odontograma/{cenario['paciente'].id}/historico").text
    assert "1 tratamento" in depois
    assert "R$ 50,00" in depois


def test_corrigir_o_valor_muda_o_total_do_dia(cliente, cenario):
    cliente.patch(
        f"/api/lancamento/{cenario['lancamento'].id}",
        json={"status": "REALIZADO", "data": "2026-05-10", "valor": "300.00"},
    )
    depois = cliente.get(f"/odontograma/{cenario['paciente'].id}/historico").text
    assert "R$ 300,00" in depois


def test_paciente_sem_lancamento_nenhum_devolve_o_vazio_de_sempre(cliente, cenario):
    resposta = cliente.get(f"/odontograma/{cenario['vazia'].id}/historico")
    assert resposta.status_code == 200
    assert "Nenhum lançamento ainda" in resposta.text


def test_o_historico_de_outra_clinica_da_404(sessao, cliente):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheia = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add(alheia)
    sessao.flush()
    assert cliente.get(f"/odontograma/{alheia.id}/historico").status_code == 404


def test_sem_sessao_e_recusado(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        resposta = anonimo.get(f"/odontograma/{cenario['paciente'].id}/historico")
        assert resposta.status_code == 303


# --- a tela sabe onde trocar ----------------------------------------------------


def test_a_tabela_do_historico_tem_onde_o_javascript_encaixa(cliente, cenario):
    html = cliente.get(f"/odontograma/{cenario['paciente'].id}").text
    assert 'id="historico-linhas"' in html


def test_o_javascript_pede_as_linhas_ao_servidor(cliente, cenario):
    """Se ele recontar sozinho, a soma passa a existir em dois lugares."""
    fonte = HISTORICO_JS.read_text()
    assert "/historico" in fonte


# --- a tela do dia manda editar no odontograma ----------------------------------


def test_a_tela_do_dia_tem_como_editar_o_tratamento(cliente, cenario):
    """Editar dente e tratamento exige o desenho do lado; o link leva para la."""
    lancar_outro(cliente, cenario)
    html = cliente.get("/atendimentos?dia=2026-05-10").text
    paciente_id = cenario["paciente"].id
    lancamento_id = cenario["lancamento"].id
    assert f"/odontograma/{paciente_id}?editar={lancamento_id}" in html


def test_abrir_com_editar_na_url_nao_derruba_a_tela(cliente, cenario):
    resposta = cliente.get(
        f"/odontograma/{cenario['paciente'].id}?editar={cenario['lancamento'].id}"
    )
    assert resposta.status_code == 200


def test_excluir_devolve_o_desenho_sem_o_tratamento(cliente, cenario):
    """Dente pintado depois de a linha sumir e a tela dizendo duas coisas."""
    resposta = cliente.delete(f"/api/lancamento/{cenario['lancamento'].id}")
    assert resposta.status_code == 200
    assert resposta.json()["estado"]["dentes"]["16"]["regioes"] == {}


# --- o painel corrige, e da para sair da correcao -------------------------------


def test_o_painel_manda_a_correcao_por_patch(cliente, cenario):
    """POST cria um segundo lancamento; corrigir tem de mexer no que existe."""
    fonte = PAINEL_JS.read_text()
    assert "PATCH" in fonte
    assert "bddente:corrigir" in fonte


def test_da_para_cancelar_a_correcao_sem_recarregar(cliente, cenario):
    """Quem clicou em editar por engano precisa de um caminho de volta visivel."""
    assert "painel-parar-correcao" in PAINEL.read_text()
    assert "painel-parar-correcao" in PAINEL_JS.read_text()
