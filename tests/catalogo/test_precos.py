"""Preco na tela de tratamentos.

Os 606 precos ja estavam no banco desde a migracao do MVP — vieram dos 51
arquivos ARQSE### do Dentalis, um por convenio. A tela e que nunca os mostrou.

Duas regras que estes testes guardam: preco antigo nao some quando muda (um
lancamento de 2015 foi cobrado ao preco de 2015), e o catalogo inteiro sai numa
consulta so — sao 612 pares procedimento x convenio.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.catalogo.service import precos_por_procedimento
from app.main import criar_app
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo

HOJE = date.today()


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    particular = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    uniodonto = Convenio(clinica_id=clinica.id, codigo="051", nome="UNIODONTO")
    sessao.add_all([categoria, particular, uniodonto])
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    sem_tabela = Procedimento(
        clinica_id=clinica.id, codigo="99", nome="Sem tabela",
        categoria_id=categoria.id, escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add_all([restauracao, sem_tabela])
    sessao.flush()
    return clinica, usuario, restauracao, sem_tabela, particular, uniodonto


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def preco(sessao, procedimento, convenio, valor, quando=HOJE):
    sessao.add(
        Preco(
            procedimento_id=procedimento.id,
            convenio_id=convenio.id,
            valor=Decimal(valor),
            vigente_desde=quando,
        )
    )
    sessao.flush()


def test_traz_o_preco_de_cada_convenio(sessao, cenario):
    clinica, _, restauracao, _, particular, uniodonto = cenario
    preco(sessao, restauracao, particular, "180.00")
    preco(sessao, restauracao, uniodonto, "90.00")
    tabela = precos_por_procedimento(sessao, clinica_id=clinica.id)
    assert [(linha["convenio"], linha["valor"]) for linha in tabela[restauracao.id]] == [
        ("PARTICULAR", Decimal("180.00")),
        ("UNIODONTO", Decimal("90.00")),
    ]


def test_o_preco_vigente_vence_o_antigo(sessao, cenario):
    """Trocar preco grava linha nova; a tela mostra a mais recente que ja valia."""
    clinica, _, restauracao, _, particular, _ = cenario
    preco(sessao, restauracao, particular, "120.00", HOJE - timedelta(days=400))
    preco(sessao, restauracao, particular, "180.00", HOJE - timedelta(days=10))
    tabela = precos_por_procedimento(sessao, clinica_id=clinica.id)
    assert [linha["valor"] for linha in tabela[restauracao.id]] == [Decimal("180.00")]


def test_preco_que_ainda_nao_comecou_a_valer_nao_aparece(sessao, cenario):
    clinica, _, restauracao, _, particular, _ = cenario
    preco(sessao, restauracao, particular, "120.00", HOJE - timedelta(days=10))
    preco(sessao, restauracao, particular, "999.00", HOJE + timedelta(days=30))
    tabela = precos_por_procedimento(sessao, clinica_id=clinica.id)
    assert [linha["valor"] for linha in tabela[restauracao.id]] == [Decimal("120.00")]


def test_da_para_perguntar_o_preco_de_uma_data_antiga(sessao, cenario):
    clinica, _, restauracao, _, particular, _ = cenario
    preco(sessao, restauracao, particular, "120.00", date(2015, 1, 1))
    preco(sessao, restauracao, particular, "180.00", date(2024, 1, 1))
    tabela = precos_por_procedimento(sessao, clinica_id=clinica.id, em=date(2016, 6, 1))
    assert [linha["valor"] for linha in tabela[restauracao.id]] == [Decimal("120.00")]


def test_procedimento_sem_tabela_simplesmente_nao_aparece(sessao, cenario):
    clinica, _, restauracao, sem_tabela, particular, _ = cenario
    preco(sessao, restauracao, particular, "180.00")
    tabela = precos_por_procedimento(sessao, clinica_id=clinica.id)
    assert sem_tabela.id not in tabela


def test_nao_enxerga_preco_de_outra_clinica(sessao, cenario):
    clinica, _, restauracao, _, particular, _ = cenario
    preco(sessao, restauracao, particular, "180.00")

    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    cat = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    conv = Convenio(clinica_id=outra.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([cat, conv])
    sessao.flush()
    alheio = Procedimento(
        clinica_id=outra.id, codigo="21", nome="Alheio", categoria_id=cat.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(alheio)
    sessao.flush()
    preco(sessao, alheio, conv, "500.00")

    tabela = precos_por_procedimento(sessao, clinica_id=clinica.id)
    assert alheio.id not in tabela


def test_o_catalogo_inteiro_sai_numa_consulta_so(sessao, cenario):
    """Sao 612 pares procedimento x convenio no banco real. Uma consulta por
    linha da tela seriam 612 idas ao banco para desenhar uma pagina."""
    clinica, _, restauracao, sem_tabela, particular, uniodonto = cenario
    for p in (restauracao, sem_tabela):
        for c in (particular, uniodonto):
            preco(sessao, p, c, "100.00")

    consultas = []
    conexao = sessao.get_bind()

    def contar(conn, cursor, instrucao, *resto):
        if instrucao.lstrip().upper().startswith("SELECT"):
            consultas.append(instrucao)

    event.listen(conexao, "before_cursor_execute", contar)
    try:
        precos_por_procedimento(sessao, clinica_id=clinica.id)
    finally:
        event.remove(conexao, "before_cursor_execute", contar)

    assert len(consultas) == 1, f"foram {len(consultas)} consultas"


# --- a tela --------------------------------------------------------------------


def test_a_tela_mostra_o_preco_particular(sessao, cliente, cenario):
    _, _, restauracao, _, particular, _ = cenario
    preco(sessao, restauracao, particular, "180.00")
    html = cliente.get("/tratamentos").text
    assert "180,00" in html


def test_a_tela_mostra_travessao_para_quem_nao_tem_tabela(sessao, cliente, cenario):
    """'Sem tabela' e 'de graca' sao coisas diferentes: R$ 0,00 mentiria."""
    _, _, restauracao, _, particular, _ = cenario
    preco(sessao, restauracao, particular, "180.00")
    html = cliente.get("/tratamentos").text
    linha_sem_tabela = [
        pedaco.split("</tr>")[0]
        for pedaco in html.split("<tr>")
        if "Sem tabela" in pedaco.split("</tr>")[0]
    ][0]
    assert "R$" not in linha_sem_tabela
    assert "—" in linha_sem_tabela


def test_a_tela_lista_os_outros_convenios(sessao, cliente, cenario):
    _, _, restauracao, _, particular, uniodonto = cenario
    preco(sessao, restauracao, particular, "180.00")
    preco(sessao, restauracao, uniodonto, "90.00")
    html = cliente.get("/tratamentos").text
    assert "UNIODONTO" in html
    assert "90,00" in html
