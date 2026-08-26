"""As agregacoes do financeiro.

Dois numeros diferentes de proposito, e o resto do modulo depende de nao
confundi-los:

- **Recebido** e dinheiro que entrou no periodo (`parcela.valor_pago`).
- **Produzido** e tratamento feito no periodo (`lancamento.valor`).

Um tratamento feito em marco pode ser pago em julho. Mostrar os dois lado a lado
e o que deixa isso visivel em vez de escondido numa media.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.clinico.service import lancar
from app.financeiro.models import Parcela
from app.financeiro.service import (
    a_receber,
    anos_com_movimento,
    producao_por_categoria,
    producao_por_convenio,
    producao_por_dia,
    recebido_por_mes,
    resumo,
)
from app.pacientes.models import Paciente
from app.shared.tipos import Escopo, Regiao, StatusLancamento


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    dentistica = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    protese = Categoria(clinica_id=clinica.id, codigo="06", nome="Protese", ordem=6)
    particular = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    uniodonto = Convenio(clinica_id=clinica.id, codigo="051", nome="UNIODONTO")
    sessao.add_all([dentistica, protese, particular, uniodonto])
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=dentistica.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    coroa = Procedimento(
        clinica_id=clinica.id, codigo="60", nome="Coroa",
        categoria_id=protese.id, escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    amanda = Paciente(
        clinica_id=clinica.id, codigo_legado="0001/PT", nome="AMANDA",
        convenio_id=particular.id,
    )
    joao = Paciente(
        clinica_id=clinica.id, codigo_legado="0002/PT", nome="JOAO",
        convenio_id=uniodonto.id,
    )
    sessao.add_all([restauracao, coroa, amanda, joao])
    sessao.flush()
    return {
        "clinica": clinica, "usuario": usuario, "restauracao": restauracao,
        "coroa": coroa, "amanda": amanda, "joao": joao,
    }


def produzir(sessao, c, procedimento, paciente, quando, valor, dente=16):
    return lancar(
        sessao, clinica_id=c["clinica"].id, usuario_id=c["usuario"].id,
        paciente_id=paciente.id, procedimento_id=procedimento.id,
        escopo=Escopo.REGIOES, dente=dente, regioes=[Regiao.MESIAL],
        status=StatusLancamento.REALIZADO, data=quando, valor=Decimal(valor),
    )


def cobrar(sessao, c, paciente, vencimento, cobrado, pago=None, pago_em=None):
    parcela = Parcela(
        clinica_id=c["clinica"].id,
        paciente_id=paciente.id,
        numero="01/01",
        vencimento=vencimento,
        valor_cobrado=Decimal(cobrado),
        valor_pago=Decimal(pago or "0"),
        pago_em=pago_em,
    )
    sessao.add(parcela)
    sessao.flush()
    return parcela


MAIO = (date(2026, 5, 1), date(2026, 5, 31))


# --- os quatro numeros do periodo ----------------------------------------------


def test_periodo_sem_movimento_devolve_zero_e_nao_erro(sessao, cenario):
    r = resumo(sessao, clinica_id=cenario["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.recebido == Decimal("0.00")
    assert r.produzido == Decimal("0.00")
    assert r.a_receber == Decimal("0.00")
    assert r.tratamentos == 0


def test_recebido_soma_o_que_foi_pago_no_periodo(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 4, 1), "300.00", "300.00", date(2026, 5, 10))
    cobrar(sessao, c, c["joao"], date(2026, 4, 1), "200.00", "200.00", date(2026, 6, 2))
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.recebido == Decimal("300.00")


def test_pagamento_parcial_conta_pelo_que_entrou(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 4, 1), "300.00", "50.00", date(2026, 5, 10))
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.recebido == Decimal("50.00")


def test_produzido_soma_o_tratamento_feito_no_periodo(sessao, cenario):
    c = cenario
    produzir(sessao, c, c["restauracao"], c["amanda"], date(2026, 5, 12), "180.00")
    produzir(sessao, c, c["coroa"], c["joao"], date(2026, 5, 20), "800.00", dente=26)
    produzir(sessao, c, c["restauracao"], c["amanda"], date(2026, 7, 1), "999.00", dente=36)
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.produzido == Decimal("980.00")
    assert r.tratamentos == 2


def test_tratamento_apenas_planejado_nao_conta_como_produzido(sessao, cenario):
    """Produzido e o que foi feito. Planejado e promessa."""
    c = cenario
    lancar(
        sessao, clinica_id=c["clinica"].id, usuario_id=c["usuario"].id,
        paciente_id=c["amanda"].id, procedimento_id=c["restauracao"].id,
        escopo=Escopo.DENTE, dente=16, status=StatusLancamento.PLANEJADO,
        data=date(2026, 5, 12), valor=Decimal("500.00"),
    )
    sessao.flush()
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.produzido == Decimal("0.00")
    assert r.tratamentos == 0


def test_a_receber_conta_o_saldo_do_que_venceu_no_periodo(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 5, 5), "300.00", "50.00", date(2026, 5, 6))
    cobrar(sessao, c, c["joao"], date(2026, 5, 20), "200.00")
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.a_receber == Decimal("450.00")


def test_a_receber_nao_arrasta_a_divida_dos_meses_anteriores(sessao, cenario):
    """O numero e do mes, como os outros tres cartoes da tela.

    Somar tudo desde 1996 punha R$ 2 milhoes de carne do Dentalis num cartao
    ao lado de tres numeros mensais. Aquele saldo nao muda e nao vai ser
    recebido; ficava so afogando o que aconteceu no mes.
    """
    c = cenario
    cobrar(sessao, c, c["amanda"], date(1998, 7, 1), "1200.00")
    cobrar(sessao, c, c["joao"], date(2026, 4, 30), "200.00")
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.a_receber == Decimal("0.00")


def test_a_receber_ignora_o_que_ainda_nao_venceu(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["joao"], date(2026, 6, 1), "700.00")
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.a_receber == Decimal("0.00")


def test_a_receber_ignora_parcela_substituida(sessao, cenario):
    """Os degraus do carne do Dentalis: a mesma divida regravada a cada pagamento."""
    c = cenario
    degrau = cobrar(sessao, c, c["amanda"], date(2026, 5, 10), "1200.00")
    degrau.substituida = True
    sessao.flush()
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.a_receber == Decimal("0.00")


def test_a_receber_zera_quando_a_parcela_do_mes_foi_quitada(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 5, 5), "300.00", "300.00", date(2026, 5, 9))
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.a_receber == Decimal("0.00")


def test_parcela_excluida_nao_conta_em_lugar_nenhum(sessao, cenario):
    from datetime import UTC, datetime

    c = cenario
    parcela = cobrar(
        sessao, c, c["amanda"], date(2026, 4, 1), "300.00", "300.00", date(2026, 5, 10)
    )
    parcela.excluido_em = datetime.now(UTC)
    sessao.flush()
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.recebido == Decimal("0.00")
    assert r.a_receber == Decimal("0.00")


def test_dinheiro_de_outra_clinica_nunca_entra(sessao, cenario):
    c = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra")
    sessao.add(alheio)
    sessao.flush()
    sessao.add(
        Parcela(
            clinica_id=outra.id, paciente_id=alheio.id, numero="01/01",
            vencimento=date(2026, 4, 1), valor_cobrado=Decimal("999.00"),
            valor_pago=Decimal("999.00"), pago_em=date(2026, 5, 10),
        )
    )
    sessao.flush()
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.recebido == Decimal("0.00")


# --- graficos ------------------------------------------------------------------


def test_recebido_por_mes_devolve_doze_posicoes_mesmo_vazias(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 1, 1), "300.00", "300.00", date(2026, 5, 10))
    meses = recebido_por_mes(sessao, clinica_id=c["clinica"].id, ano=2026)
    assert len(meses) == 12
    assert meses[4] == Decimal("300.00")  # maio e o indice 4
    assert meses[0] == Decimal("0.00")


def test_recebido_por_mes_ignora_outro_ano(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2025, 1, 1), "300.00", "300.00", date(2025, 5, 10))
    meses = recebido_por_mes(sessao, clinica_id=c["clinica"].id, ano=2026)
    assert sum(meses) == Decimal("0.00")


def test_producao_por_dia_devolve_um_numero_por_dia_do_mes(sessao, cenario):
    c = cenario
    produzir(sessao, c, c["restauracao"], c["amanda"], date(2026, 5, 12), "180.00")
    produzir(sessao, c, c["coroa"], c["joao"], date(2026, 5, 12), "800.00", dente=26)
    produzir(sessao, c, c["restauracao"], c["joao"], date(2026, 5, 20), "180.00", dente=36)
    dias = producao_por_dia(sessao, clinica_id=c["clinica"].id, ano=2026, mes=5)
    assert len(dias) == 31
    assert dias[11] == 2  # dia 12
    assert dias[19] == 1  # dia 20
    assert dias[0] == 0


def test_producao_por_dia_sabe_o_tamanho_do_mes(sessao, cenario):
    c = cenario
    assert len(producao_por_dia(sessao, clinica_id=c["clinica"].id, ano=2026, mes=2)) == 28
    assert len(producao_por_dia(sessao, clinica_id=c["clinica"].id, ano=2024, mes=2)) == 29


def test_producao_por_categoria_soma_por_nome_de_categoria(sessao, cenario):
    c = cenario
    produzir(sessao, c, c["restauracao"], c["amanda"], date(2026, 5, 12), "180.00")
    produzir(sessao, c, c["restauracao"], c["joao"], date(2026, 5, 13), "220.00", dente=26)
    produzir(sessao, c, c["coroa"], c["joao"], date(2026, 5, 20), "800.00", dente=36)
    fatias = producao_por_categoria(
        sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1]
    )
    assert fatias == [("Protese", Decimal("800.00")), ("Dentistica", Decimal("400.00"))]


def test_producao_por_convenio_soma_pelo_convenio_do_paciente(sessao, cenario):
    c = cenario
    produzir(sessao, c, c["restauracao"], c["amanda"], date(2026, 5, 12), "180.00")
    produzir(sessao, c, c["coroa"], c["joao"], date(2026, 5, 20), "800.00", dente=26)
    fatias = producao_por_convenio(
        sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1]
    )
    assert fatias == [("UNIODONTO", Decimal("800.00")), ("PARTICULAR", Decimal("180.00"))]


def test_paciente_sem_convenio_aparece_como_nao_informado(sessao, cenario):
    c = cenario
    sem = Paciente(clinica_id=c["clinica"].id, nome="SEM CONVENIO")
    sessao.add(sem)
    sessao.flush()
    produzir(sessao, c, c["restauracao"], sem, date(2026, 5, 12), "180.00")
    fatias = producao_por_convenio(
        sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1]
    )
    assert fatias == [("não informado", Decimal("180.00"))]


# --- lista de cobranca ----------------------------------------------------------


def test_a_cobranca_lista_o_que_venceu_e_tem_saldo(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 3, 1), "300.00", "50.00", date(2026, 4, 1))
    cobrar(sessao, c, c["joao"], date(2026, 4, 15), "200.00")
    cobrar(sessao, c, c["joao"], date(2026, 4, 20), "100.00", "100.00", date(2026, 4, 25))
    linhas = a_receber(
        sessao, clinica_id=c["clinica"].id, ate=date(2026, 5, 31), desde=date(2020, 1, 1)
    )
    assert [(x.paciente, x.saldo) for x in linhas] == [
        ("AMANDA", Decimal("250.00")),
        ("JOAO", Decimal("200.00")),
    ]


def test_a_cobranca_vem_da_mais_velha_para_a_mais_nova(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["joao"], date(2026, 4, 15), "200.00")
    cobrar(sessao, c, c["amanda"], date(2026, 1, 5), "300.00")
    linhas = a_receber(
        sessao, clinica_id=c["clinica"].id, ate=date(2026, 5, 31), desde=date(2020, 1, 1)
    )
    assert [x.vencimento for x in linhas] == [date(2026, 1, 5), date(2026, 4, 15)]


def test_a_cobranca_respeita_o_corte_de_quando_comecar(sessao, cenario):
    """R$ 3,4 milhoes em aberto desde 1996 nao e cobranca, e historia."""
    c = cenario
    cobrar(sessao, c, c["amanda"], date(1998, 4, 1), "300.00")
    cobrar(sessao, c, c["joao"], date(2026, 4, 15), "200.00")
    linhas = a_receber(
        sessao, clinica_id=c["clinica"].id, ate=date(2026, 5, 31), desde=date(2024, 5, 31)
    )
    assert [x.paciente for x in linhas] == ["JOAO"]


def test_a_cobranca_diz_ha_quantos_dias_esta_vencida(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 5, 1), "300.00")
    linhas = a_receber(
        sessao, clinica_id=c["clinica"].id, ate=date(2026, 5, 31), desde=date(2020, 1, 1)
    )
    assert linhas[0].dias_vencida == 30


def test_a_cobranca_ignora_parcela_excluida(sessao, cenario):
    from datetime import UTC, datetime

    c = cenario
    parcela = cobrar(sessao, c, c["amanda"], date(2026, 4, 1), "300.00")
    parcela.excluido_em = datetime.now(UTC)
    sessao.flush()
    linhas = a_receber(
        sessao, clinica_id=c["clinica"].id, ate=date(2026, 5, 31), desde=date(2020, 1, 1)
    )
    assert linhas == []


def test_a_cobranca_traz_o_paciente_sem_uma_consulta_por_linha(sessao, cenario):
    """Sao milhares de parcelas vencidas no banco real: uma consulta por linha
    para descobrir o nome seria a tela travando sozinha."""
    from sqlalchemy import event

    c = cenario
    for dia in range(1, 11):
        cobrar(sessao, c, c["amanda"], date(2026, 4, dia), "100.00")

    consultas = []
    conexao = sessao.get_bind()

    def contar(conn, cursor, instrucao, *resto):
        if instrucao.lstrip().upper().startswith("SELECT"):
            consultas.append(instrucao)

    event.listen(conexao, "before_cursor_execute", contar)
    try:
        linhas = a_receber(
            sessao, clinica_id=c["clinica"].id, ate=date(2026, 5, 31),
            desde=date(2020, 1, 1),
        )
    finally:
        event.remove(conexao, "before_cursor_execute", contar)

    assert len(linhas) == 10
    assert len(consultas) <= 2, f"foram {len(consultas)} consultas"


def test_o_dinheiro_e_decimal_e_nunca_float(sessao, cenario):
    """Float em dinheiro erra centavo, e centavo errado em prontuario e erro."""
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 4, 1), "0.10", "0.10", date(2026, 5, 1))
    cobrar(sessao, c, c["joao"], date(2026, 4, 1), "0.20", "0.20", date(2026, 5, 1))
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert isinstance(r.recebido, Decimal)
    assert r.recebido == Decimal("0.30")


def test_o_resumo_nao_enxerga_parcela_de_outro_periodo_pelo_vencimento(sessao, cenario):
    """Recebido segue a data do pagamento, nao a do vencimento."""
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2020, 1, 1), "300.00", "300.00", date(2026, 5, 10))
    r = resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    assert r.recebido == Decimal("300.00")


def test_nada_do_financeiro_grava_ao_consultar(sessao, cenario):
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2026, 4, 1), "300.00")
    antes = sessao.scalars(select(Parcela)).all()
    resumo(sessao, clinica_id=c["clinica"].id, de=MAIO[0], ate=MAIO[1])
    recebido_por_mes(sessao, clinica_id=c["clinica"].id, ano=2026)
    producao_por_dia(sessao, clinica_id=c["clinica"].id, ano=2026, mes=5)
    depois = sessao.scalars(select(Parcela)).all()
    assert len(antes) == len(depois) == 1


# --- seletor de periodo --------------------------------------------------------


def test_os_anos_com_movimento_vem_do_mais_novo_para_o_mais_velho(sessao, cenario):
    c = cenario
    for ano in (2019, 2026, 2023):
        cobrar(
            sessao, c, c["amanda"], date(ano, 1, 1), "100.00", "100.00", date(ano, 3, 1)
        )
    assert anos_com_movimento(sessao, clinica_id=c["clinica"].id) == [2026, 2023, 2019]


def test_ano_anterior_a_1995_fica_de_fora_do_seletor(sessao, cenario):
    """Antes de julho de 1994 o dinheiro era Cruzeiro Real: somar aquilo com Real
    da um numero que nao significa nada."""
    c = cenario
    cobrar(sessao, c, c["amanda"], date(1992, 1, 1), "100.00", "100.00", date(1992, 3, 1))
    cobrar(sessao, c, c["amanda"], date(2020, 1, 1), "100.00", "100.00", date(2020, 3, 1))
    assert anos_com_movimento(sessao, clinica_id=c["clinica"].id) == [2020]


def test_sem_movimento_nenhum_o_seletor_vem_vazio(sessao, cenario):
    assert anos_com_movimento(sessao, clinica_id=cenario["clinica"].id) == []


def test_ano_no_futuro_fica_de_fora_do_seletor(sessao, cenario):
    """O historico tem uma parcela com pagamento no ano 2203 — erro de digitacao
    de 1996. A linha fica no banco; o que ela nao pode e virar opcao de menu."""
    c = cenario
    cobrar(sessao, c, c["amanda"], date(2203, 1, 1), "100.00", "100.00", date(2203, 3, 1))
    cobrar(sessao, c, c["amanda"], date(2020, 1, 1), "100.00", "100.00", date(2020, 3, 1))
    assert anos_com_movimento(sessao, clinica_id=c["clinica"].id) == [2020]
