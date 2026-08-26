"""Editar um lancamento ja feito: valor, situacao, data e observacao.

O que esta tela NAO muda, de proposito: dente, regiao e procedimento. Trocar o
alvo de um tratamento nao e correcao, e outro tratamento — e para isso ja existe
excluir (logicamente) e lancar de novo, que deixa os dois na auditoria.

E a data e uma so por vez: um lancamento planejado tem data planejada, um
realizado tem data realizada. Guardar as duas seria guardar uma contradicao.
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
from app.clinico.service import excluir_lancamento, lancar
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
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([restauracao, paciente])
    sessao.flush()
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL], status=StatusLancamento.PLANEJADO,
        data=date(2026, 5, 10), valor=Decimal("180.00"),
    )
    sessao.flush()
    return clinica, usuario, paciente, restauracao, lancamento


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def corpo(**extra) -> dict:
    dados = {"status": "PLANEJADO", "valor": "180.00", "data": "2026-05-10"}
    dados.update(extra)
    return dados


# --- editar --------------------------------------------------------------------


def test_editar_o_valor_grava_e_devolve_o_estado_novo(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00")
    )
    assert resposta.status_code == 200
    assert resposta.json()["estado"]["dentes"]["16"]["regioes"]["MESIAL"] == "PLANEJADO"
    sessao.refresh(lancamento)
    assert lancamento.valor == Decimal("250.00")


def test_a_edicao_deixa_antes_e_depois_na_auditoria(sessao, cliente, cenario):
    _, usuario, _, _, lancamento = cenario
    cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00"))
    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "lancamento", Auditoria.acao == "ATUALIZAR"
        )
    ).one()
    assert linha.dados_antes["valor"] == "180.00"
    assert linha.dados_depois["valor"] == "250.00"
    assert linha.usuario_id == usuario.id


def test_editar_a_observacao_funciona(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=corpo(observacao="paciente pediu para adiar"),
    )
    sessao.refresh(lancamento)
    assert lancamento.observacao == "paciente pediu para adiar"


# --- a data segue a situacao ---------------------------------------------------


def test_virar_realizado_move_a_data_de_planejada_para_realizada(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    assert lancamento.data_planejada == date(2026, 5, 10)

    cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=corpo(status="REALIZADO", data="2026-05-12"),
    )
    sessao.refresh(lancamento)
    assert lancamento.status is StatusLancamento.REALIZADO
    assert lancamento.data_realizada == date(2026, 5, 12)
    assert lancamento.data_planejada is None


def test_voltar_para_planejado_devolve_a_data(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(status="REALIZADO", data="2026-05-12")
    )
    cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(status="PLANEJADO", data="2026-06-01")
    )
    sessao.refresh(lancamento)
    assert lancamento.status is StatusLancamento.PLANEJADO
    assert lancamento.data_planejada == date(2026, 6, 1)
    assert lancamento.data_realizada is None


def test_lancamento_pode_ficar_sem_data(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(data=None))
    sessao.refresh(lancamento)
    assert lancamento.data_planejada is None
    assert lancamento.data_realizada is None


def test_virar_realizado_muda_a_cor_no_desenho(cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(status="REALIZADO")
    )
    dente = resposta.json()["estado"]["dentes"]["16"]
    assert dente["regioes"]["MESIAL"] == "REALIZADO"


# --- o que a edicao recusa -----------------------------------------------------


def test_valor_negativo_e_recusado(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="-10"))
    assert resposta.status_code == 422
    sessao.refresh(lancamento)
    assert lancamento.valor == Decimal("180.00")


def test_data_invalida_e_recusada(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(data="30/02/2026")
    )
    assert resposta.status_code == 422


def test_lancamento_excluido_nao_pode_ser_editado(sessao, cliente, cenario):
    """Editar o que foi apagado seria ressuscitar sem deixar claro que ressuscitou."""
    clinica, usuario, _, _, lancamento = cenario
    excluir_lancamento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, lancamento_id=lancamento.id
    )
    sessao.flush()
    resposta = cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="250"))
    assert resposta.status_code == 404


def test_lancamento_inexistente_da_404(cliente):
    assert cliente.patch("/api/lancamento/999999", json=corpo()).status_code == 404


def test_lancamento_de_outra_clinica_da_404(sessao, cliente, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    usuario_alheio = criar_usuario(
        sessao, clinica_id=outra.id, email="x@e.com", senha="senha-longa", nome="X"
    )
    categoria = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=outra.id, codigo="21", nome="Alheio", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add_all([procedimento, paciente])
    sessao.flush()
    alheio = lancar(
        sessao, clinica_id=outra.id, usuario_id=usuario_alheio.id,
        paciente_id=paciente.id, procedimento_id=procedimento.id,
        escopo=Escopo.DENTE, dente=16, status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    resposta = cliente.patch(f"/api/lancamento/{alheio.id}", json=corpo(valor="250"))
    assert resposta.status_code == 404
    sessao.refresh(alheio)
    assert alheio.valor == Decimal("0.00")


def test_a_edicao_nao_mexe_em_dente_nem_em_regiao(sessao, cliente, cenario):
    """Trocar o alvo nao e correcao, e outro tratamento — exclui e lanca de novo."""
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=corpo(dente=26, escopo="DENTE", regioes=["DISTAL"]),
    )
    sessao.refresh(lancamento)
    assert lancamento.dente == 16
    assert lancamento.escopo is Escopo.REGIOES


def test_sem_sessao_e_recusada(sessao, cenario):
    _, _, _, _, lancamento = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        resposta = anonimo.patch(f"/api/lancamento/{lancamento.id}", json=corpo())
        assert resposta.status_code == 303


# --- a tela --------------------------------------------------------------------


def test_o_historico_do_odontograma_traz_o_id_de_cada_lancamento(cliente, cenario):
    """Sem o id na linha, o JavaScript nao tem como dizer qual editar."""
    _, _, paciente, _, lancamento = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert f'data-lancamento="{lancamento.id}"' in html


def test_o_historico_e_editavel_na_tela_do_paciente(cliente, cenario):
    _, _, paciente, *_ = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert "editar" in html.lower()


def test_o_lancamento_guardado_continua_no_banco_apos_editar(sessao, cliente, cenario):
    """Editar troca o valor da linha; nunca cria uma segunda nem apaga a primeira."""
    _, _, _, _, lancamento = cenario
    cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00"))
    todos = sessao.scalars(select(Lancamento)).all()
    assert len(todos) == 1
    assert todos[0].id == lancamento.id
