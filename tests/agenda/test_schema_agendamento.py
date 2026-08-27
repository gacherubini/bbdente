"""O schema da agenda.

A tabela existe para uma pergunta so: quem vem, e quando. O que ela NAO
guarda esta tao decidido quanto o que ela guarda — nao ha `fim`, nao ha
`profissional_id`, nao ha `procedimento_id`. Ver o plano da agenda, secao 3.3.
"""

from datetime import date, datetime, time

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.agenda.models import Agendamento, SituacaoAgendamento
from app.auth.models import Clinica
from app.pacientes.models import Paciente


@pytest.fixture
def clinica(sessao):
    c = Clinica(nome="Consultorio")
    sessao.add(c)
    sessao.flush()
    return c


def test_a_tabela_existe_com_as_colunas_da_spec(engine_teste):
    colunas = {c["name"] for c in inspect(engine_teste).get_columns("agendamento")}
    assert colunas == {
        "id", "clinica_id", "paciente_id", "nome_avulso", "telefone_avulso",
        "dia", "inicio", "duracao_min", "situacao", "observacao", "avisar_avulso",
        "criado_por", "criado_em", "excluido_em",
    }


def test_fim_nao_e_coluna(engine_teste):
    """`fim` e derivado de inicio + duracao_min, como `Parcela.saldo`.

    Coluna guardada seria a mesma verdade em dois lugares, e um dos dois
    envelhece errado no primeiro dia em que alguem mudar a duracao.
    """
    colunas = {c["name"] for c in inspect(engine_teste).get_columns("agendamento")}
    assert "fim" not in colunas


def test_o_enum_de_situacao_existe_no_postgres(engine_teste):
    with engine_teste.connect() as conexao:
        valores = {
            linha[0]
            for linha in conexao.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'situacao_agendamento'"
                )
            )
        }
    assert valores == {m.value for m in SituacaoAgendamento}


def test_horario_avulso_grava_sem_paciente(sessao, clinica):
    """Marcar horario nao e dado clinico. Exigir cadastro antes de anotar um
    telefonema e o que faz a agenda voltar para o papel no segundo dia."""
    sessao.add(
        Agendamento(
            clinica_id=clinica.id,
            nome_avulso="Maria, indicacao da Ana",
            telefone_avulso="51999998888",
            dia=date(2026, 9, 1),
            inicio=time(14, 0),
        )
    )
    sessao.flush()

    gravado = sessao.query(Agendamento).one()
    assert gravado.paciente_id is None
    assert gravado.situacao is SituacaoAgendamento.MARCADO
    assert gravado.duracao_min == 30


def test_horario_sem_paciente_e_sem_nome_e_recusado_pelo_banco(sessao, clinica):
    """A regra e do banco, nao de um `if` na service: linha sem dono nenhum nao
    responde "quem vem", que e a unica pergunta desta tabela."""
    sessao.add(
        Agendamento(clinica_id=clinica.id, dia=date(2026, 9, 1), inicio=time(14, 0))
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_nome_avulso_vazio_conta_como_sem_nome(sessao, clinica):
    sessao.add(
        Agendamento(
            clinica_id=clinica.id,
            nome_avulso="",
            dia=date(2026, 9, 1),
            inicio=time(14, 0),
        )
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


@pytest.mark.parametrize("duracao", [0, 4, 601])
def test_duracao_implausivel_e_recusada(sessao, clinica, duracao):
    sessao.add(
        Agendamento(
            clinica_id=clinica.id,
            nome_avulso="Maria",
            dia=date(2026, 9, 1),
            inicio=time(14, 0),
            duracao_min=duracao,
        )
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_horario_de_paciente_cadastrada_dispensa_o_nome_avulso(sessao, clinica):
    paciente = Paciente(clinica_id=clinica.id, nome="MARIA SILVA")
    sessao.add(paciente)
    sessao.flush()

    sessao.add(
        Agendamento(
            clinica_id=clinica.id,
            paciente_id=paciente.id,
            dia=date(2026, 9, 1),
            inicio=time(9, 30),
            duracao_min=60,
        )
    )
    sessao.flush()

    assert sessao.query(Agendamento).one().paciente_id == paciente.id


def test_fim_e_calculado_a_partir_da_duracao(sessao, clinica):
    agendamento = Agendamento(
        clinica_id=clinica.id,
        nome_avulso="Maria",
        dia=date(2026, 9, 1),
        inicio=time(14, 0),
        duracao_min=90,
    )
    assert agendamento.fim == time(15, 30)


def test_fim_que_passa_da_meia_noite_para_as_23_59(sessao, clinica):
    """Consultorio nao atende de madrugada, mas 23:30 + 90min nao pode virar
    01:00 e fazer o cartao aparecer no topo do dia anterior."""
    agendamento = Agendamento(
        clinica_id=clinica.id,
        nome_avulso="Maria",
        dia=date(2026, 9, 1),
        inicio=time(23, 30),
        duracao_min=90,
    )
    assert agendamento.fim == time(23, 59)


def test_desmarcado_nao_e_exclusao_logica(sessao, clinica):
    """Desmarcar e historia do consultorio; excluir e para engano. Sao colunas
    diferentes de proposito — o horario desmarcado continua visivel, riscado."""
    agendamento = Agendamento(
        clinica_id=clinica.id,
        nome_avulso="Maria",
        dia=date(2026, 9, 1),
        inicio=time(14, 0),
        situacao=SituacaoAgendamento.DESMARCADO,
    )
    sessao.add(agendamento)
    sessao.flush()

    assert agendamento.excluido_em is None


def test_criado_em_nasce_preenchido_pelo_banco(sessao, clinica):
    agendamento = Agendamento(
        clinica_id=clinica.id,
        nome_avulso="Maria",
        dia=date(2026, 9, 1),
        inicio=time(14, 0),
    )
    sessao.add(agendamento)
    sessao.flush()
    sessao.refresh(agendamento)

    assert isinstance(agendamento.criado_em, datetime)
