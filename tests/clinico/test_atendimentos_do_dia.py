"""A tela do dia: quem foi atendido hoje, e o que foi feito em cada um.

O que conta aqui e o que FOI FEITO — status REALIZADO com data realizada no dia.
Um tratamento planejado para hoje e agenda, nao atendimento: misturar os dois
repete o erro que o AGENTS.md ja proibe entre o "a fazer" da lista de pacientes
e o "a receber" do financeiro.

Como nao existe entidade `atendimento` no banco, um atendimento aqui e
"um paciente num dia". Duas idas da mesma pessoa no mesmo dia aparecem como uma.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.service import (
    atendimentos_do_dia,
    excluir_lancamento,
    lancar,
    planejados_do_dia,
)
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

DIA = date(2026, 8, 26)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    outra = Clinica(nome="Outra")
    sessao.add_all([clinica, outra])
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
    profilaxia = Procedimento(
        clinica_id=clinica.id, codigo="01", nome="Profilaxia",
        categoria_id=categoria.id, escopo_sugerido=Escopo.BOCA, regioes_sugeridas=[],
    )
    # Os nomes estao fora de ordem alfabetica de proposito: a tela ordena por nome,
    # e com "Amanda" criada primeiro o teste de ordem passaria por acidente.
    zilda = Paciente(clinica_id=clinica.id, codigo_legado="0002/PT", nome="Zilda")
    amanda = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    de_fora = Paciente(clinica_id=outra.id, codigo_legado="0003/PT", nome="De Fora")
    sessao.add_all([restauracao, profilaxia, zilda, amanda, de_fora])
    sessao.flush()
    return {
        "clinica": clinica, "outra": outra, "usuario": usuario,
        "restauracao": restauracao, "profilaxia": profilaxia,
        "zilda": zilda, "amanda": amanda, "de_fora": de_fora,
    }


@pytest.fixture
def lancar_em(sessao, cenario):
    def fazer(paciente, *, dia=DIA, status=StatusLancamento.REALIZADO,
              valor="100.00", dente=16, procedimento=None, clinica=None):
        procedimento = procedimento or cenario["restauracao"]
        clinica = clinica or cenario["clinica"]
        lancamento = lancar(
            sessao, clinica_id=clinica.id, usuario_id=cenario["usuario"].id,
            paciente_id=paciente.id, procedimento_id=procedimento.id,
            escopo=Escopo.REGIOES if dente else Escopo.BOCA, dente=dente,
            regioes=[Regiao.MESIAL] if dente else [], status=status,
            data=dia, valor=Decimal(valor),
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


def do_dia(sessao, cenario, dia=DIA):
    return atendimentos_do_dia(sessao, clinica_id=cenario["clinica"].id, dia=dia)


# --- o agrupamento -------------------------------------------------------------


def test_dois_tratamentos_do_mesmo_paciente_no_dia_sao_um_atendimento_so(
    sessao, cenario, lancar_em
):
    lancar_em(cenario["amanda"])
    lancar_em(cenario["amanda"], dente=17)

    grupos = do_dia(sessao, cenario)

    assert len(grupos) == 1
    assert grupos[0]["paciente_id"] == cenario["amanda"].id
    assert grupos[0]["quantos"] == 2


def test_pacientes_diferentes_sao_atendimentos_diferentes(sessao, cenario, lancar_em):
    lancar_em(cenario["amanda"])
    lancar_em(cenario["zilda"])

    grupos = do_dia(sessao, cenario)

    assert len(grupos) == 2
    assert {g["paciente_id"] for g in grupos} == {
        cenario["amanda"].id, cenario["zilda"].id
    }


def test_o_total_do_atendimento_soma_os_tratamentos(sessao, cenario, lancar_em):
    lancar_em(cenario["amanda"], valor="340.00")
    lancar_em(cenario["amanda"], dente=17, valor="250.00")

    grupos = do_dia(sessao, cenario)

    assert grupos[0]["total"] == Decimal("590.00")


def test_o_atendimento_traz_o_dente_e_o_nome_do_tratamento(sessao, cenario, lancar_em):
    lancar_em(cenario["amanda"], dente=11)

    item = do_dia(sessao, cenario)[0]["itens"][0]

    assert item["dente"] == 11
    assert item["procedimento"] == "Restauracao"


def test_tratamento_de_boca_toda_entra_sem_dente(sessao, cenario, lancar_em):
    lancar_em(cenario["amanda"], dente=None, procedimento=cenario["profilaxia"])

    item = do_dia(sessao, cenario)[0]["itens"][0]

    assert item["dente"] is None
    assert item["escopo"] == "BOCA"


# --- o que NAO entra -----------------------------------------------------------


def test_planejado_para_hoje_nao_e_atendimento_feito(sessao, cenario, lancar_em):
    """Agenda nao e prontuario. O tratamento marcado para hoje ainda nao aconteceu."""
    lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)

    assert do_dia(sessao, cenario) == []


def test_lancamento_excluido_nao_entra(sessao, cenario, lancar_em):
    lancamento = lancar_em(cenario["amanda"])
    excluir_lancamento(
        sessao, clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id, lancamento_id=lancamento.id,
    )
    sessao.flush()

    assert do_dia(sessao, cenario) == []


def test_tratamento_de_outro_dia_nao_entra(sessao, cenario, lancar_em):
    lancar_em(cenario["amanda"], dia=date(2026, 8, 25))

    assert do_dia(sessao, cenario) == []


def test_tratamento_de_outra_clinica_nao_entra(sessao, cenario, lancar_em):
    lancar_em(cenario["de_fora"], clinica=cenario["outra"])

    assert do_dia(sessao, cenario) == []


def test_dia_sem_movimento_devolve_lista_vazia(sessao, cenario):
    assert do_dia(sessao, cenario) == []


# --- a tela --------------------------------------------------------------------


def test_a_tela_mostra_o_nome_do_paciente_e_linka_para_o_odontograma(
    cliente, cenario, lancar_em
):
    lancar_em(cenario["amanda"])

    resposta = cliente.get(f"/atendimentos?dia={DIA.isoformat()}")

    assert resposta.status_code == 200
    assert "Amanda" in resposta.text
    assert f'href="/odontograma/{cenario["amanda"].id}"' in resposta.text


def test_a_tela_ordena_os_atendimentos_por_nome(cliente, cenario, lancar_em):
    lancar_em(cenario["zilda"])
    lancar_em(cenario["amanda"])

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert corpo.index("Amanda") < corpo.index("Zilda")


def test_a_tela_traz_o_total_do_dia(cliente, cenario, lancar_em):
    lancar_em(cenario["amanda"], valor="890.00")
    lancar_em(cenario["zilda"], valor="150.00")

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "1.040,00" in corpo


def test_a_tela_sem_movimento_diz_que_nao_houve_atendimento(cliente):
    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "Nenhum atendimento" in corpo


def test_a_tela_abre_no_dia_de_hoje_sem_parametro(cliente):
    resposta = cliente.get("/atendimentos")

    assert resposta.status_code == 200
    assert date.today().isoformat() in resposta.text


def test_dia_invalido_na_url_nao_derruba_a_tela(cliente):
    """Numero vindo da URL nunca derruba a tela — mesma regra do financeiro."""
    resposta = cliente.get("/atendimentos?dia=trinta-de-fevereiro")

    assert resposta.status_code == 200
    assert date.today().isoformat() in resposta.text


def test_a_tela_exige_login(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get("/atendimentos").status_code in (302, 303, 307)


# --- planejado para o dia: aparece, mas em bloco separado ----------------------
#
# Nao entra na conta do que foi FEITO. Fica visivel porque quem abre a tela quer
# saber quem tem hora marcada, e some-lo faria a tela parecer quebrada para quem
# acabou de lancar um planejamento.


def planejados(sessao, cenario, dia=DIA):
    return planejados_do_dia(sessao, clinica_id=cenario["clinica"].id, dia=dia)


def test_planejado_para_o_dia_entra_nos_planejados(sessao, cenario, lancar_em):
    lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)

    grupos = planejados(sessao, cenario)

    assert len(grupos) == 1
    assert grupos[0]["paciente_id"] == cenario["amanda"].id
    assert grupos[0]["quantos"] == 1


def test_realizado_nao_entra_nos_planejados(sessao, cenario, lancar_em):
    """Os dois blocos sao disjuntos: nada aparece nos dois ao mesmo tempo."""
    lancar_em(cenario["amanda"], status=StatusLancamento.REALIZADO)

    assert planejados(sessao, cenario) == []


def test_planejado_de_outro_dia_nao_entra(sessao, cenario, lancar_em):
    lancar_em(
        cenario["amanda"], dia=date(2026, 8, 25), status=StatusLancamento.PLANEJADO
    )

    assert planejados(sessao, cenario) == []


def test_planejado_excluido_nao_entra(sessao, cenario, lancar_em):
    lancamento = lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)
    excluir_lancamento(
        sessao, clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id, lancamento_id=lancamento.id,
    )
    sessao.flush()

    assert planejados(sessao, cenario) == []


def test_planejado_de_outra_clinica_nao_entra(sessao, cenario, lancar_em):
    lancar_em(
        cenario["de_fora"], clinica=cenario["outra"], status=StatusLancamento.PLANEJADO
    )

    assert planejados(sessao, cenario) == []


# --- os dois blocos na tela ----------------------------------------------------


def test_a_tela_mostra_o_planejado_do_dia(cliente, cenario, lancar_em):
    lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "Planejado para hoje" in corpo
    assert "Amanda" in corpo


def test_o_feito_vem_antes_do_planejado(cliente, cenario, lancar_em):
    lancar_em(cenario["zilda"], status=StatusLancamento.REALIZADO)
    lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert corpo.index("Feito hoje") < corpo.index("Planejado para hoje")


def test_o_produzido_do_dia_ignora_o_planejado(cliente, cenario, lancar_em):
    """O numero de produzido e do que foi FEITO. Somar planejado nele inflaria a
    producao do dia com trabalho que ainda nao aconteceu."""
    lancar_em(cenario["zilda"], valor="150.00", status=StatusLancamento.REALIZADO)
    lancar_em(cenario["amanda"], valor="890.00", status=StatusLancamento.PLANEJADO)

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "150,00" in corpo
    assert "1.040,00" not in corpo


def test_dia_so_com_planejado_nao_diz_que_nao_houve_nada(cliente, cenario, lancar_em):
    lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "Nenhum atendimento" not in corpo


def test_dia_vazio_de_verdade_continua_dizendo_que_nao_houve_nada(cliente):
    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "Nenhum atendimento" in corpo


def test_o_planejado_linka_para_o_odontograma_do_paciente(cliente, cenario, lancar_em):
    lancar_em(cenario["amanda"], status=StatusLancamento.PLANEJADO)

    corpo = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert f'href="/odontograma/{cenario["amanda"].id}"' in corpo
