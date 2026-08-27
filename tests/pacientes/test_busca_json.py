"""Busca de paciente em JSON, para a janela que fecha o atendimento.

E a MESMA busca da lista (nome, telefone, codigo) — so muda o embrulho. Se um dia
divergirem, a dentista acha o paciente numa tela e nao acha na outra.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes.models import Paciente, PacienteTelefone
from app.shared.db import obter_sessao


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    amanda = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="AMANDA ROSA")
    joao = Paciente(clinica_id=clinica.id, codigo_legado="0002/PT", nome="JOAO PEDRO")
    sessao.add_all([amanda, joao])
    sessao.flush()
    sessao.add(
        PacienteTelefone(
            paciente_id=joao.id, numero="51999881234",
            numero_original="51999881234", principal=True,
        )
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        yield c, clinica, amanda


def test_acha_por_nome(cliente):
    c, _, amanda = cliente
    achados = c.get("/api/pacientes?q=amanda").json()["pacientes"]
    assert [p["id"] for p in achados] == [amanda.id]
    assert achados[0]["nome"] == "AMANDA ROSA"
    assert achados[0]["codigo_legado"] == "0001/PT"


def test_acha_por_telefone(cliente):
    c, *_ = cliente
    achados = c.get("/api/pacientes?q=99881234").json()["pacientes"]
    assert [p["nome"] for p in achados] == ["JOAO PEDRO"]


def test_acha_por_codigo_do_dentalis(cliente):
    c, *_ = cliente
    achados = c.get("/api/pacientes?q=0002/PT").json()["pacientes"]
    assert [p["nome"] for p in achados] == ["JOAO PEDRO"]


def test_busca_vazia_nao_despeja_a_base_inteira(cliente):
    """Abrir a janela nao e motivo para carregar 5.561 nomes."""
    c, *_ = cliente
    assert c.get("/api/pacientes?q=").json()["pacientes"] == []


def test_nao_enxerga_paciente_de_outra_clinica(sessao, cliente):
    c, *_ = cliente
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    sessao.add(Paciente(clinica_id=outra.id, nome="AMANDA DE OUTRA"))
    sessao.flush()
    nomes = [p["nome"] for p in c.get("/api/pacientes?q=amanda").json()["pacientes"]]
    assert nomes == ["AMANDA ROSA"]


def test_sem_sessao_e_recusada(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get("/api/pacientes?q=amanda").status_code == 303
