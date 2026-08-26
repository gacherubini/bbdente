"""Cadastro de paciente novo pela tela.

Quem cadastra esta com a pessoa na frente: o caminho tem de ser curto (nome basta) e
terminar no odontograma. E como a base tem 30 anos de historico, criar duplicata e o
erro caro — por isso o aviso de cadastro parecido vem antes de gravar, nunca depois.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Convenio
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    sessao.add(Convenio(clinica_id=clinica.id, codigo="UNI", nome="Unimed"))
    joana = Paciente(
        clinica_id=clinica.id,
        codigo_legado="0001/PT",
        nome="Joana Marques",
        ultimo_atendimento=date(2024, 3, 2),
    )
    sessao.add(joana)
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c, joana


def _quantos(sessao) -> int:
    return sessao.scalars(select(func.count()).select_from(Paciente)).one()


def test_o_formulario_ja_vem_com_o_nome_que_a_pessoa_buscou(cliente):
    """Ela acabou de buscar 'joana' e nao achou: nao pode ter de digitar de novo."""
    c, _ = cliente
    resposta = c.get("/pacientes/novo?nome=joana")
    assert resposta.status_code == 200
    assert 'value="joana"' in resposta.text


def test_o_formulario_lista_os_convenios_vindos_do_catalogo(cliente):
    c, _ = cliente
    assert "Unimed" in c.get("/pacientes/novo").text


def test_nome_vazio_devolve_o_formulario_com_erro_e_nao_grava(cliente, sessao):
    c, _ = cliente
    antes = _quantos(sessao)
    resposta = c.post("/pacientes/novo", data={"nome": "   "})
    assert resposta.status_code == 200
    assert "Digite o nome do paciente" in resposta.text
    assert _quantos(sessao) == antes


def test_nome_parecido_pede_confirmacao_antes_de_gravar(cliente, sessao):
    """Duplicata em base de 30 anos e o erro caro: avisar antes, nunca depois."""
    c, joana = cliente
    antes = _quantos(sessao)
    resposta = c.post("/pacientes/novo", data={"nome": "Joana Marques"})
    assert resposta.status_code == 200
    assert "Joana Marques" in resposta.text
    assert f'/odontograma/{joana.id}' in resposta.text
    assert "Cadastrar mesmo assim" in resposta.text
    assert _quantos(sessao) == antes, "nao pode gravar enquanto so avisa"


def test_confirmando_cria_e_leva_direto_para_o_odontograma(cliente, sessao):
    c, joana = cliente
    antes = _quantos(sessao)
    resposta = c.post(
        "/pacientes/novo", data={"nome": "Joana Marques", "confirmar": "1"}
    )
    assert resposta.status_code == 303
    assert _quantos(sessao) == antes + 1
    novo = sessao.scalars(
        select(Paciente).where(Paciente.id != joana.id, Paciente.nome == "Joana Marques")
    ).one()
    assert resposta.headers["location"] == f"/odontograma/{novo.id}"


def test_nome_inedito_cria_e_redireciona_sem_perguntar_nada(cliente, sessao):
    c, _ = cliente
    resposta = c.post(
        "/pacientes/novo",
        data={
            "nome": "Zuleica do Prado",
            "telefone": "11 98888-7777",
            "nascimento": "1980-05-04",
        },
    )
    assert resposta.status_code == 303
    novo = sessao.scalars(
        select(Paciente).where(Paciente.nome == "Zuleica do Prado")
    ).one()
    assert resposta.headers["location"] == f"/odontograma/{novo.id}"
    assert novo.nascimento == date(1980, 5, 4)


def test_a_lista_oferece_cadastrar_o_termo_que_a_busca_nao_achou(cliente):
    c, _ = cliente
    html = c.get("/pacientes?q=Wanderleia&filtro=todos").text
    assert "Nenhum paciente encontrado para «Wanderleia»" in html
    assert 'href="/pacientes/novo?nome=Wanderleia"' in html
    assert "cadastrar «Wanderleia»" in html


def test_a_lista_tem_o_botao_de_novo_paciente_levando_o_termo_digitado(cliente):
    c, _ = cliente
    html = c.get("/pacientes?q=Wanderleia&filtro=todos").text
    assert 'href="/pacientes/novo?nome=Wanderleia"' in html
    assert "Novo paciente" in html
