"""A ponte entre a agenda e o prontuario.

Horario avulso e etapa, nunca estado permanente: quando o atendimento e
concluido, o cadastro nasce e o horario passa a apontar para ele. A regra que
manda aqui e uma so — **o prontuario e mais importante que a agenda**. Nada
que der errado no vinculo pode impedir um tratamento de ser gravado.
"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.agenda import service
from app.agenda.models import Agendamento
from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo

HOJE = date(2026, 8, 26)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa-12", nome="K"
    )
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
    return {"clinica": clinica, "usuario": usuario, "procedimento": procedimento}


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def _avulso(sessao, cenario, nome="Maria, indicacao da Ana"):
    return service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome_avulso=nome,
        telefone_avulso="51999998888",
        dia=HOJE,
        inicio=time(9, 0),
    )


def _atendimento(cenario, **extra):
    corpo = {
        "novo": {"nome": "MARIA DA SILVA"},
        "confirmar": True,
        "itens": [
            {
                "procedimento_id": cenario["procedimento"].id,
                "escopo": "BOCA",
                "status": "REALIZADO",
                "data": HOJE.isoformat(),
                "valor": "100.00",
            }
        ],
    }
    corpo.update(extra)
    return corpo


def test_concluir_o_atendimento_vincula_o_horario_avulso(cliente, sessao, cenario):
    agendamento = _avulso(sessao, cenario)

    resposta = cliente.post(
        "/api/atendimento", json=_atendimento(cenario, agendamento_id=agendamento.id)
    )

    assert resposta.status_code == 201
    assert agendamento.paciente_id == resposta.json()["paciente_id"]
    assert agendamento.nome_avulso is None


def test_o_vinculo_fica_na_auditoria(cliente, sessao, cenario):
    agendamento = _avulso(sessao, cenario)
    cliente.post(
        "/api/atendimento", json=_atendimento(cenario, agendamento_id=agendamento.id)
    )

    linha = (
        sessao.query(Auditoria)
        .filter_by(entidade="agendamento", acao="VINCULAR")
        .one()
    )
    assert linha.dados_antes["nome_avulso"] == "Maria, indicacao da Ana"
    assert linha.dados_depois["paciente_id"] == agendamento.paciente_id


def test_agendamento_inexistente_nao_derruba_o_atendimento(cliente, sessao, cenario):
    """O prontuario e mais importante que a agenda. Um id velho numa aba aberta
    ha uma hora nao pode fazer o tratamento se perder."""
    resposta = cliente.post(
        "/api/atendimento", json=_atendimento(cenario, agendamento_id=999_999)
    )

    assert resposta.status_code == 201


def test_agendamento_de_outra_clinica_nao_derruba_nem_vincula(cliente, sessao, cenario):
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
        dia=HOJE,
        inicio=time(9, 0),
    )

    resposta = cliente.post(
        "/api/atendimento", json=_atendimento(cenario, agendamento_id=alheio.id)
    )

    assert resposta.status_code == 201
    assert alheio.paciente_id is None
    assert alheio.nome_avulso == "Alheia"


def test_horario_que_ja_tem_paciente_nao_e_roubado(cliente, sessao, cenario):
    """Concluir um atendimento no horario de outra pessoa nao pode reescrever de
    quem era aquele horario — seria apagar a historia sem ninguem pedir."""
    dona = Paciente(clinica_id=cenario["clinica"].id, nome="DONA DO HORARIO")
    sessao.add(dona)
    sessao.flush()
    agendamento = service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=dona.id,
        dia=HOJE,
        inicio=time(9, 0),
    )

    resposta = cliente.post(
        "/api/atendimento", json=_atendimento(cenario, agendamento_id=agendamento.id)
    )

    assert resposta.status_code == 201
    assert agendamento.paciente_id == dona.id
    assert resposta.json()["paciente_id"] != dona.id


def test_atendimento_sem_agendamento_continua_funcionando(cliente, sessao, cenario):
    resposta = cliente.post("/api/atendimento", json=_atendimento(cenario))

    assert resposta.status_code == 201
    assert sessao.query(Agendamento).count() == 0


def test_a_boca_em_branco_sabe_de_qual_horario_veio(cliente, sessao, cenario):
    """Ela clicou em "atender" no cartao: a tela tem de dizer quem esta na
    cadeira, senao ela digita o nome de novo no fim."""
    agendamento = _avulso(sessao, cenario)

    resposta = cliente.get(f"/odontograma?agendamento={agendamento.id}")

    assert resposta.status_code == 200
    assert "Maria, indicacao da Ana" in resposta.text
    assert f'data-agendamento="{agendamento.id}"' in resposta.text


def test_agendamento_invalido_na_url_abre_a_boca_em_branco_normal(cliente):
    resposta = cliente.get("/odontograma?agendamento=999999")

    assert resposta.status_code == 200
    assert 'data-agendamento=""' in resposta.text


def test_o_cartao_da_agenda_leva_para_o_atendimento(cliente, sessao, cenario):
    agendamento = _avulso(sessao, cenario)

    pagina = cliente.get(f"/agenda?dia={HOJE.isoformat()}").text

    assert f"/odontograma?agendamento={agendamento.id}" in pagina
