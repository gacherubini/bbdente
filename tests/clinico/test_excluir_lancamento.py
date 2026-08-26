"""Excluir um tratamento pela tela do dia.

Exclusao LOGICA, sempre: a linha continua no banco com `excluido_em` preenchido.
Prontuario tem guarda minima de 10 anos (CFO), e a regra 1 do AGENTS.md nao abre
excecao — nao ha DELETE de SQL em lugar nenhum deste caminho.

O que some e a leitura: a tela do dia, a producao do financeiro e os graficos
todos passam pelo mesmo filtro `excluido_em IS NULL`. O que NAO some e a parcela:
`parcela` nao tem `lancamento_id`, entao nao ha como saber qual carne era daquele
tratamento. Dividia excluida continua de pe, e isso e deliberado.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Lancamento
from app.clinico.service import atendimentos_do_dia, lancar, producao
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

DIA = date(2026, 8, 26)


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
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([restauracao, paciente])
    sessao.flush()
    return clinica, usuario, paciente, restauracao


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


@pytest.fixture
def lancar_em(sessao, cenario):
    clinica, usuario, paciente, restauracao = cenario

    def fazer(*, dente=16, valor="180.00", status=StatusLancamento.REALIZADO):
        lancamento = lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.REGIOES, dente=dente, regioes=[Regiao.MESIAL],
            status=status, data=DIA, valor=Decimal(valor),
        )
        sessao.flush()
        return lancamento

    return fazer


# --- a exclusao em si ----------------------------------------------------------


def test_excluir_marca_a_data_e_nao_apaga_a_linha(sessao, cliente, lancar_em):
    lancamento = lancar_em()

    assert cliente.delete(f"/api/lancamento/{lancamento.id}").status_code == 200

    guardado = sessao.get(Lancamento, lancamento.id)
    assert guardado is not None, "exclusao e logica: a linha nunca sai do banco"
    assert guardado.excluido_em is not None


def test_excluir_grava_na_auditoria(sessao, cliente, lancar_em):
    lancamento = lancar_em()

    cliente.delete(f"/api/lancamento/{lancamento.id}")

    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "lancamento",
            Auditoria.entidade_id == lancamento.id,
            Auditoria.acao == "EXCLUIR",
        )
    ).first()
    assert linha is not None


def test_excluir_duas_vezes_da_404_na_segunda(cliente, lancar_em):
    lancamento = lancar_em()

    assert cliente.delete(f"/api/lancamento/{lancamento.id}").status_code == 200
    assert cliente.delete(f"/api/lancamento/{lancamento.id}").status_code == 404


def test_lancamento_inexistente_da_404(cliente):
    assert cliente.delete("/api/lancamento/999999").status_code == 404


def test_lancamento_de_outra_clinica_da_404(sessao, cliente, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = criar_usuario(
        sessao, clinica_id=outra.id, email="x@e.com", senha="senha-longa", nome="X"
    )
    categoria = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=outra.id, codigo="21", nome="Alheio", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=outra.id, codigo_legado="0009/PT", nome="De Fora")
    sessao.add_all([procedimento, paciente])
    sessao.flush()
    de_fora = lancar(
        sessao, clinica_id=outra.id, usuario_id=alheio.id, paciente_id=paciente.id,
        procedimento_id=procedimento.id, escopo=Escopo.DENTE, dente=11, regioes=[],
        status=StatusLancamento.REALIZADO, data=DIA, valor=Decimal("90.00"),
    )
    sessao.flush()

    assert cliente.delete(f"/api/lancamento/{de_fora.id}").status_code == 404
    assert sessao.get(Lancamento, de_fora.id).excluido_em is None


def test_exclusao_exige_login(sessao, cenario, lancar_em):
    lancamento = lancar_em()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.delete(f"/api/lancamento/{lancamento.id}").status_code in (
            401, 303, 307,
        )
    assert sessao.get(Lancamento, lancamento.id).excluido_em is None


# --- o que some junto ----------------------------------------------------------


def test_o_excluido_sai_do_dia_e_da_producao(sessao, cliente, cenario, lancar_em):
    """A tela do dia e o "produzido" do financeiro leem a mesma coluna.

    Sao dois filtros diferentes em dois modulos (`_do_dia` e
    `_realizados_no_periodo`); um teste so os prende juntos.
    """
    clinica, *_ = cenario
    lancar_em(dente=16, valor="180.00")
    fica = lancar_em(dente=24, valor="90.00")
    vai = lancar_em(dente=36, valor="200.00")

    cliente.delete(f"/api/lancamento/{vai.id}")

    grupos = atendimentos_do_dia(sessao, clinica_id=clinica.id, dia=DIA)
    assert [g["quantos"] for g in grupos] == [2]
    assert grupos[0]["total"] == Decimal("270.00")
    assert vai.id not in {i["lancamento_id"] for i in grupos[0]["itens"]}
    assert fica.id in {i["lancamento_id"] for i in grupos[0]["itens"]}

    feito = producao(sessao, clinica_id=clinica.id, de=DIA, ate=DIA)
    assert feito["valor"] == Decimal("270.00")
    assert feito["tratamentos"] == 2


def test_o_ultimo_tratamento_excluido_esvazia_o_dia(sessao, cliente, cenario, lancar_em):
    clinica, *_ = cenario
    unico = lancar_em()

    cliente.delete(f"/api/lancamento/{unico.id}")

    assert atendimentos_do_dia(sessao, clinica_id=clinica.id, dia=DIA) == []


# --- a tela --------------------------------------------------------------------


def test_a_tela_do_dia_traz_o_botao_de_excluir_em_cada_linha(cliente, lancar_em):
    lancamento = lancar_em()

    html = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "excluir-lancamento" in html
    assert f'data-lancamento="{lancamento.id}"' in html


def test_a_linha_carrega_o_que_a_confirmacao_precisa_dizer(cliente, lancar_em):
    """A frase e "Excluir Restauracao do dente 16?" — os dois vem da propria linha."""
    lancar_em(dente=16)

    html = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert 'data-dente="16"' in html
    assert 'data-procedimento="Restauracao"' in html


def test_o_planejado_do_dia_tambem_da_para_excluir(cliente, lancar_em):
    """Cancelar um planejamento errado e o mesmo gesto: os dois blocos usam o
    mesmo macro, e um planejado lancado por engano nao tem outro caminho de saida."""
    planejado = lancar_em(dente=24, status=StatusLancamento.PLANEJADO)

    html = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert f'data-lancamento="{planejado.id}"' in html


def test_a_tela_do_dia_carrega_o_javascript_da_exclusao(cliente, lancar_em):
    lancar_em()

    html = cliente.get(f"/atendimentos?dia={DIA.isoformat()}").text

    assert "atendimentos.js" in html
