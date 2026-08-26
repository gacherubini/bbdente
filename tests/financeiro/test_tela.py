"""A tela do Financeiro.

O menu deixa de dizer 'em breve'. O que a tela precisa acertar, e estes testes
guardam: dizer o que cada numero e, nao mentir quando o periodo esta vazio, e
nao despejar 30 anos de divida como se fosse cobranca de hoje.
"""

import json
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.clinico.service import lancar
from app.financeiro.models import Parcela
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([categoria, convenio])
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    paciente = Paciente(
        clinica_id=clinica.id, codigo_legado="0001/PT", nome="AMANDA ROSA",
        convenio_id=convenio.id,
    )
    sessao.add_all([procedimento, paciente])
    sessao.flush()
    return clinica, usuario, paciente, procedimento


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def com_movimento(sessao, cenario, quando=date(2026, 5, 10)):
    clinica, usuario, paciente, procedimento = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
            vencimento=date(2026, 4, 1), valor_cobrado=Decimal("1200.00"),
            valor_pago=Decimal("1200.00"), pago_em=quando,
        )
    )
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=procedimento.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL], status=StatusLancamento.REALIZADO,
        data=quando, valor=Decimal("980.00"),
    )
    sessao.flush()


def embutido(html: str, identificador: str):
    bruto = re.search(
        rf'id="{identificador}"[^>]*>(.*?)</script>', html, re.S
    )
    assert bruto, f"o JSON '{identificador}' nao esta embutido na pagina"
    return json.loads(bruto.group(1))


# --- a tela --------------------------------------------------------------------


def test_a_tela_abre_e_marca_a_aba(cliente):
    resposta = cliente.get("/financeiro?ano=2026&mes=5")
    assert resposta.status_code == 200
    assert 'href="/financeiro" class="ativo"' in resposta.text


def test_o_menu_nao_diz_mais_em_breve(cliente):
    assert "Financeiro <b>em breve</b>" not in cliente.get("/financeiro").text


def test_a_tela_diz_o_que_cada_numero_e(sessao, cliente, cenario):
    com_movimento(sessao, cenario)
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    for rotulo in ("Recebido", "Produzido", "A receber", "Tratamentos"):
        assert rotulo in html


def test_o_cartao_a_receber_promete_o_mes_e_nao_o_acumulado(sessao, cliente, cenario):
    """O rotulo e o calculo tem que dizer a mesma coisa.

    Enquanto o calculo somava desde 1996, o rotulo dizia "tudo que venceu e nao
    foi pago" — literalmente verdade, e ainda assim ilegivel ao lado de tres
    numeros mensais. Se um dos dois voltar atras sem o outro, este teste cai.
    """
    com_movimento(sessao, cenario)
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert "venceu no mês e não foi pago" in html
    assert "tudo que venceu" not in html


def test_divida_de_meses_anteriores_nao_aparece_no_cartao_do_mes(
    sessao, cliente, cenario
):
    clinica, _, paciente, _ = cenario
    # Um valor que nao aparece em nenhum outro numero da tela: se ele vazar para
    # o HTML, so pode ter vindo do cartao "a receber".
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
            vencimento=date(1998, 7, 1), valor_cobrado=Decimal("7777.77"),
        )
    )
    com_movimento(sessao, cenario)
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert "1.200,00" in html, "o recebido de maio continua na tela"
    assert "7.777,77" not in html


def test_os_numeros_do_mes_aparecem_formatados(sessao, cliente, cenario):
    com_movimento(sessao, cenario)
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert "1.200,00" in html
    assert "980,00" in html


def test_mes_vazio_avisa_em_vez_de_mostrar_quatro_zeros_mudos(sessao, cliente, cenario):
    com_movimento(sessao, cenario, quando=date(2026, 5, 10))
    html = cliente.get("/financeiro?ano=2026&mes=9").text
    assert "nada registrado" in html.lower()


def test_sem_sessao_e_recusada(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get("/financeiro").status_code == 303


def test_periodo_invalido_na_url_nao_derruba_a_tela(cliente):
    assert cliente.get("/financeiro?ano=abacaxi&mes=99").status_code == 200


# --- os dados dos graficos -----------------------------------------------------


def test_o_grafico_do_ano_vem_com_doze_pontos(sessao, cliente, cenario):
    com_movimento(sessao, cenario)
    dados = embutido(cliente.get("/financeiro?ano=2026&mes=5").text, "dados-graficos")
    assert len(dados["recebido_por_mes"]) == 12
    assert dados["recebido_por_mes"][4] == "1200.00"
    assert dados["recebido_por_mes"][0] == "0.00"


def test_o_grafico_do_ano_anterior_vem_junto_para_comparar(sessao, cliente, cenario):
    dados = embutido(cliente.get("/financeiro?ano=2026&mes=5").text, "dados-graficos")
    assert len(dados["recebido_ano_anterior"]) == 12


def test_o_grafico_do_mes_tem_um_ponto_por_dia(sessao, cliente, cenario):
    com_movimento(sessao, cenario)
    dados = embutido(cliente.get("/financeiro?ano=2026&mes=5").text, "dados-graficos")
    assert len(dados["tratamentos_por_dia"]) == 31
    assert dados["tratamentos_por_dia"][9] == 1  # dia 10

    dados_fev = embutido(cliente.get("/financeiro?ano=2026&mes=2").text, "dados-graficos")
    assert len(dados_fev["tratamentos_por_dia"]) == 28


def test_as_pizzas_vem_com_nome_e_valor(sessao, cliente, cenario):
    com_movimento(sessao, cenario)
    dados = embutido(cliente.get("/financeiro?ano=2026&mes=5").text, "dados-graficos")
    assert dados["por_categoria"] == [["Dentistica", "980.00"]]
    assert dados["por_convenio"] == [["PARTICULAR", "980.00"]]


def test_o_dinheiro_vai_como_texto_e_nunca_como_float(sessao, cliente, cenario):
    """Float em JavaScript erra centavo. O valor viaja como string e o desenho
    nao faz conta com ele alem de comparar tamanho de barra."""
    com_movimento(sessao, cenario)
    dados = embutido(cliente.get("/financeiro?ano=2026&mes=5").text, "dados-graficos")
    assert all(isinstance(v, str) for v in dados["recebido_por_mes"])


def test_o_grafico_tem_tabela_equivalente_para_quem_nao_ve(sessao, cliente, cenario):
    """Grafico que so existe em pixel exclui quem usa leitor de tela e some
    quando o JavaScript falha."""
    com_movimento(sessao, cenario)
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert "tabela-equivalente" in html


# --- lista de cobranca ----------------------------------------------------------


def test_a_cobranca_mostra_paciente_vencimento_e_saldo(sessao, cliente, cenario):
    clinica, _, paciente, _ = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
            vencimento=date(2026, 3, 1), valor_cobrado=Decimal("300.00"),
            valor_pago=Decimal("50.00"), pago_em=date(2026, 3, 20),
        )
    )
    sessao.flush()
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert "AMANDA ROSA" in html
    assert "250,00" in html


def test_a_cobranca_leva_para_o_odontograma_do_paciente(sessao, cliente, cenario):
    clinica, _, paciente, _ = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
            vencimento=date(2026, 3, 1), valor_cobrado=Decimal("300.00"),
        )
    )
    sessao.flush()
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert f'href="/odontograma/{paciente.id}"' in html


def test_a_cobranca_antiga_fica_fora_por_padrao(sessao, cliente, cenario):
    """R$ 3,4 milhoes em aberto desde 1996 nao e cobranca, e historia."""
    clinica, _, paciente, _ = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
            vencimento=date(1998, 3, 1), valor_cobrado=Decimal("300.00"),
        )
    )
    sessao.flush()
    html = cliente.get("/financeiro?ano=2026&mes=5").text
    assert "AMANDA ROSA" not in html


def test_da_para_pedir_a_cobranca_inteira(sessao, cliente, cenario):
    clinica, _, paciente, _ = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
            vencimento=date(1998, 3, 1), valor_cobrado=Decimal("300.00"),
        )
    )
    sessao.flush()
    html = cliente.get("/financeiro?ano=2026&mes=5&cobranca=tudo").text
    assert "AMANDA ROSA" in html


# --- contrato do desenhista ----------------------------------------------------


def test_o_javascript_dos_graficos_nao_formata_dinheiro():
    """Quem soma e escreve dinheiro e o servidor, onde ha teste — o JavaScript
    so transforma valor em altura de barra e angulo de fatia.

    Arredondar coordenada de SVG nao conta: nao e dinheiro, e geometria. O que
    nao pode voltar para ca e a escrita do valor.
    """
    from pathlib import Path

    fonte = Path("app/static/graficos.js").read_text(encoding="utf-8")
    for proibido in ("R$", "toLocaleString", "Intl.NumberFormat"):
        assert proibido not in fonte, f"formatacao de dinheiro vazou para o JS: {proibido}"


def test_o_javascript_nunca_poe_nome_do_banco_como_html():
    """Nome de convenio e de categoria vem do banco, e banco nao e fonte
    confiavel de HTML."""
    from pathlib import Path

    fonte = Path("app/static/graficos.js").read_text(encoding="utf-8")
    assert "textContent = fatia[0]" in fonte


def test_a_cobranca_nao_despeja_dez_mil_linhas_numa_pagina(sessao, cliente, cenario):
    """Sao 10.233 parcelas vencidas no banco real. Uma pagina com todas nao e
    lista de cobranca, e arquivo morto que trava o navegador."""
    from app.financeiro.service import LIMITE_DE_COBRANCA

    clinica, _, paciente, _ = cenario
    for dia in range(1, LIMITE_DE_COBRANCA + 20):
        sessao.add(
            Parcela(
                clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
                vencimento=date(2020, 1, 1) + timedelta(days=dia),
                valor_cobrado=Decimal("100.00"),
            )
        )
    sessao.flush()
    html = cliente.get("/financeiro?ano=2026&mes=5&cobranca=tudo").text
    assert html.count('href="/financeiro/recebimento?parcela_id=') == LIMITE_DE_COBRANCA
    assert "Mostrando as" in html
