"""A tela da agenda: a semana, o mes, e marcar um horario.

Uma rota so com duas vistas, tudo por formulario com 303 de volta — funciona
sem JavaScript, o botao "voltar" nao reenvia, e nao ha endpoint JSON novo.
"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.agenda import service
from app.agenda.models import Agendamento, SituacaoAgendamento
from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao

QUARTA = date(2026, 8, 26)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa-12", nome="K"
    )
    paciente = Paciente(clinica_id=clinica.id, nome="MARIA SILVA")
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


def test_sem_sessao_a_agenda_manda_para_o_login(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        resposta = anonimo.get("/agenda")

    assert resposta.status_code == 303
    assert resposta.headers["location"].startswith("/login")


def test_a_semana_abre_e_mostra_os_dias(cliente):
    resposta = cliente.get(f"/agenda?dia={QUARTA.isoformat()}")

    assert resposta.status_code == 200
    assert "seg" in resposta.text and "dom" in resposta.text
    assert "24" in resposta.text


def test_a_vista_de_mes_abre_pela_mesma_rota(cliente):
    resposta = cliente.get(f"/agenda?vista=mes&dia={QUARTA.isoformat()}")

    assert resposta.status_code == 200
    assert "agosto" in resposta.text.lower()


def test_dia_invalido_na_url_nao_derruba_a_tela(cliente):
    """URL e coisa que o usuario edita. Data impossivel cai em hoje."""
    resposta = cliente.get("/agenda?dia=2026-02-31")

    assert resposta.status_code == 200


def test_vista_inventada_cai_na_semana(cliente):
    resposta = cliente.get(f"/agenda?vista=trimestre&dia={QUARTA.isoformat()}")

    assert resposta.status_code == 200


def test_marcar_horario_de_paciente_cadastrada(cliente, sessao, cenario):
    resposta = cliente.post(
        "/agenda",
        data={
            "paciente_id": str(cenario["paciente"].id),
            "nome": "MARIA SILVA",
            "dia": QUARTA.isoformat(),
            "inicio": "09:00",
            "duracao_min": "30",
        },
    )

    assert resposta.status_code == 303
    agendamento = sessao.query(Agendamento).one()
    assert agendamento.paciente_id == cenario["paciente"].id


def test_marcar_horario_de_quem_nao_e_da_base(cliente, sessao):
    """O campo de busca E o campo de nome: sem paciente_id, o que ela digitou
    vira o nome do horario. Uma pergunta, duas saidas."""
    resposta = cliente.post(
        "/agenda",
        data={
            "nome": "Maria, indicacao da Ana",
            "telefone": "51999998888",
            "dia": QUARTA.isoformat(),
            "inicio": "10:00",
            "duracao_min": "60",
        },
    )

    assert resposta.status_code == 303
    agendamento = sessao.query(Agendamento).one()
    assert agendamento.paciente_id is None
    assert agendamento.nome_avulso == "Maria, indicacao da Ana"
    assert agendamento.telefone_avulso == "(51) 99999-8888"


def test_marcar_sem_telefone_funciona(cliente, sessao):
    """Nao ter WhatsApp nao pode impedir de marcar."""
    resposta = cliente.post(
        "/agenda",
        data={"nome": "Joana", "dia": QUARTA.isoformat(), "inicio": "11:00"},
    )

    assert resposta.status_code == 303
    assert sessao.query(Agendamento).one().telefone_avulso is None


def test_marcar_sem_nome_nenhum_volta_com_erro_em_vez_de_500(cliente, sessao):
    resposta = cliente.post(
        "/agenda", data={"nome": "  ", "dia": QUARTA.isoformat(), "inicio": "09:00"}
    )

    assert resposta.status_code == 200
    assert "nome" in resposta.text.lower()
    assert sessao.query(Agendamento).count() == 0


def test_hora_invalida_volta_com_erro(cliente, sessao):
    resposta = cliente.post(
        "/agenda", data={"nome": "Joana", "dia": QUARTA.isoformat(), "inicio": "25:99"}
    )

    assert resposta.status_code == 200
    assert sessao.query(Agendamento).count() == 0


def test_o_formulario_ja_vem_com_o_dia_e_a_hora_do_clique(cliente):
    resposta = cliente.get(f"/agenda/novo?dia={QUARTA.isoformat()}&hora=14:00")

    assert resposta.status_code == 200
    assert "14:00" in resposta.text
    assert QUARTA.isoformat() in resposta.text


def test_remarcar_pela_tela(cliente, sessao, cenario):
    agendamento = service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso="Joana",
        dia=QUARTA,
        inicio=time(9, 0),
    )

    resposta = cliente.post(
        f"/agenda/{agendamento.id}",
        data={"dia": "2026-08-28", "inicio": "15:30", "duracao_min": "60"},
    )

    assert resposta.status_code == 303
    assert agendamento.dia == date(2026, 8, 28)
    assert agendamento.inicio == time(15, 30)


def test_confirmar_faltou_e_desmarcar_pela_tela(cliente, sessao, cenario):
    agendamento = service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso="Joana",
        dia=QUARTA,
        inicio=time(9, 0),
    )

    for valor, esperado in [
        ("CONFIRMADO", SituacaoAgendamento.CONFIRMADO),
        ("FALTOU", SituacaoAgendamento.FALTOU),
        ("DESMARCADO", SituacaoAgendamento.DESMARCADO),
    ]:
        resposta = cliente.post(
            f"/agenda/{agendamento.id}/situacao", data={"situacao": valor}
        )
        assert resposta.status_code == 303
        assert agendamento.situacao is esperado

    assert agendamento.excluido_em is None


def test_situacao_inventada_nao_muda_nada(cliente, sessao, cenario):
    agendamento = service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso="Joana",
        dia=QUARTA,
        inicio=time(9, 0),
    )

    resposta = cliente.post(
        f"/agenda/{agendamento.id}/situacao", data={"situacao": "SUMIU"}
    )

    assert resposta.status_code == 400
    assert agendamento.situacao is SituacaoAgendamento.MARCADO


def test_excluir_pela_tela_e_logico(cliente, sessao, cenario):
    agendamento = service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso="Engano",
        dia=QUARTA,
        inicio=time(9, 0),
    )

    resposta = cliente.post(f"/agenda/{agendamento.id}/excluir")

    assert resposta.status_code == 303
    assert agendamento.excluido_em is not None


def test_horario_de_outra_clinica_da_404(cliente, sessao):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    outro_usuario = criar_usuario(
        sessao, clinica_id=outra.id, email="o@e.com", senha="senha-longa-12", nome="O"
    )
    alheio = service.marcar(
        sessao,
        clinica_id=outra.id,
        usuario_id=outro_usuario.id,
        nome_avulso="Alheia",
        dia=QUARTA,
        inicio=time(9, 0),
    )

    assert cliente.post(f"/agenda/{alheio.id}/excluir").status_code == 404
    assert cliente.get(f"/agenda/{alheio.id}").status_code == 404


def test_a_tela_avisa_do_conflito_sem_ter_bloqueado(cliente, sessao, cenario):
    service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso="Amanda",
        dia=QUARTA,
        inicio=time(9, 0),
        duracao_min=60,
    )

    resposta = cliente.post(
        "/agenda",
        data={"nome": "Joana", "dia": QUARTA.isoformat(), "inicio": "09:30"},
    )

    assert resposta.status_code == 303
    assert sessao.query(Agendamento).count() == 2
    assert "conflito" in resposta.headers["location"]


def test_cada_hora_oferece_os_dois_comecos(cliente):
    """A linha e de uma hora, mas com duas seções por dentro: às 19 dá para
    clicar na de cima (19:00) ou na de baixo (19:30)."""
    pagina = cliente.get(f"/agenda?dia={QUARTA.isoformat()}").text

    assert f"/agenda/novo?dia={QUARTA.isoformat()}&hora=19:00" in pagina
    assert f"/agenda/novo?dia={QUARTA.isoformat()}&hora=19:30" in pagina


def test_o_cartao_da_meia_hora_fica_na_secao_de_baixo(cliente, sessao, cenario):
    service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso="Meia hora",
        dia=QUARTA,
        inicio=time(9, 30),
    )

    pagina = cliente.get(f"/agenda?dia={QUARTA.isoformat()}").text
    secao_da_meia = pagina.split('agenda-secao agenda-secao-meia')[1:]

    assert any("Meia hora" in trecho.split("</div>")[0] for trecho in secao_da_meia)
