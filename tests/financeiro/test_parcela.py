"""A tabela `parcela`: uma cobranca do paciente, paga ou nao.

Uma tabela so para as duas coisas. Recebimento e parcela com `pago_em`
preenchido — duas tabelas guardariam a mesma verdade em dois lugares, e um dos
dois envelheceria errado.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.auth.models import Clinica
from app.financeiro.models import Parcela
from app.pacientes.models import Paciente


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add(paciente)
    sessao.flush()
    return clinica, paciente


def nova(clinica, paciente, **extra) -> Parcela:
    dados = {
        "clinica_id": clinica.id,
        "paciente_id": paciente.id,
        "numero": "01/01",
        "vencimento": date(2026, 5, 10),
        "valor_cobrado": Decimal("180.00"),
    }
    dados.update(extra)
    return Parcela(**dados)


def test_grava_e_le_uma_parcela(sessao, cenario):
    clinica, paciente = cenario
    sessao.add(nova(clinica, paciente))
    sessao.flush()
    guardada = sessao.scalars(select(Parcela)).one()
    assert guardada.valor_cobrado == Decimal("180.00")
    assert guardada.valor_pago == Decimal("0.00")
    assert guardada.pago_em is None
    assert guardada.revisar_motivo == []


def test_o_saldo_e_derivado_e_nao_coluna(sessao, cenario):
    """Saldo em coluna e a mesma verdade em dois lugares, e um deles envelhece
    errado assim que alguem corrigir o valor pago."""
    colunas = {c["name"] for c in inspect(sessao.get_bind()).get_columns("parcela")}
    assert "saldo" not in colunas


def test_saldo_do_que_nao_foi_pago_e_o_valor_inteiro(sessao, cenario):
    clinica, paciente = cenario
    parcela = nova(clinica, paciente)
    assert parcela.saldo == Decimal("180.00")
    assert parcela.quitada is False


def test_pagamento_parcial_deixa_saldo(sessao, cenario):
    """7.849 linhas do Dentalis sao assim: tem data de pagamento e sobrou saldo."""
    clinica, paciente = cenario
    parcela = nova(
        clinica, paciente, pago_em=date(2026, 6, 1), valor_pago=Decimal("50.00")
    )
    assert parcela.saldo == Decimal("130.00")
    assert parcela.quitada is False


def test_parcela_paga_por_inteiro_esta_quitada(sessao, cenario):
    clinica, paciente = cenario
    parcela = nova(
        clinica, paciente, pago_em=date(2026, 6, 1), valor_pago=Decimal("180.00")
    )
    assert parcela.saldo == Decimal("0.00")
    assert parcela.quitada is True


def test_pagar_a_mais_vira_saldo_negativo(sessao, cenario):
    """Sao 112 linhas assim no historico: credito do paciente, nao erro."""
    clinica, paciente = cenario
    parcela = nova(
        clinica, paciente, pago_em=date(2026, 6, 1), valor_pago=Decimal("200.00")
    )
    assert parcela.saldo == Decimal("-20.00")
    assert parcela.quitada is True


def test_a_parcela_guarda_a_marca_de_revisao(sessao, cenario):
    """21 linhas do ARQFAT tem data impossivel (ano 0200, 9200): entram marcadas."""
    clinica, paciente = cenario
    sessao.add(
        nova(clinica, paciente, revisar_motivo=["data_impossivel"])
    )
    sessao.flush()
    assert sessao.scalars(select(Parcela)).one().revisar_motivo == ["data_impossivel"]


def test_a_parcela_guarda_o_codigo_do_dentalis(sessao, cenario):
    clinica, paciente = cenario
    sessao.add(nova(clinica, paciente, codigo_legado="0001/PT|01/01|1996-09-03"))
    sessao.flush()
    assert sessao.scalars(select(Parcela)).one().codigo_legado == "0001/PT|01/01|1996-09-03"


def test_a_exclusao_e_logica(sessao, cenario):
    clinica, paciente = cenario
    parcela = nova(clinica, paciente)
    sessao.add(parcela)
    sessao.flush()
    parcela.excluido_em = datetime.now(UTC)
    sessao.flush()
    assert sessao.get(Parcela, parcela.id) is not None


def test_parcela_exige_paciente(sessao, cenario):
    clinica, _ = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id, paciente_id=999999,
            vencimento=date(2026, 5, 10), valor_cobrado=Decimal("10.00"),
        )
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_os_indices_dos_dois_eixos_de_consulta_existem(sessao):
    """'Quanto entrou no periodo' e 'o que venceu e nao foi pago' — as duas
    perguntas que o modulo faz o tempo todo, sobre 28 mil linhas."""
    indices = {i["name"] for i in inspect(sessao.get_bind()).get_indexes("parcela")}
    assert "ix_parcela_clinica_pago_em" in indices
    assert "ix_parcela_clinica_vencimento" in indices
