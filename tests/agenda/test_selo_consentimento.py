"""O selo de consentimento no cartao, e o botao de um clique.

A base de autorizacao so cresce se perguntar for barato: a hora de perguntar e
com a paciente ali, marcando o retorno. Um clique no cartao, sem sair da agenda.
"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.agenda import service
from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes import service as pacientes
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
    paciente = pacientes.criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="MARIA SILVA",
        telefone="51999998888",
    )
    return {"clinica": clinica, "usuario": usuario, "paciente": paciente}


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def _marcar(sessao, cenario, **kwargs):
    dados = {"dia": QUARTA, "inicio": time(9, 0)}
    dados.update(kwargs)
    return service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        **dados,
    )


def test_quem_nunca_foi_perguntada_ganha_o_selo_e_o_botao(cliente, sessao, cenario):
    _marcar(sessao, cenario, paciente_id=cenario["paciente"].id)

    pagina = cliente.get(f"/agenda?dia={QUARTA.isoformat()}").text

    assert "perguntar" in pagina
    assert f'action="/pacientes/{cenario["paciente"].id}/whatsapp"' in pagina


def test_um_clique_registra_a_autorizacao_e_volta_para_a_agenda(cliente, sessao, cenario):
    paciente = cenario["paciente"]
    _marcar(sessao, cenario, paciente_id=paciente.id)

    resposta = cliente.post(
        f"/pacientes/{paciente.id}/whatsapp",
        data={"aceita": "sim", "voltar": f"/agenda?dia={QUARTA.isoformat()}"},
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/agenda?dia={QUARTA.isoformat()}"
    assert paciente.aceita_whatsapp is True
    assert sessao.query(Auditoria).filter_by(acao="CONSENTIMENTO").count() == 1


def test_quem_ja_autorizou_nao_e_perguntada_de_novo(cliente, sessao, cenario):
    paciente = cenario["paciente"]
    pacientes.definir_consentimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=paciente.id,
        aceita=True,
    )
    _marcar(sessao, cenario, paciente_id=paciente.id)

    pagina = cliente.get(f"/agenda?dia={QUARTA.isoformat()}").text

    assert "perguntar" not in pagina


def test_quem_nao_tem_numero_aproveitavel_diz_que_nao_ha_lembrete(
    cliente, sessao, cenario
):
    """Nao adianta perguntar autorizacao de quem nao tem numero para receber."""
    sem_numero = Paciente(clinica_id=cenario["clinica"].id, nome="SEM TELEFONE")
    sessao.add(sem_numero)
    sessao.flush()
    _marcar(sessao, cenario, paciente_id=sem_numero.id)

    pagina = cliente.get(f"/agenda?dia={QUARTA.isoformat()}").text

    assert "sem lembrete" in pagina


def test_o_voltar_so_aceita_caminho_de_dentro_do_sistema(cliente, sessao, cenario):
    """`voltar` vem de formulario, e formulario e coisa que se edita. Endereco de
    fora vira redirecionamento aberto — o sistema mandando a dentista para um
    site que nao e dele."""
    paciente = cenario["paciente"]

    resposta = cliente.post(
        f"/pacientes/{paciente.id}/whatsapp",
        data={"aceita": "sim", "voltar": "https://exemplo.invalido/roubo"},
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/pacientes/{paciente.id}/editar"


def test_resposta_inventada_nao_muda_nada(cliente, sessao, cenario):
    paciente = cenario["paciente"]

    resposta = cliente.post(
        f"/pacientes/{paciente.id}/whatsapp", data={"aceita": "talvez"}
    )

    assert resposta.status_code == 400
    assert paciente.aceita_whatsapp is None


def test_paciente_de_outra_clinica_da_404(cliente, sessao):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    estranha = Paciente(clinica_id=outra.id, nome="ALHEIA")
    sessao.add(estranha)
    sessao.flush()

    assert (
        cliente.post(
            f"/pacientes/{estranha.id}/whatsapp", data={"aceita": "sim"}
        ).status_code
        == 404
    )


def test_a_ficha_abre_e_mostra_a_permissao(cliente, cenario):
    """Este teste existe porque um erro de edicao de template jogou o formulario
    de permissao para dentro do `block titulo` e a suite inteira passou: nenhum
    teste abria esta tela."""
    paciente = cenario["paciente"]

    resposta = cliente.get(f"/pacientes/{paciente.id}/editar")

    assert resposta.status_code == 200
    assert f"<title>Editar {paciente.nome} — BDDente</title>" in resposta.text
    assert "Nunca perguntamos" in resposta.text
    assert 'value="nao_perguntado"' in resposta.text


def test_a_ficha_diz_quando_ela_pediu_para_nao_receber(cliente, sessao, cenario):
    paciente = cenario["paciente"]
    pacientes.definir_consentimento(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        paciente_id=paciente.id,
        aceita=False,
    )

    pagina = cliente.get(f"/pacientes/{paciente.id}/editar").text

    assert "Pediu para não receber" in pagina


def test_o_cadastro_novo_oferece_as_tres_opcoes(cliente):
    pagina = cliente.get("/pacientes/novo").text

    assert 'name="aceita_whatsapp" value=""' in pagina
    assert 'name="aceita_whatsapp" value="sim"' in pagina
    assert 'name="aceita_whatsapp" value="nao"' in pagina
