"""Migracao do ARQFAT: as 28.244 parcelas, o livro-caixa de 30 anos.

Estes testes migram so pacientes e financeiro — nao precisam dos 44.812
lancamentos, e por isso rodam em segundos em vez de minutos.
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.financeiro.models import Parcela
from app.pacientes.models import Paciente
from migracao.extrato import Extrato

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture
def caixa_migrado(sessao):
    from migracao import financeiro, pacientes

    clinica = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        pacientes.migrar(sessao, extrato, clinica.id)
        resultado = financeiro.migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica, resultado


def test_traz_as_28244_parcelas(sessao, caixa_migrado):
    assert sessao.query(Parcela).count() == 28_244


def test_a_soma_cobrada_bate_ao_centavo(sessao, caixa_migrado):
    soma = sessao.query(func.sum(Parcela.valor_cobrado)).scalar()
    assert Decimal(soma).quantize(Decimal("0.01")) == Decimal("5808797.26")


def test_a_soma_paga_bate_ao_centavo(sessao, caixa_migrado):
    """R$ 2.378.315,73 — e a soma dos lancamentos realizados ja migrados da
    R$ 2.374.762,13. Duas fontes independentes contando a mesma coisa."""
    soma = sessao.query(func.sum(Parcela.valor_pago)).scalar()
    assert Decimal(soma).quantize(Decimal("0.01")) == Decimal("2378315.73")


def test_7546_parcelas_nunca_foram_pagas(sessao, caixa_migrado):
    assert sessao.query(Parcela).filter(Parcela.pago_em.is_(None)).count() == 7_546


def test_quem_nao_pagou_nao_tem_valor_pago(sessao, caixa_migrado):
    """Sem data de pagamento e com dinheiro registrado seria contradicao."""
    contraditorias = (
        sessao.query(Parcela)
        .filter(Parcela.pago_em.is_(None), Parcela.valor_pago > 0)
        .count()
    )
    assert contraditorias == 0


def test_o_que_esta_em_aberto_de_verdade_conta_o_pagamento_parcial(sessao, caixa_migrado):
    """7.849 parcelas foram pagas pela metade: tem data de pagamento e sobrou
    saldo. Somar so as parcelas sem data daria R$ 1.299.587,61 — menos da metade
    da divida real."""
    cobrado = Decimal(sessao.query(func.sum(Parcela.valor_cobrado)).scalar())
    pago = Decimal(sessao.query(func.sum(Parcela.valor_pago)).scalar())
    assert (cobrado - pago).quantize(Decimal("0.01")) == Decimal("3430481.53")

    sem_data = Decimal(
        sessao.query(func.coalesce(func.sum(Parcela.valor_cobrado), 0))
        .filter(Parcela.pago_em.is_(None))
        .scalar()
    )
    assert sem_data.quantize(Decimal("0.01")) == Decimal("1299587.61")


def test_toda_parcela_tem_dono_e_nenhum_e_orfao(sessao, caixa_migrado):
    orfas = (
        sessao.query(Parcela)
        .outerjoin(Paciente, Parcela.paciente_id == Paciente.id)
        .filter(Paciente.id.is_(None))
        .count()
    )
    assert orfas == 0


def test_5340_pacientes_tem_parcela(sessao, caixa_migrado):
    quantos = sessao.query(func.count(func.distinct(Parcela.paciente_id))).scalar()
    assert quantos == 5_340


def test_as_cinco_datas_impossiveis_entram_marcadas(sessao, caixa_migrado):
    """Ano 0200, 0202, 0203 e 9200. A data entra como veio, marcada — chutar o
    seculo seria inventar um fato financeiro."""
    marcadas = sessao.scalars(
        select(Parcela).where(func.cardinality(Parcela.revisar_motivo) > 0)
    ).all()
    assert len(marcadas) == 5
    assert {m for p in marcadas for m in p.revisar_motivo} == {"data_suspeita"}


def test_forma_de_pagamento_vazia_nao_vira_a_string_00(sessao, caixa_migrado):
    """28.234 das 28.244 linhas tem CODTPAG '00', que no ARQTPAG e vazio. Gravar
    '00' fingiria uma informacao que o Dentalis nunca teve."""
    assert sessao.query(Parcela).filter(Parcela.forma_pagamento == "00").count() == 0
    com_forma = sessao.query(Parcela).filter(Parcela.forma_pagamento.isnot(None)).count()
    assert com_forma == 6


def test_a_parcela_guarda_de_onde_veio(sessao, caixa_migrado):
    sem_codigo = sessao.query(Parcela).filter(Parcela.codigo_legado.is_(None)).count()
    assert sem_codigo == 0


def test_rodar_de_novo_nao_duplica(sessao, caixa_migrado):
    from migracao import financeiro

    clinica, _ = caixa_migrado
    with Extrato(EXTRATO) as extrato:
        segunda = financeiro.migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert sessao.query(Parcela).count() == 28_244
    assert segunda.ja_existiam == 28_244


def test_o_resultado_conta_o_que_gravou(caixa_migrado):
    _, resultado = caixa_migrado
    assert resultado.parcelas == 28_244
    assert resultado.marcadas == 5
    assert resultado.substituidas == 5_163
    assert resultado.soma_paga.quantize(Decimal("0.01")) == Decimal("2378315.73")


# --- carne: o Dentalis regravava o saldo a cada pagamento -----------------------


def test_as_linhas_superadas_de_um_carne_entram_marcadas(sessao, caixa_migrado):
    """3.014 grupos, 8.177 linhas: a ultima de cada grupo e a divida que sobrou,
    as 5.163 anteriores ja foram substituidas por ela."""
    marcadas = sessao.query(Parcela).filter(Parcela.substituida.is_(True)).count()
    assert marcadas == 5_163


def test_a_divida_real_e_menor_do_que_a_soma_ingenua(sessao, caixa_migrado):
    """Somar toda linha daria R$ 3.430.481,53 e contaria a mesma divida ate sete
    vezes. Pulando as substituidas, sobram R$ 2.037.593,22."""
    ingenua = Decimal(
        sessao.query(
            func.sum(Parcela.valor_cobrado - Parcela.valor_pago)
        ).scalar()
    ).quantize(Decimal("0.01"))
    assert ingenua == Decimal("3430481.53")

    real = Decimal(
        sessao.query(func.sum(Parcela.valor_cobrado - Parcela.valor_pago))
        .filter(Parcela.substituida.is_(False))
        .scalar()
    ).quantize(Decimal("0.01"))
    assert real == Decimal("2037593.22")


def test_o_dinheiro_recebido_conta_todos_os_degraus(sessao, caixa_migrado):
    """O que se conta duas vezes num carne e a divida, nunca o dinheiro: cada
    degrau registra um pagamento que aconteceu."""
    soma = sessao.query(func.sum(Parcela.valor_pago)).scalar()
    assert Decimal(soma).quantize(Decimal("0.01")) == Decimal("2378315.73")
    das_substituidas = sessao.query(func.sum(Parcela.valor_pago)).filter(
        Parcela.substituida.is_(True)
    ).scalar()
    assert Decimal(das_substituidas) > 0


def test_parcela_sozinha_nunca_e_marcada_como_substituida(sessao, caixa_migrado):
    """A regra so pega grupo de mesmo paciente e mesmo vencimento: toda linha
    marcada tem de ter ao menos uma irma que a substituiu."""
    grupos = sessao.execute(
        select(
            Parcela.paciente_id,
            Parcela.vencimento,
            func.count(),
            func.count().filter(Parcela.substituida.is_(True)),
        ).group_by(Parcela.paciente_id, Parcela.vencimento)
    ).all()
    solitarias = [
        (paciente_id, vencimento)
        for paciente_id, vencimento, total, marcadas in grupos
        if marcadas and total < 2
    ]
    assert solitarias == []


def test_o_grupo_marcado_sempre_guarda_uma_linha_nao_marcada(sessao, caixa_migrado):
    """A divida que sobrou tem de continuar visivel: marcar o grupo inteiro
    sumiria com ela da cobranca."""
    grupos = sessao.execute(
        select(
            Parcela.paciente_id,
            Parcela.vencimento,
            func.count(),
            func.count().filter(Parcela.substituida.is_(True)),
        ).group_by(Parcela.paciente_id, Parcela.vencimento)
    ).all()
    inteiros = [
        (paciente_id, vencimento)
        for paciente_id, vencimento, total, marcadas in grupos
        if marcadas and marcadas == total
    ]
    assert inteiros == []
