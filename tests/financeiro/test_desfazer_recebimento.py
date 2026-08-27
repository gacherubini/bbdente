"""Desfazer um recebimento registrado por engano.

O caso real: a dentista lancou atendimentos sem querer, apagou os lancamentos, e
o "recebido" do mes nao mudou. Nao era conta errada — `parcela` nao tem vinculo
nenhum com `lancamento`, sao fatos independentes, e o sistema nao tem como saber
que aquele dinheiro era "daquele" tratamento. O que faltava era poder desfazer o
recebimento em si: o financeiro tinha tres rotas e nenhuma apagava.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.financeiro.models import Parcela
from app.financeiro.service import (
    RecebimentoInvalido,
    excluir_recebimento,
    recebido,
    recebimentos_do_periodo,
    registrar_recebimento,
)
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao

HOJE = date(2026, 8, 26)
DE, ATE = date(2026, 8, 1), date(2026, 8, 31)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add(paciente)
    sessao.flush()
    return {"clinica": clinica, "usuario": usuario, "paciente": paciente}


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def um_recebimento(sessao, cenario, valor="2400.00") -> Parcela:
    return registrar_recebimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=cenario["paciente"].id,
        valor=Decimal(valor),
        quando=HOJE,
    )


def test_desfazer_tira_o_dinheiro_da_soma_do_mes(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    cid = cenario["clinica"].id
    assert recebido(sessao, clinica_id=cid, de=DE, ate=ATE) == Decimal("2400.00")

    excluir_recebimento(
        sessao, clinica_id=cid, usuario_id=cenario["usuario"].id, parcela_id=parcela.id
    )
    sessao.flush()
    assert recebido(sessao, clinica_id=cid, de=DE, ate=ATE) == Decimal("0.00")


def test_desfazer_e_exclusao_logica_a_linha_continua_no_banco(sessao, cenario):
    """Guarda minima de 10 anos: nunca ha DELETE."""
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    excluir_recebimento(
        sessao, clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id, parcela_id=parcela.id,
    )
    sessao.flush()
    viva = sessao.get(Parcela, parcela.id)
    assert viva is not None
    assert viva.excluido_em is not None


def test_desfazer_deixa_rastro_na_auditoria(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    excluir_recebimento(
        sessao, clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id, parcela_id=parcela.id,
    )
    sessao.flush()
    linha = sessao.scalars(
        select(Auditoria)
        .where(Auditoria.entidade == "parcela", Auditoria.acao == "EXCLUIR")
        .order_by(Auditoria.id.desc())
    ).first()
    assert linha is not None
    assert linha.entidade_id == parcela.id


def test_nao_desfaz_parcela_que_veio_do_dentalis(sessao, cenario):
    """As 28.244 parcelas migradas nao foram registradas aqui e nao sao 'engano
    de digitacao': apagar uma delas e apagar historico de 30 anos. So o que a
    clinica registrou pelo sistema pode ser desfeito."""
    historica = Parcela(
        clinica_id=cenario["clinica"].id,
        paciente_id=cenario["paciente"].id,
        vencimento=date(2015, 3, 10),
        valor_cobrado=Decimal("300.00"),
        valor_pago=Decimal("300.00"),
        pago_em=date(2015, 3, 10),
        codigo_legado="0001|01|10/03/2015",
    )
    sessao.add(historica)
    sessao.flush()
    with pytest.raises(RecebimentoInvalido, match="Dentalis|hist"):
        excluir_recebimento(
            sessao, clinica_id=cenario["clinica"].id,
            usuario_id=cenario["usuario"].id, parcela_id=historica.id,
        )
    assert sessao.get(Parcela, historica.id).excluido_em is None


def test_desfazer_duas_vezes_nao_explode(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    cid, uid = cenario["clinica"].id, cenario["usuario"].id
    assert excluir_recebimento(sessao, clinica_id=cid, usuario_id=uid, parcela_id=parcela.id)
    sessao.flush()
    assert not excluir_recebimento(sessao, clinica_id=cid, usuario_id=uid, parcela_id=parcela.id)


def test_recebimento_de_outra_clinica_nao_e_desfeito(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    assert not excluir_recebimento(
        sessao, clinica_id=cenario["clinica"].id + 999,
        usuario_id=cenario["usuario"].id, parcela_id=parcela.id,
    )


def test_a_lista_do_periodo_traz_o_que_da_para_desfazer(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    linhas = recebimentos_do_periodo(
        sessao, clinica_id=cenario["clinica"].id, de=DE, ate=ATE
    )
    assert [linha.parcela_id for linha in linhas] == [parcela.id]
    assert linhas[0].paciente == "Amanda"
    assert linhas[0].valor == Decimal("2400.00")
    assert linhas[0].pode_desfazer is True


def test_a_lista_nao_mostra_o_que_ja_foi_desfeito(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    excluir_recebimento(
        sessao, clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id, parcela_id=parcela.id,
    )
    sessao.flush()
    assert recebimentos_do_periodo(
        sessao, clinica_id=cenario["clinica"].id, de=DE, ate=ATE
    ) == []


# --- pela tela --------------------------------------------------------------

def test_a_tela_do_financeiro_lista_o_recebimento_com_o_desfazer(sessao, cenario, cliente):
    um_recebimento(sessao, cenario)
    sessao.flush()
    corpo = cliente.get("/financeiro?ano=2026&mes=8").text
    assert "Amanda" in corpo
    assert "desfazer" in corpo.lower()


def test_desfazer_pela_tela_muda_o_recebido(sessao, cenario, cliente):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    resposta = cliente.post(f"/financeiro/recebimento/{parcela.id}/desfazer")
    assert resposta.status_code == 303
    assert recebido(
        sessao, clinica_id=cenario["clinica"].id, de=DE, ate=ATE
    ) == Decimal("0.00")


def test_desfazer_pela_tela_volta_para_o_mes_que_estava_aberto(sessao, cenario, cliente):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    resposta = cliente.post(
        f"/financeiro/recebimento/{parcela.id}/desfazer",
        data={"ano": "2026", "mes": "8"},
    )
    assert resposta.headers["location"] == "/financeiro?ano=2026&mes=8"


def test_a_url_do_desfazer_tambem_protege_o_historico(sessao, cenario, cliente):
    """A tela nao oferece o botao para parcela do Dentalis; a trava nao pode
    depender disso — quem chegar pela URL tambem nao apaga historico."""
    historica = Parcela(
        clinica_id=cenario["clinica"].id,
        paciente_id=cenario["paciente"].id,
        vencimento=date(2015, 3, 10),
        valor_cobrado=Decimal("300.00"),
        valor_pago=Decimal("300.00"),
        pago_em=date(2015, 3, 10),
        codigo_legado="0001|01|10/03/2015",
    )
    sessao.add(historica)
    sessao.flush()
    resposta = cliente.post(f"/financeiro/recebimento/{historica.id}/desfazer")
    assert resposta.status_code == 422
    assert sessao.get(Parcela, historica.id).excluido_em is None


def test_desfazer_exige_sessao(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as sem_sessao:
        resposta = sem_sessao.post(f"/financeiro/recebimento/{parcela.id}/desfazer")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"
    assert sessao.get(Parcela, parcela.id).excluido_em is None
