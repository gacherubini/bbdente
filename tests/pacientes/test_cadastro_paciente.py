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
        c.cookies.set(NOME_COOKIE, assinar(usuario))
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


# --- a ficha completa ----------------------------------------------------------


def test_a_tela_de_cadastro_traz_a_ficha_completa_recolhida(cliente):
    """O caminho curto continua curto: os campos existem, mas dentro de um bloco
    fechado — quem so quer abrir o odontograma nao passa por eles."""
    c, _ = cliente
    html = c.get("/pacientes/novo").text
    assert "<details" in html
    for campo in ("cpf", "indicacao", "observacao", "logradouro", "cidade", "cep"):
        assert f'name="{campo}"' in html


def test_cadastrar_com_a_ficha_completa_grava_tudo(sessao, cliente):
    c, _ = cliente
    resposta = c.post(
        "/pacientes/novo",
        data={
            "nome": "Nadia Prado",
            "telefone": "51 99999-1234",
            "cpf": "529.982.247-25",
            "indicacao": "Indicada pela irma",
            "observacao": "Usa aparelho.",
            "logradouro": "Rua Nova, 45",
            "bairro": "Cristal",
            "cidade": "Porto Alegre",
            "uf": "RS",
            "cep": "90810-000",
        },
    )
    assert resposta.status_code == 303
    novo = sessao.scalars(
        select(Paciente).where(Paciente.nome == "Nadia Prado")
    ).one()
    assert novo.cpf == "529.982.247-25"
    assert novo.indicacao == "Indicada pela irma"
    assert novo.observacao == "Usa aparelho."
    (endereco,) = novo.enderecos
    assert (endereco.tipo, endereco.logradouro, endereco.uf) == (
        "RESIDENCIAL", "Rua Nova, 45", "RS",
    )


def test_cadastro_sem_ficha_nao_cria_endereco_em_branco(sessao, cliente):
    c, _ = cliente
    c.post("/pacientes/novo", data={"nome": "Otavio Lemos"})
    novo = sessao.scalars(
        select(Paciente).where(Paciente.nome == "Otavio Lemos")
    ).one()
    assert novo.enderecos == []
    assert novo.cpf is None


def test_cpf_errado_no_cadastro_grava_marcado(sessao, cliente):
    c, _ = cliente
    c.post("/pacientes/novo", data={"nome": "Paula Vieira", "cpf": "529.982.247-26"})
    novo = sessao.scalars(
        select(Paciente).where(Paciente.nome == "Paula Vieira")
    ).one()
    assert novo.cpf == "529.982.247-26"
    assert "cpf_suspeito" in novo.revisar_motivo


def test_o_aviso_de_duplicata_nao_perde_a_ficha_digitada(cliente):
    """O formulario volta para confirmar: o que foi digitado tem de voltar junto."""
    c, joana = cliente
    resposta = c.post(
        "/pacientes/novo",
        data={"nome": "Joana Marques", "observacao": "Amiga da Joana",
              "cidade": "Viamao"},
    )
    assert resposta.status_code == 200
    assert "Amiga da Joana" in resposta.text
    assert "Viamao" in resposta.text
