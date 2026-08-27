"""O historico do paciente agrupado por data: cada data e um atendimento.

Aqui, ao contrario da tela do dia, o PLANEJADO entra junto — a tabela continua
sendo a mesma que a dentista corrige na linha, e esconder o planejado tiraria
dela o jeito de marcar o tratamento como feito.

Lancamento sem data nenhuma existe no historico migrado e nao pode sumir: vai
para um grupo proprio, no fim.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.service import atendimentos_do_paciente, lancar
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
    sessao.add(categoria)
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    amanda = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([restauracao, amanda])
    sessao.flush()
    return {
        "clinica": clinica, "usuario": usuario,
        "restauracao": restauracao, "amanda": amanda,
    }


@pytest.fixture
def lancar_em(sessao, cenario):
    def fazer(*, dia, status=StatusLancamento.REALIZADO, valor="100.00", dente=16):
        lancamento = lancar(
            sessao, clinica_id=cenario["clinica"].id, usuario_id=cenario["usuario"].id,
            paciente_id=cenario["amanda"].id,
            procedimento_id=cenario["restauracao"].id,
            escopo=Escopo.REGIOES, dente=dente, regioes=[Regiao.MESIAL],
            status=status, data=dia, valor=Decimal(valor),
        )
        sessao.flush()
        return lancamento
    return fazer


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def grupos_de(sessao, cenario):
    return atendimentos_do_paciente(
        sessao, clinica_id=cenario["clinica"].id, paciente_id=cenario["amanda"].id
    )


# --- o agrupamento -------------------------------------------------------------


def test_lancamentos_do_mesmo_dia_ficam_num_grupo_so(sessao, cenario, lancar_em):
    lancar_em(dia=date(2026, 3, 14))
    lancar_em(dia=date(2026, 3, 14), dente=17)

    grupos = grupos_de(sessao, cenario)

    assert len(grupos) == 1
    assert grupos[0]["data"] == date(2026, 3, 14)
    assert grupos[0]["quantos"] == 2


def test_os_grupos_vem_do_mais_novo_para_o_mais_antigo(sessao, cenario, lancar_em):
    lancar_em(dia=date(2025, 11, 18))
    lancar_em(dia=date(2026, 3, 14))
    lancar_em(dia=date(2026, 2, 2))

    datas = [g["data"] for g in grupos_de(sessao, cenario)]

    assert datas == [date(2026, 3, 14), date(2026, 2, 2), date(2025, 11, 18)]


def test_lancamento_sem_data_vai_para_um_grupo_no_fim(sessao, cenario, lancar_em):
    """O historico migrado tem lancamento sem data. Ele nao pode sumir da tela."""
    lancar_em(dia=None)
    lancar_em(dia=date(2026, 3, 14))

    grupos = grupos_de(sessao, cenario)

    assert len(grupos) == 2
    assert grupos[0]["data"] == date(2026, 3, 14)
    assert grupos[-1]["data"] is None
    assert grupos[-1]["quantos"] == 1


def test_dois_lancamentos_sem_data_ficam_no_mesmo_grupo(sessao, cenario, lancar_em):
    """Com data None dos dois lados, ordenar sem cuidado levanta TypeError."""
    lancar_em(dia=None)
    lancar_em(dia=None, dente=17)

    grupos = grupos_de(sessao, cenario)

    assert len(grupos) == 1
    assert grupos[0]["quantos"] == 2


def test_planejado_e_realizado_do_mesmo_dia_ficam_juntos(sessao, cenario, lancar_em):
    lancar_em(dia=date(2026, 3, 14), status=StatusLancamento.REALIZADO)
    lancar_em(dia=date(2026, 3, 14), status=StatusLancamento.PLANEJADO, dente=17)

    grupos = grupos_de(sessao, cenario)

    assert len(grupos) == 1
    assert {i["status"] for i in grupos[0]["itens"]} == {"REALIZADO", "PLANEJADO"}


def test_o_total_do_grupo_soma_os_lancamentos(sessao, cenario, lancar_em):
    lancar_em(dia=date(2026, 3, 14), valor="340.00")
    lancar_em(dia=date(2026, 3, 14), valor="250.00", dente=17)

    assert grupos_de(sessao, cenario)[0]["total"] == Decimal("590.00")


def test_paciente_sem_lancamento_devolve_lista_vazia(sessao, cenario):
    assert grupos_de(sessao, cenario) == []


# --- a tela --------------------------------------------------------------------


def test_a_tela_mostra_o_cabecalho_do_grupo(cliente, cenario, lancar_em):
    lancar_em(dia=date(2026, 3, 14), valor="340.00")
    lancar_em(dia=date(2026, 3, 14), valor="250.00", dente=17)

    corpo = cliente.get(f"/odontograma/{cenario['amanda'].id}").text

    assert "14/03/2026" in corpo
    assert "2 tratamentos" in corpo
    assert "590,00" in corpo


def test_um_tratamento_so_nao_vira_plural_no_cabecalho(cliente, cenario, lancar_em):
    lancar_em(dia=date(2026, 3, 14))

    corpo = cliente.get(f"/odontograma/{cenario['amanda'].id}").text

    assert "1 tratamento" in corpo
    assert "1 tratamentos" not in corpo


def test_a_tela_nomeia_o_grupo_sem_data(cliente, cenario, lancar_em):
    lancar_em(dia=None)

    corpo = cliente.get(f"/odontograma/{cenario['amanda'].id}").text

    assert "Sem data" in corpo


def test_a_edicao_inline_continua_achando_os_dados_na_linha(
    cliente, cenario, lancar_em
):
    """historico.js monta o formulario a partir destes data-*. Se algum sumir do
    template, a edicao na linha para de funcionar sem erro nenhum no console."""
    lancamento = lancar_em(dia=date(2026, 3, 14), valor="340.00")

    corpo = cliente.get(f"/odontograma/{cenario['amanda'].id}").text

    assert f'data-lancamento="{lancamento.id}"' in corpo
    assert 'data-status="REALIZADO"' in corpo
    assert 'data-valor="340.00"' in corpo
    assert 'data-data="2026-03-14"' in corpo
    for classe in ("col-data", "col-situacao", "col-valor", "editar-lancamento"):
        assert classe in corpo


def test_o_historico_continua_sendo_uma_tabela_so(cliente, cenario, lancar_em):
    """historico.js acha a tabela por `.titulo-historico + table` e monta a linha
    de edicao com 6 colunas. Quebrar o historico em uma tabela por dia deixaria o
    seletor achando so o primeiro dia."""
    lancar_em(dia=date(2026, 3, 14))
    lancar_em(dia=date(2026, 2, 2))

    corpo = cliente.get(f"/odontograma/{cenario['amanda'].id}").text
    depois_do_titulo = corpo.split('class="titulo-historico"', 1)[1]

    assert depois_do_titulo.count("<table") == 1
    assert 'colspan="6"' in depois_do_titulo


def test_o_grupo_do_dia_e_uma_linha_da_mesma_tabela(cliente, cenario, lancar_em):
    lancar_em(dia=date(2026, 3, 14))

    corpo = cliente.get(f"/odontograma/{cenario['amanda'].id}").text

    assert "grupo-dia" in corpo
