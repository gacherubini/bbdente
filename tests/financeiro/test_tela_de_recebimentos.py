"""A tela dos recebimentos: ver o dinheiro que entrou, corrigir e apagar.

Os atendimentos ja tinham uma tela do dia onde a dentista ve o que lancou e
apaga o que errou. O dinheiro nao tinha: dava para registrar um recebimento e
nunca mais ve-lo de perto — so somado dentro do cartao "Recebido". Esta tela e a
irma daquela, no eixo do mes.

Editar tem a mesma trava do desfazer, e pelo mesmo motivo: so o que a clinica
registrou pelo sistema se mexe. As 28.244 parcelas do Dentalis sao historico.
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
    a_receber_total,
    editar_recebimento,
    recebido,
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
        forma="Pix",
        observacao="entrada do canal",
    )


def uma_do_dentalis(sessao, cenario) -> Parcela:
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
    return historica


def editar(sessao, cenario, parcela, **mudancas):
    dados = {
        "valor": Decimal("2400.00"),
        "quando": HOJE,
        "forma": "Pix",
        "observacao": "entrada do canal",
    }
    dados.update(mudancas)
    return editar_recebimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        parcela_id=parcela.id,
        **dados,
    )


# --- pela service -----------------------------------------------------------

def test_corrigir_o_valor_muda_a_soma_do_mes(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    editar(sessao, cenario, parcela, valor=Decimal("240.00"))
    sessao.flush()
    assert recebido(
        sessao, clinica_id=cenario["clinica"].id, de=DE, ate=ATE
    ) == Decimal("240.00")


def test_corrigir_para_menos_nao_inventa_divida(sessao, cenario):
    """O recebimento avulso nasce quitado (cobrado == pago). Baixar so o pago
    deixaria um saldo de R$ 2.160 na lista de cobranca — a clinica passaria a
    cobrar da paciente um erro de digitacao da propria clinica."""
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    editar(sessao, cenario, parcela, valor=Decimal("240.00"))
    sessao.flush()
    assert a_receber_total(
        sessao, clinica_id=cenario["clinica"].id, de=DE, ate=ATE
    ) == Decimal("0.00")


def test_corrigir_a_data_tira_o_dinheiro_do_mes_errado(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    editar(sessao, cenario, parcela, quando=date(2026, 7, 3))
    sessao.flush()
    cid = cenario["clinica"].id
    assert recebido(sessao, clinica_id=cid, de=DE, ate=ATE) == Decimal("0.00")
    assert recebido(
        sessao, clinica_id=cid, de=date(2026, 7, 1), ate=date(2026, 7, 31)
    ) == Decimal("2400.00")


def test_corrigir_forma_e_observacao(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    editar(sessao, cenario, parcela, forma="Dinheiro", observacao="era em espécie")
    sessao.flush()
    viva = sessao.get(Parcela, parcela.id)
    assert viva.forma_pagamento == "Dinheiro"
    assert viva.observacao == "era em espécie"


def test_apagar_a_observacao_apaga_mesmo(sessao, cenario):
    """Campo esvaziado no formulario e uma correcao como outra qualquer: se
    'ficar como estava' fosse a regra, nao haveria como desfazer o que se
    digitou errado."""
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    editar(sessao, cenario, parcela, forma=None, observacao=None)
    sessao.flush()
    viva = sessao.get(Parcela, parcela.id)
    assert viva.forma_pagamento is None
    assert viva.observacao is None


def test_editar_deixa_o_antes_e_o_depois_na_auditoria(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    editar(sessao, cenario, parcela, valor=Decimal("240.00"))
    sessao.flush()
    linha = sessao.scalars(
        select(Auditoria)
        .where(Auditoria.entidade == "parcela", Auditoria.acao == "ATUALIZAR")
        .order_by(Auditoria.id.desc())
    ).first()
    assert linha is not None
    assert linha.entidade_id == parcela.id
    assert linha.dados_antes["valor_pago"] == "2400.00"
    assert linha.dados_depois["valor_pago"] == "240.00"


def test_nao_edita_parcela_que_veio_do_dentalis(sessao, cenario):
    historica = uma_do_dentalis(sessao, cenario)
    with pytest.raises(RecebimentoInvalido, match="Dentalis|hist"):
        editar(sessao, cenario, historica, valor=Decimal("1.00"))
    assert sessao.get(Parcela, historica.id).valor_pago == Decimal("300.00")


def test_nao_edita_recebimento_de_outra_clinica(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    with pytest.raises(LookupError):
        editar_recebimento(
            sessao,
            clinica_id=cenario["clinica"].id + 999,
            usuario_id=cenario["usuario"].id,
            parcela_id=parcela.id,
            valor=Decimal("10.00"),
            quando=HOJE,
        )


def test_nao_edita_recebimento_ja_desfeito(sessao, cenario):
    from app.financeiro.service import excluir_recebimento

    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    excluir_recebimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        parcela_id=parcela.id,
    )
    sessao.flush()
    with pytest.raises(LookupError):
        editar(sessao, cenario, parcela, valor=Decimal("10.00"))


def test_valor_zero_nao_e_recebimento(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    with pytest.raises(RecebimentoInvalido):
        editar(sessao, cenario, parcela, valor=Decimal("0.00"))


def test_data_no_futuro_nao_e_recebimento(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    with pytest.raises(RecebimentoInvalido):
        editar(
            sessao, cenario, parcela,
            quando=date(date.today().year + 1, 1, 1),
        )


# --- pela tela --------------------------------------------------------------

def test_a_tela_lista_o_recebimento_com_forma_e_observacao(sessao, cenario, cliente):
    um_recebimento(sessao, cenario)
    sessao.flush()
    corpo = cliente.get("/recebimentos?ano=2026&mes=8").text
    assert "Amanda" in corpo
    assert "2.400,00" in corpo
    assert "Pix" in corpo
    assert "entrada do canal" in corpo
    assert "editar" in corpo.lower()
    assert "desfazer" in corpo.lower()


def test_a_tela_marca_a_aba_recebimentos(sessao, cenario, cliente):
    """Aba propria na lateral, e nao o Financeiro aceso: quem esta em
    Recebimentos precisa ver onde esta."""
    corpo = cliente.get("/recebimentos?ano=2026&mes=8").text
    assert 'href="/recebimentos" class="ativo"' in corpo
    assert 'href="/financeiro" class="ativo"' not in corpo


def test_a_tela_de_recebimentos_exige_sessao(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as sem_sessao:
        resposta = sem_sessao.get("/recebimentos")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_a_tela_nao_oferece_editar_nem_desfazer_no_que_veio_do_dentalis(
    sessao, cenario, cliente
):
    historica = uma_do_dentalis(sessao, cenario)
    corpo = cliente.get("/recebimentos?ano=2015&mes=3").text
    assert "Amanda" in corpo
    assert "histórico" in corpo.lower()
    assert f"/financeiro/recebimento/{historica.id}/editar" not in corpo
    assert f"/financeiro/recebimento/{historica.id}/desfazer" not in corpo


def test_o_formulario_de_edicao_vem_preenchido(sessao, cenario, cliente):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    corpo = cliente.get(f"/financeiro/recebimento/{parcela.id}/editar").text
    assert "2.400,00" in corpo
    assert "2026-08-26" in corpo
    assert "entrada do canal" in corpo


def test_editar_pela_tela_muda_o_valor_e_volta_para_a_lista(sessao, cenario, cliente):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    resposta = cliente.post(
        f"/financeiro/recebimento/{parcela.id}/editar",
        data={
            "valor": "240,00",
            "data": "2026-08-26",
            "forma": "Dinheiro",
            "observacao": "era em espécie",
        },
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/recebimentos?ano=2026&mes=8"
    assert recebido(
        sessao, clinica_id=cenario["clinica"].id, de=DE, ate=ATE
    ) == Decimal("240.00")


def test_valor_impossivel_volta_o_formulario_com_erro_sem_gravar(
    sessao, cenario, cliente
):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    resposta = cliente.post(
        f"/financeiro/recebimento/{parcela.id}/editar",
        data={"valor": "abacaxi", "data": "2026-08-26", "forma": "", "observacao": ""},
    )
    assert resposta.status_code == 200
    assert "abacaxi" in resposta.text
    assert sessao.get(Parcela, parcela.id).valor_pago == Decimal("2400.00")


def test_a_url_da_edicao_protege_o_historico(sessao, cenario, cliente):
    historica = uma_do_dentalis(sessao, cenario)
    assert cliente.get(
        f"/financeiro/recebimento/{historica.id}/editar"
    ).status_code == 422
    resposta = cliente.post(
        f"/financeiro/recebimento/{historica.id}/editar",
        data={"valor": "1,00", "data": "2015-03-10", "forma": "", "observacao": ""},
    )
    assert resposta.status_code == 422
    assert sessao.get(Parcela, historica.id).valor_pago == Decimal("300.00")


def test_editar_exige_sessao(sessao, cenario):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as sem_sessao:
        resposta = sem_sessao.post(
            f"/financeiro/recebimento/{parcela.id}/editar",
            data={"valor": "1,00", "data": "2026-08-26"},
        )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"
    assert sessao.get(Parcela, parcela.id).valor_pago == Decimal("2400.00")


def test_desfazer_pela_tela_de_recebimentos_volta_para_ela(sessao, cenario, cliente):
    """Quem apagou na lista de recebimentos quer continuar na lista, e nao ser
    jogado no painel do financeiro."""
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    resposta = cliente.post(
        f"/financeiro/recebimento/{parcela.id}/desfazer",
        data={"ano": "2026", "mes": "8", "voltar": "recebimentos"},
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/recebimentos?ano=2026&mes=8"
    assert sessao.get(Parcela, parcela.id).excluido_em is not None


def test_voltar_inventado_nao_vira_redirecionamento_para_fora(sessao, cenario, cliente):
    parcela = um_recebimento(sessao, cenario)
    sessao.flush()
    resposta = cliente.post(
        f"/financeiro/recebimento/{parcela.id}/desfazer",
        data={"ano": "2026", "mes": "8", "voltar": "https://exemplo.invalido"},
    )
    assert resposta.headers["location"] == "/financeiro?ano=2026&mes=8"
