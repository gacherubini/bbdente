"""A grade: a semana e o mes montados para a tela.

O que estes testes protegem e o orcamento de consultas. A montagem esta na
service, e nao na rota, justamente para que semana e mes nao virem a mesma
montagem escrita duas vezes — e um `for` que busca o nome de cada paciente
passa despercebido no desenvolvimento e trava a tela em producao.
"""

from datetime import date, time

import pytest

from app.agenda import service
from app.agenda.models import SituacaoAgendamento
from app.auth.models import Clinica, Usuario
from app.pacientes.models import Paciente, PacienteTelefone

SEGUNDA = date(2026, 8, 24)
QUARTA = date(2026, 8, 26)


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
    sessao.add(
        PacienteTelefone(
            paciente_id=paciente.id, numero="(51) 99999-8888", principal=True
        )
    )
    sessao.flush()
    return clinica, usuario, paciente


def test_a_semana_comeca_na_segunda_e_termina_no_domingo():
    """Semana de consultorio comeca na segunda. Domingo entra na grade mesmo
    fechado: e mais barato mostrar uma coluna vazia do que explicar por que o
    horario que ela marcou num domingo sumiu."""
    periodo = service.semana_de(date(2026, 8, 26))

    assert periodo.de == SEGUNDA
    assert periodo.ate == date(2026, 8, 30)
    assert len(periodo.dias) == 7


def test_a_semana_de_uma_segunda_e_a_dela_mesma():
    assert service.semana_de(SEGUNDA).de == SEGUNDA


def test_o_mes_cobre_semanas_inteiras():
    """A grade do mes e retangular: comeca na segunda da semana do dia 1 e
    termina no domingo da semana do ultimo dia. Senao a primeira linha teria
    buracos e o mes de fevereiro mudaria de formato.

    Agosto de 2026 comeca num sabado e termina numa segunda — a grade vai de
    27/07 a 06/09, e as duas pontas trazem dias de outro mes de proposito.
    """
    periodo = service.mes_de(date(2026, 8, 15))

    assert periodo.de == date(2026, 7, 27)
    assert periodo.ate == date(2026, 9, 6)
    assert len(periodo.dias) % 7 == 0
    assert date(2026, 8, 31) in periodo.dias


def test_a_grade_traz_o_nome_da_paciente_cadastrada(sessao, cenario):
    clinica, usuario, paciente = cenario
    service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        dia=QUARTA,
        inicio=time(9, 0),
    )

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))
    cartao = grade.do_dia(QUARTA)[0]

    assert cartao.nome == "MARIA SILVA"
    assert cartao.telefone == "(51) 99999-8888"
    assert cartao.paciente_id == paciente.id


def test_a_grade_traz_o_horario_avulso_com_o_que_foi_digitado(sessao, cenario):
    clinica, usuario, _ = cenario
    service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Maria, indicacao da Ana",
        telefone_avulso="51999997777",
        dia=QUARTA,
        inicio=time(10, 0),
    )

    cartao = service.grade(
        sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA)
    ).do_dia(QUARTA)[0]

    assert cartao.nome == "Maria, indicacao da Ana"
    assert cartao.telefone == "(51) 99999-7777"
    assert cartao.paciente_id is None


def test_os_cartoes_do_dia_vem_em_ordem_de_hora(sessao, cenario):
    clinica, usuario, _ = cenario
    for hora in (time(15, 0), time(8, 30), time(11, 0)):
        service.marcar(
            sessao,
            clinica_id=clinica.id,
            usuario_id=usuario.id,
            nome_avulso=f"as {hora}",
            dia=QUARTA,
            inicio=hora,
        )

    horas = [c.inicio for c in service.grade(
        sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA)
    ).do_dia(QUARTA)]

    assert horas == [time(8, 30), time(11, 0), time(15, 0)]


def test_o_desmarcado_continua_na_grade(sessao, cenario):
    """Some da contagem, nao da historia: a celula continua dizendo que alguem
    tinha aquele horario, para ela nao remarcar em cima."""
    clinica, usuario, _ = cenario
    agendamento = service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Joana",
        dia=QUARTA,
        inicio=time(9, 0),
    )
    service.mudar_situacao(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        agendamento_id=agendamento.id,
        situacao=SituacaoAgendamento.DESMARCADO,
    )

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert len(grade.do_dia(QUARTA)) == 1
    assert grade.do_dia(QUARTA)[0].desmarcado is True
    assert grade.quantos_no_dia(QUARTA) == 0


def test_o_excluido_some_da_grade(sessao, cenario):
    clinica, usuario, _ = cenario
    agendamento = service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Engano",
        dia=QUARTA,
        inicio=time(9, 0),
    )
    service.excluir(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        agendamento_id=agendamento.id,
    )

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert grade.do_dia(QUARTA) == []


def test_horario_de_outra_clinica_nunca_entra(sessao, cenario):
    clinica, usuario, _ = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    outro_usuario = Usuario(
        clinica_id=outra.id, nome="Outro", email="o@local", senha_hash="x"
    )
    sessao.add(outro_usuario)
    sessao.flush()
    service.marcar(
        sessao,
        clinica_id=outra.id,
        usuario_id=outro_usuario.id,
        nome_avulso="Alheia",
        dia=QUARTA,
        inicio=time(9, 0),
    )

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert grade.do_dia(QUARTA) == []


def test_a_faixa_de_horas_vem_do_dado_com_piso_e_teto(sessao, cenario):
    """Sem horario de funcionamento configuravel no primeiro corte: a primeira
    linha e a ultima saem do que esta marcado, entre 08h e 19h."""
    clinica, usuario, _ = cenario
    service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Cedo",
        dia=QUARTA,
        inicio=time(7, 0),
    )

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert grade.primeira_hora == 7
    assert grade.ultima_hora == 19


def test_sem_nada_marcado_a_faixa_e_a_padrao(sessao, cenario):
    clinica, _, _ = cenario
    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert (grade.primeira_hora, grade.ultima_hora) == (8, 19)


def test_a_semana_inteira_gasta_tres_consultas(sessao, cenario):
    """Orcamento de consultas. Um `for` que busca o nome de cada paciente passa
    despercebido no desenvolvimento e trava a tela com a agenda cheia."""
    clinica, usuario, paciente = cenario
    for dia_offset, hora in enumerate([time(9, 0), time(10, 0), time(11, 0)]):
        service.marcar(
            sessao,
            clinica_id=clinica.id,
            usuario_id=usuario.id,
            paciente_id=paciente.id,
            dia=date(2026, 8, 24 + dia_offset),
            inicio=hora,
        )
    sessao.flush()

    from sqlalchemy import event

    consultas = []
    motor = sessao.get_bind()

    def contar(conexao, cursor, instrucao, parametros, contexto, muitos):
        if instrucao.lstrip().upper().startswith("SELECT"):
            consultas.append(instrucao)

    event.listen(motor, "before_cursor_execute", contar)
    try:
        service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))
    finally:
        event.remove(motor, "before_cursor_execute", contar)

    assert len(consultas) <= 3, "\n\n".join(consultas)


def _lancar_realizado(sessao, clinica, usuario, paciente, dia):
    """Um lancamento realizado, que e o que faz alguem aparecer como atendido."""
    from decimal import Decimal

    from app.catalogo.models import Categoria, Procedimento
    from app.clinico import service as clinico
    from app.shared.tipos import Escopo, StatusLancamento

    categoria = Categoria(clinica_id=clinica.id, codigo="01", nome="Clinica", ordem=1)
    sessao.add(categoria)
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=clinica.id,
        codigo="01",
        nome="Consulta",
        categoria_id=categoria.id,
        escopo_sugerido=Escopo.BOCA,
    )
    sessao.add(procedimento)
    sessao.flush()
    return clinico.lancar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        procedimento_id=procedimento.id,
        escopo=Escopo.BOCA,
        status=StatusLancamento.REALIZADO,
        data=dia,
        valor=Decimal("100.00"),
    )


def test_quem_foi_atendido_sem_horario_aparece_no_rodape_do_dia(sessao, cenario):
    """Vem do prontuario, e por isso nao tem hora: `lancamento` guarda data,
    nunca hora. E o caso real de quem chegou sem marcar."""
    clinica, usuario, paciente = cenario
    _lancar_realizado(sessao, clinica, usuario, paciente, QUARTA)

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert [c.nome for c in grade.sem_hora_no_dia(QUARTA)] == ["MARIA SILVA"]
    assert grade.do_dia(QUARTA) == []


def test_quem_tinha_horario_e_foi_atendida_nao_aparece_duas_vezes(sessao, cenario):
    clinica, usuario, paciente = cenario
    service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        dia=QUARTA,
        inicio=time(9, 0),
    )
    _lancar_realizado(sessao, clinica, usuario, paciente, QUARTA)

    grade = service.grade(sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA))

    assert grade.sem_hora_no_dia(QUARTA) == []
    assert grade.do_dia(QUARTA)[0].atendida is True


def test_o_fato_vence_a_anotacao_quando_ela_marcou_falta_por_engano(sessao, cenario):
    """Horario FALTOU com atendimento no dia: a tela mostra que foi atendida.
    O prontuario e o fato; a situacao da agenda e uma anotacao."""
    clinica, usuario, paciente = cenario
    agendamento = service.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        dia=QUARTA,
        inicio=time(9, 0),
    )
    service.mudar_situacao(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        agendamento_id=agendamento.id,
        situacao=SituacaoAgendamento.FALTOU,
    )
    _lancar_realizado(sessao, clinica, usuario, paciente, QUARTA)

    cartao = service.grade(
        sessao, clinica_id=clinica.id, periodo=service.semana_de(QUARTA)
    ).do_dia(QUARTA)[0]

    assert cartao.atendida is True
    assert cartao.situacao == "FALTOU"
