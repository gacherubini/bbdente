"""Marcar, remarcar, desmarcar e excluir um horario.

O que estes testes fixam nao e o CRUD — e as tres regras que fazem a agenda
ser usavel no telefone: horario avulso e caminho normal, conflito avisa mas
nunca bloqueia, e desmarcar nao apaga.
"""

from datetime import date, time

import pytest

from app.agenda import service
from app.agenda.models import SituacaoAgendamento
from app.auth.models import Auditoria, Clinica, Usuario
from app.pacientes.models import Paciente

DIA = date(2026, 9, 1)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    usuario = Usuario(
        clinica_id=clinica.id, nome="Dra. Katia", email="k@local", senha_hash="x"
    )
    paciente = Paciente(clinica_id=clinica.id, nome="MARIA SILVA")
    sessao.add_all([usuario, paciente])
    sessao.flush()
    return clinica, usuario, paciente


def _marcar(sessao, cenario, **kwargs):
    clinica, usuario, _ = cenario
    dados = {
        "dia": DIA,
        "inicio": time(9, 0),
        "duracao_min": 30,
        "nome_avulso": "Maria, indicacao da Ana",
    }
    dados.update(kwargs)
    return service.marcar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, **dados
    )


def test_marca_horario_de_paciente_cadastrada(sessao, cenario):
    _, _, paciente = cenario
    agendamento = _marcar(sessao, cenario, paciente_id=paciente.id, nome_avulso=None)

    assert agendamento.paciente_id == paciente.id
    assert agendamento.situacao is SituacaoAgendamento.MARCADO


def test_marca_horario_avulso_sem_cadastro_nenhum(sessao, cenario):
    """O caminho de quem liga e nao e da base. Nao e excecao, e caminho normal."""
    agendamento = _marcar(sessao, cenario, telefone_avulso="(51) 99999-8888")

    assert agendamento.paciente_id is None
    assert agendamento.nome_avulso == "Maria, indicacao da Ana"


def test_avulso_sem_telefone_marca_do_mesmo_jeito(sessao, cenario):
    """Nao ter WhatsApp nunca impede de marcar. Nao e erro nem bloqueio."""
    agendamento = _marcar(sessao, cenario, telefone_avulso=None)

    assert agendamento.id is not None
    assert agendamento.telefone_avulso is None


def test_o_telefone_avulso_passa_pela_regua_do_cadastro(sessao, cenario):
    """Uma regua so no sistema inteiro: `pacientes/telefone.py`."""
    agendamento = _marcar(sessao, cenario, telefone_avulso="51999998888")

    assert agendamento.telefone_avulso == "(51) 99999-8888"


def test_telefone_estranho_entra_como_veio_em_vez_de_ser_recusado(sessao, cenario):
    """Mesma regra do CPF suspeito: dado estranho e marcado, nunca recusado —
    ela esta com a paciente na linha e nao pode ser barrada por um numero."""
    agendamento = _marcar(sessao, cenario, telefone_avulso="3653")

    assert agendamento.telefone_avulso == "3653"


def test_sem_paciente_e_sem_nome_e_recusado_antes_do_banco(sessao, cenario):
    with pytest.raises(service.SemDono):
        _marcar(sessao, cenario, nome_avulso="   ")


def test_paciente_de_outra_clinica_nao_pode_ser_agendada(sessao, cenario):
    clinica, usuario, _ = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    estranha = Paciente(clinica_id=outra.id, nome="ALHEIA")
    sessao.add(estranha)
    sessao.flush()

    with pytest.raises(service.PacienteDeOutraClinica):
        service.marcar(
            sessao,
            clinica_id=clinica.id,
            usuario_id=usuario.id,
            paciente_id=estranha.id,
            dia=DIA,
            inicio=time(9, 0),
        )


def test_marcar_grava_auditoria(sessao, cenario):
    clinica, _, _ = cenario
    agendamento = _marcar(sessao, cenario)

    linha = sessao.query(Auditoria).filter_by(entidade="agendamento").one()
    assert linha.acao == "MARCAR"
    assert linha.entidade_id == agendamento.id
    assert linha.clinica_id == clinica.id


def test_conflito_avisa_e_nao_bloqueia(sessao, cenario):
    """Duas pessoas no mesmo horario acontece de verdade: encaixe, urgencia,
    acompanhante. Bloquear faria ela voltar para o papel."""
    _marcar(sessao, cenario, inicio=time(9, 0), duracao_min=60)
    segundo = _marcar(sessao, cenario, inicio=time(9, 30), nome_avulso="Joana")

    assert segundo.id is not None
    conflitos = service.conflitos_de(sessao, agendamento=segundo)
    assert len(conflitos) == 1


def test_horario_encostado_nao_e_conflito(sessao, cenario):
    """09:00 + 30min termina as 09:30. Quem comeca as 09:30 nao conflita —
    senao a agenda avisaria em toda consulta seguida, e o aviso viraria ruido."""
    _marcar(sessao, cenario, inicio=time(9, 0), duracao_min=30)
    segundo = _marcar(sessao, cenario, inicio=time(9, 30), nome_avulso="Joana")

    assert service.conflitos_de(sessao, agendamento=segundo) == []


def test_desmarcado_nao_conflita_com_ninguem(sessao, cenario):
    primeiro = _marcar(sessao, cenario, inicio=time(9, 0), duracao_min=60)
    service.mudar_situacao(
        sessao,
        clinica_id=primeiro.clinica_id,
        usuario_id=None,
        agendamento_id=primeiro.id,
        situacao=SituacaoAgendamento.DESMARCADO,
    )
    segundo = _marcar(sessao, cenario, inicio=time(9, 30), nome_avulso="Joana")

    assert service.conflitos_de(sessao, agendamento=segundo) == []


def test_remarcar_muda_dia_e_hora_e_deixa_os_dois_na_auditoria(sessao, cenario):
    """E por isso que nao existe tabela de historico de remarcacao: o antes e o
    depois ja estao na auditoria."""
    clinica, usuario, _ = cenario
    agendamento = _marcar(sessao, cenario)

    service.remarcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        agendamento_id=agendamento.id,
        dia=date(2026, 9, 3),
        inicio=time(15, 0),
        duracao_min=60,
        observacao="pediu para adiar",
    )

    assert agendamento.dia == date(2026, 9, 3)
    assert agendamento.inicio == time(15, 0)
    linha = sessao.query(Auditoria).filter_by(acao="REMARCAR").one()
    assert linha.dados_antes["inicio"] == "09:00:00"
    assert linha.dados_depois["inicio"] == "15:00:00"


def test_desmarcar_nao_e_exclusao(sessao, cenario):
    clinica, usuario, _ = cenario
    agendamento = _marcar(sessao, cenario)

    service.mudar_situacao(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        agendamento_id=agendamento.id,
        situacao=SituacaoAgendamento.DESMARCADO,
    )

    assert agendamento.situacao is SituacaoAgendamento.DESMARCADO
    assert agendamento.excluido_em is None


def test_excluir_e_logico_e_some_da_agenda(sessao, cenario):
    clinica, usuario, _ = cenario
    agendamento = _marcar(sessao, cenario)

    service.excluir(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        agendamento_id=agendamento.id,
    )

    assert agendamento.excluido_em is not None
    assert service.obter(sessao, clinica_id=clinica.id, agendamento_id=agendamento.id) is None


def test_horario_de_outra_clinica_nao_e_alcancado(sessao, cenario):
    clinica, usuario, _ = cenario
    agendamento = _marcar(sessao, cenario)
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()

    assert service.obter(sessao, clinica_id=outra.id, agendamento_id=agendamento.id) is None
    with pytest.raises(service.NaoEncontrado):
        service.excluir(
            sessao,
            clinica_id=outra.id,
            usuario_id=usuario.id,
            agendamento_id=agendamento.id,
        )
