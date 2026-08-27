"""Autorizacao para mandar mensagem no WhatsApp.

Tres estados, e o do meio e o que importa: `NULL` = **nunca perguntamos**, e
`NULL` nao recebe. Os 5.559 cadastros migrados entram todos assim — o Dentalis
nunca perguntou isso, e presumir autorizacao de 5.559 pessoas e exatamente o que
a lei nao deixa.

A consequencia e dura e esta escrita no plano: no primeiro mes quase ninguem
recebe lembrete. A base de autorizacao cresce consulta a consulta.
"""

from datetime import date, time

import pytest

from app.agenda import service as agenda
from app.auth.models import Auditoria, Clinica, Usuario
from app.pacientes import service
from app.pacientes.models import Paciente

DIA = date(2026, 9, 1)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = Usuario(
        clinica_id=clinica.id, nome="K", email="k@local", senha_hash="x"
    )
    sessao.add(usuario)
    sessao.flush()
    return clinica, usuario


def test_paciente_novo_nasce_sem_resposta(sessao, cenario):
    clinica, usuario = cenario
    paciente = service.criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="MARIA"
    )

    assert paciente.aceita_whatsapp is None


def test_paciente_migrado_fica_sem_resposta(sessao, cenario):
    """Nenhum backfill, nenhum default `true`. Sem isso, o primeiro disparo
    mandaria mensagem para 5.559 pessoas que nunca autorizaram nada."""
    clinica, _ = cenario
    migrado = Paciente(clinica_id=clinica.id, nome="ANTIGA", codigo_legado="0001/PT")
    sessao.add(migrado)
    sessao.flush()

    assert migrado.aceita_whatsapp is None


@pytest.mark.parametrize("resposta", [True, False])
def test_registrar_a_resposta_grava_e_audita(sessao, cenario, resposta):
    """Consentimento e justamente o que se precisa provar depois."""
    clinica, usuario = cenario
    paciente = service.criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="MARIA"
    )

    service.definir_consentimento(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        aceita=resposta,
    )

    assert paciente.aceita_whatsapp is resposta
    linha = sessao.query(Auditoria).filter_by(acao="CONSENTIMENTO").one()
    assert linha.dados_antes["aceita_whatsapp"] is None
    assert linha.dados_depois["aceita_whatsapp"] is resposta


def test_paciente_de_outra_clinica_nao_e_alcancado(sessao, cenario):
    clinica, usuario = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    estranha = Paciente(clinica_id=outra.id, nome="ALHEIA")
    sessao.add(estranha)
    sessao.flush()

    with pytest.raises(LookupError):
        service.definir_consentimento(
            sessao,
            clinica_id=clinica.id,
            usuario_id=usuario.id,
            paciente_id=estranha.id,
            aceita=True,
        )


def test_contatos_de_conta_se_pode_mandar(sessao, cenario):
    """A agenda precisa disso para o selo do cartao — e sem JOIN em tabela de
    outro modulo."""
    clinica, usuario = cenario
    paciente = service.criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="MARIA",
        telefone="51999998888",
    )
    service.definir_consentimento(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        aceita=True,
    )

    contato = service.contatos_de(
        sessao, clinica_id=clinica.id, paciente_ids=[paciente.id]
    )[paciente.id]

    assert contato.nome == "MARIA"
    assert contato.telefone == "(51) 99999-8888"
    assert contato.aceita_whatsapp is True


def test_horario_avulso_nasce_avisando(sessao, cenario):
    """O telefone avulso e ditado agora, ao telefone, para marcar aquela consulta
    — mandar o lembrete daquela consulta e a finalidade para a qual ele acabou de
    ser dado. Diferente dos 5.559 migrados, coletados desde 1996 sem registro de
    autorizacao nenhum."""
    clinica, usuario = cenario
    agendamento = agenda.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Maria, indicacao da Ana",
        telefone_avulso="51999998888",
        dia=DIA,
        inicio=time(9, 0),
    )

    assert agendamento.avisar_avulso is True


def test_da_para_marcar_sem_avisar(sessao, cenario):
    """"Nao me manda mensagem" tem de caber no mesmo formulario."""
    clinica, usuario = cenario
    agendamento = agenda.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Joana",
        telefone_avulso="51999998888",
        avisar_avulso=False,
        dia=DIA,
        inicio=time(9, 0),
    )

    assert agendamento.avisar_avulso is False
