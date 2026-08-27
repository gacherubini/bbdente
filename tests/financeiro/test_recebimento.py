"""Registrar dinheiro que entrou.

Duas formas da mesma coisa: um recebimento avulso (vira parcela ja quitada) e a
quitacao de uma parcela que estava em aberto. Pagar menos que o saldo e
pagamento parcial, e o resto continua devido — e assim que o Dentalis registrou
7.849 parcelas em 30 anos, e assim continua sendo.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.financeiro.models import Parcela
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao

HOJE = date.today()


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    paciente = Paciente(
        clinica_id=clinica.id, codigo_legado="0001/PT", nome="AMANDA ROSA"
    )
    sessao.add(paciente)
    sessao.flush()
    return clinica, usuario, paciente


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        yield c


def em_aberto(sessao, cenario, cobrado="300.00", pago="0"):
    clinica, _, paciente = cenario
    parcela = Parcela(
        clinica_id=clinica.id, paciente_id=paciente.id, numero="01/01",
        vencimento=HOJE - timedelta(days=30),
        valor_cobrado=Decimal(cobrado), valor_pago=Decimal(pago),
    )
    sessao.add(parcela)
    sessao.flush()
    return parcela


def formulario(**extra) -> dict:
    dados = {"valor": "150,00", "data": HOJE.isoformat(), "forma": "Dinheiro"}
    dados.update(extra)
    return dados


# --- a tela --------------------------------------------------------------------


def test_a_tela_de_recebimento_abre_para_um_paciente(cliente, cenario):
    _, _, paciente = cenario
    resposta = cliente.get(f"/financeiro/recebimento?paciente_id={paciente.id}")
    assert resposta.status_code == 200
    assert "AMANDA ROSA" in resposta.text


def test_a_tela_de_quitacao_ja_vem_com_o_saldo(sessao, cliente, cenario):
    parcela = em_aberto(sessao, cenario, cobrado="300.00", pago="50.00")
    html = cliente.get(f"/financeiro/recebimento?parcela_id={parcela.id}").text
    assert "250,00" in html


def test_paciente_de_outra_clinica_da_404(sessao, cliente):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra")
    sessao.add(alheio)
    sessao.flush()
    resposta = cliente.get(f"/financeiro/recebimento?paciente_id={alheio.id}")
    assert resposta.status_code == 404


def test_a_tela_do_paciente_oferece_registrar_recebimento(cliente, cenario):
    _, _, paciente = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert f"/financeiro/recebimento?paciente_id={paciente.id}" in html


# --- recebimento avulso ---------------------------------------------------------


def test_recebimento_avulso_entra_quitado(sessao, cliente, cenario):
    _, _, paciente = cenario
    resposta = cliente.post(
        "/financeiro/recebimento", data=formulario(paciente_id=str(paciente.id))
    )
    assert resposta.status_code == 303
    parcela = sessao.scalars(select(Parcela)).one()
    assert parcela.valor_cobrado == Decimal("150.00")
    assert parcela.valor_pago == Decimal("150.00")
    assert parcela.pago_em == HOJE
    assert parcela.saldo == Decimal("0.00")
    assert parcela.forma_pagamento == "Dinheiro"


def test_recebimento_avulso_aparece_no_recebido_do_mes(sessao, cliente, cenario):
    from app.financeiro.service import recebido

    clinica, _, paciente = cenario
    cliente.post(
        "/financeiro/recebimento", data=formulario(paciente_id=str(paciente.id))
    )
    entrou = recebido(
        sessao, clinica_id=clinica.id,
        de=HOJE.replace(day=1), ate=HOJE,
    )
    assert entrou == Decimal("150.00")


def test_o_recebimento_deixa_rastro_na_auditoria(sessao, cliente, cenario):
    _, usuario, paciente = cenario
    cliente.post(
        "/financeiro/recebimento", data=formulario(paciente_id=str(paciente.id))
    )
    linha = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "parcela")
    ).one()
    assert linha.acao == "CRIAR"
    assert linha.usuario_id == usuario.id
    assert linha.dados_depois["valor_pago"] == "150.00"


# --- quitar uma parcela em aberto ------------------------------------------------


def test_quitar_por_inteiro_zera_o_saldo(sessao, cliente, cenario):
    parcela = em_aberto(sessao, cenario, cobrado="300.00")
    cliente.post(
        "/financeiro/recebimento",
        data=formulario(parcela_id=str(parcela.id), valor="300,00"),
    )
    sessao.refresh(parcela)
    assert parcela.valor_pago == Decimal("300.00")
    assert parcela.pago_em == HOJE
    assert parcela.quitada is True


def test_pagar_menos_que_o_saldo_e_pagamento_parcial(sessao, cliente, cenario):
    parcela = em_aberto(sessao, cenario, cobrado="300.00")
    cliente.post(
        "/financeiro/recebimento",
        data=formulario(parcela_id=str(parcela.id), valor="50,00"),
    )
    sessao.refresh(parcela)
    assert parcela.valor_pago == Decimal("50.00")
    assert parcela.saldo == Decimal("250.00")
    assert parcela.quitada is False


def test_pagar_de_novo_soma_ao_que_ja_tinha_sido_pago(sessao, cliente, cenario):
    parcela = em_aberto(sessao, cenario, cobrado="300.00", pago="50.00")
    cliente.post(
        "/financeiro/recebimento",
        data=formulario(parcela_id=str(parcela.id), valor="100,00"),
    )
    sessao.refresh(parcela)
    assert parcela.valor_pago == Decimal("150.00")
    assert parcela.saldo == Decimal("150.00")


def test_quitar_nao_cria_parcela_nova(sessao, cliente, cenario):
    parcela = em_aberto(sessao, cenario)
    cliente.post(
        "/financeiro/recebimento",
        data=formulario(parcela_id=str(parcela.id), valor="300,00"),
    )
    assert sessao.scalars(select(func.count()).select_from(Parcela)).one() == 1


def test_a_quitacao_guarda_antes_e_depois_na_auditoria(sessao, cliente, cenario):
    parcela = em_aberto(sessao, cenario, cobrado="300.00")
    cliente.post(
        "/financeiro/recebimento",
        data=formulario(parcela_id=str(parcela.id), valor="300,00"),
    )
    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "parcela", Auditoria.acao == "ATUALIZAR"
        )
    ).one()
    assert linha.dados_antes["valor_pago"] == "0.00"
    assert linha.dados_depois["valor_pago"] == "300.00"


# --- o que o recebimento recusa --------------------------------------------------


def test_valor_zero_e_recusado(sessao, cliente, cenario):
    _, _, paciente = cenario
    resposta = cliente.post(
        "/financeiro/recebimento",
        data=formulario(paciente_id=str(paciente.id), valor="0,00"),
    )
    assert resposta.status_code == 200
    assert sessao.scalars(select(func.count()).select_from(Parcela)).one() == 0


def test_valor_negativo_e_recusado(sessao, cliente, cenario):
    _, _, paciente = cenario
    resposta = cliente.post(
        "/financeiro/recebimento",
        data=formulario(paciente_id=str(paciente.id), valor="-50,00"),
    )
    assert resposta.status_code == 200
    assert sessao.scalars(select(func.count()).select_from(Parcela)).one() == 0


def test_data_no_futuro_e_recusada(sessao, cliente, cenario):
    """Recebimento e fato, nao promessa: dinheiro que ainda nao entrou nao entra
    no caixa de hoje.

    `date.today()` lido AQUI, e nao o `HOJE` do topo do arquivo: aquele e
    avaliado na importacao, e a suite inteira roda depois. Em 27/08/2026 este
    teste falhou porque a suite atravessou a meia-noite entre uma leitura e a
    outra, e o "amanha" do teste virou o "hoje" do servico. A janela continua
    existindo — so encolheu de meia hora para microssegundos, porque a service
    do financeiro le o relogio por dentro.
    """
    _, _, paciente = cenario
    resposta = cliente.post(
        "/financeiro/recebimento",
        data=formulario(
            paciente_id=str(paciente.id),
            data=(date.today() + timedelta(days=1)).isoformat(),
        ),
    )
    assert resposta.status_code == 200
    assert sessao.scalars(select(func.count()).select_from(Parcela)).one() == 0


def test_sem_paciente_nem_parcela_e_recusado(sessao, cliente):
    assert cliente.post("/financeiro/recebimento", data=formulario()).status_code == 422


def test_parcela_de_outra_clinica_da_404(sessao, cliente, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra")
    sessao.add(alheio)
    sessao.flush()
    parcela = Parcela(
        clinica_id=outra.id, paciente_id=alheio.id, numero="01/01",
        vencimento=HOJE, valor_cobrado=Decimal("300.00"),
    )
    sessao.add(parcela)
    sessao.flush()
    resposta = cliente.post(
        "/financeiro/recebimento",
        data=formulario(parcela_id=str(parcela.id), valor="300,00"),
    )
    assert resposta.status_code == 404
    sessao.refresh(parcela)
    assert parcela.valor_pago == Decimal("0.00")
