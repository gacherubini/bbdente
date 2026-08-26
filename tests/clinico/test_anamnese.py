from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.clinico.models import PerguntaAnamnese, RespostaAnamnese
from app.clinico.service import anamnese, responder
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    paciente = Paciente(clinica_id=clinica.id, nome="Amanda")
    sessao.add(paciente)
    perguntas = [
        PerguntaAnamnese(
            clinica_id=clinica.id, codigo=f"{i:02d}",
            texto=f"Pergunta {i}", tipo_resposta=1, ordem=i,
        )
        for i in range(1, 4)
    ]
    sessao.add_all(perguntas)
    sessao.flush()
    return clinica, usuario, paciente, perguntas


def test_paciente_novo_ve_o_questionario_em_branco(sessao, base):
    clinica, _, paciente, _ = base
    itens = anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    assert len(itens) == 3
    assert all(item["resposta"] is None for item in itens)


def test_o_questionario_vem_na_ordem_do_catalogo(sessao, base):
    clinica, _, paciente, _ = base
    itens = anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    assert [item["codigo"] for item in itens] == ["01", "02", "03"]


def test_pergunta_inativa_nao_aparece(sessao, base):
    clinica, _, paciente, perguntas = base
    perguntas[1].ativa = False
    sessao.flush()
    codigos = [
        item["codigo"]
        for item in anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    ]
    assert codigos == ["01", "03"]


def test_responder_grava_e_aparece_na_proxima_leitura(sessao, base):
    clinica, usuario, paciente, perguntas = base
    gravadas = responder(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        respostas={perguntas[0].id: "Sim", perguntas[2].id: "toma losartana"},
    )
    sessao.flush()
    assert gravadas == 2
    por_codigo = {
        item["codigo"]: item
        for item in anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    }
    assert por_codigo["01"]["resposta"] == "Sim"
    assert por_codigo["03"]["resposta"] == "toma losartana"
    assert por_codigo["02"]["resposta"] is None
    assert por_codigo["01"]["respondido_em"] == date.today()


def test_responder_de_novo_atualiza_em_vez_de_duplicar(sessao, base):
    clinica, usuario, paciente, perguntas = base
    for resposta in ("Sim", "Não"):
        responder(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, respostas={perguntas[0].id: resposta},
        )
        sessao.flush()
    assert sessao.query(RespostaAnamnese).count() == 1
    assert sessao.scalars(select(RespostaAnamnese)).one().resposta == "Não"


def test_resposta_vazia_nao_cria_linha(sessao, base):
    clinica, usuario, paciente, perguntas = base
    assert (
        responder(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, respostas={perguntas[0].id: "   "},
        )
        == 0
    )
    sessao.flush()
    assert sessao.query(RespostaAnamnese).count() == 0


def test_responder_deixa_rastro_na_auditoria(sessao, base):
    clinica, usuario, paciente, perguntas = base
    responder(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        respostas={perguntas[0].id: "Sim"},
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "resposta_anamnese")
    ).all()
    assert len(linhas) == 1


def test_a_tela_mostra_as_perguntas_e_grava_o_formulario(sessao, base):
    clinica, usuario, paciente, perguntas = base
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        html = c.get(f"/anamnese/{paciente.id}").text
        assert "Pergunta 1" in html
        assert "Amanda" in html

        resposta = c.post(
            f"/anamnese/{paciente.id}", data={f"pergunta_{perguntas[0].id}": "Sim"}
        )
        assert resposta.status_code == 303
    sessao.flush()
    assert sessao.query(RespostaAnamnese).count() == 1
