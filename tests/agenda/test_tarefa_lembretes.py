"""O endpoint que o relógio chama.

Quem dispara não tem sessão nem cookie: é máquina. Por isso ele é autenticado
por um segredo em cabeçalho, e por isso **token errado responde 404** — um 401
confirmaria que o endereço existe, e este endpoint não se anuncia.

E a resposta não leva nome de paciente nenhum: ela vai para o log de um serviço
de cron de terceiro.
"""


import pytest
from fastapi.testclient import TestClient

from app.agenda import service
from app.agenda.models import Lembrete
from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.config import config
from app.main import criar_app
from app.pacientes import service as pacientes
from app.shared.db import obter_sessao

TOKEN = "segredo-de-teste-bem-longo"


@pytest.fixture
def cenario(sessao, monkeypatch):
    monkeypatch.setattr(config, "tarefas_token", TOKEN)
    # Não há mais id para apontar: quem responde "para quais clínicas?" é o
    # banco. O palpite `clinica_id_padrao = 1` saiu do código em 28/08/2026,
    # depois de derrubar todas as batidas de produção — ver `test_relogio.py`.
    clinica = Clinica(nome="Consultório Dra. Kátia")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa-12", nome="K"
    )
    configuracao = service.configuracao_de(sessao, clinica_id=clinica.id)
    configuracao.lembrete_ativo = True
    configuracao.endereco = "Rua X, 100"
    configuracao.telefone_clinica = "(51) 3333-3333"
    sessao.flush()
    return {"clinica": clinica, "usuario": usuario}


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        yield c


def _horario_daqui_a_vinte_horas(sessao, cenario):
    """Dentro da janela de 24h e fora do corte de 6h — as duas pontas importam.

    "Amanha as 14h" nao serve: rodando de madrugada, uma consulta das 14h de
    amanha ainda esta a mais de 24h e nao entra na fila. O teste tem de marcar
    onde o lembrete de fato sai, e nao onde o calendario parece dizer que sai.
    """
    from datetime import datetime, timedelta

    alvo = datetime.now() + timedelta(hours=20)
    paciente = pacientes.criar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome="MARIA SILVA",
        telefone="51999998888",
    )
    pacientes.definir_consentimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=paciente.id,
        aceita=True,
    )
    return service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=paciente.id,
        dia=alvo.date(),
        inicio=alvo.time().replace(second=0, microsecond=0),
    )


def test_sem_token_da_404(cliente):
    assert cliente.post("/tarefas/lembretes").status_code == 404


def test_token_errado_da_404_e_nao_401(cliente):
    """401 confirmaria que o endereço existe."""
    resposta = cliente.post(
        "/tarefas/lembretes", headers={"X-Tarefa-Token": "chute"}
    )
    assert resposta.status_code == 404


def test_token_certo_roda_e_devolve_os_contadores(cliente, sessao, cenario):
    _horario_daqui_a_vinte_horas(sessao, cenario)

    resposta = cliente.post("/tarefas/lembretes", headers={"X-Tarefa-Token": TOKEN})

    assert resposta.status_code == 200
    assert set(resposta.json()) >= {
        "reservados", "enviados", "descartados", "expirados"
    }


def test_a_resposta_nao_leva_nome_nem_telefone(cliente, sessao, cenario):
    """Isto vai para o log de um serviço de cron de terceiro."""
    _horario_daqui_a_vinte_horas(sessao, cenario)

    corpo = cliente.post(
        "/tarefas/lembretes", headers={"X-Tarefa-Token": TOKEN}
    ).text

    assert "MARIA" not in corpo
    assert "99999" not in corpo


def test_chamar_duas_vezes_nao_duplica(cliente, sessao, cenario):
    _horario_daqui_a_vinte_horas(sessao, cenario)

    cliente.post("/tarefas/lembretes", headers={"X-Tarefa-Token": TOKEN})
    cliente.post("/tarefas/lembretes", headers={"X-Tarefa-Token": TOKEN})

    assert sessao.query(Lembrete).count() == 1


def test_sem_token_configurado_o_endpoint_nao_existe(cliente, monkeypatch):
    """Ambiente sem `TAREFAS_TOKEN` não pode ter um endpoint que qualquer um
    chama mandando o cabeçalho vazio."""
    monkeypatch.setattr(config, "tarefas_token", "")

    resposta = cliente.post("/tarefas/lembretes", headers={"X-Tarefa-Token": ""})

    assert resposta.status_code == 404
