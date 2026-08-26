"""Atender primeiro, identificar depois.

O menu 'Odontograma' abre a boca em branco: ela clica no dente, escolhe o
tratamento e so no fim diz de quem e. Enquanto nao disser, NADA vai para o banco
— e e isso que a maioria destes testes guarda.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Lancamento, Odontograma
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao

JS = Path("app/static/rascunho.js")


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.MESIAL, Regiao.OCLUSAL],
    )
    consulta = Procedimento(
        clinica_id=clinica.id, codigo="1", nome="Consulta",
        categoria_id=categoria.id, escopo_sugerido=Escopo.BOCA, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([restauracao, consulta, paciente])
    sessao.flush()
    return clinica, usuario, paciente, restauracao, consulta


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def quantos(sessao, modelo) -> int:
    return sessao.scalars(select(func.count()).select_from(modelo)).one()


def item(procedimento, **extra) -> dict:
    corpo = {
        "procedimento_id": procedimento.id,
        "escopo": "REGIOES",
        "dente": 16,
        "regioes": ["MESIAL"],
        "status": "PLANEJADO",
    }
    corpo.update(extra)
    return corpo


# --- a tela em branco ----------------------------------------------------------


def test_o_menu_abre_a_boca_em_branco_sem_pedir_paciente(cliente):
    resposta = cliente.get("/odontograma")
    assert resposta.status_code == 200
    bruto = re.search(
        r'id="estado-inicial"[^>]*>(.*?)</script>', resposta.text, re.S
    )
    assert bruto, "o JSON de estado nao esta embutido na pagina"
    estado = json.loads(bruto.group(1))
    assert len(estado["dentes"]) == 32
    assert estado["paciente"] is None
    assert estado["dentes"]["16"]["paredes"]["DIREITA"] == "MESIAL"


def test_a_tela_em_branco_avisa_que_ainda_nao_gravou(cliente):
    """Sem esse aviso ela nao tem como saber que o trabalho ainda esta solto."""
    html = cliente.get("/odontograma").text
    assert "Atendimento novo" in html
    assert "nada foi gravado" in html.lower()


def test_a_tela_em_branco_marca_a_aba_odontograma(cliente):
    assert 'href="/odontograma" class="ativo"' in cliente.get("/odontograma").text


def test_abrir_a_tela_em_branco_nao_cria_odontograma_nenhum(sessao, cliente):
    antes = quantos(sessao, Odontograma)
    cliente.get("/odontograma")
    assert quantos(sessao, Odontograma) == antes


# --- previa: pintar sem gravar -------------------------------------------------


def test_a_previa_pinta_o_dente_sem_gravar_nada(sessao, cliente, cenario):
    _, _, _, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/odontograma/previa",
        json={"itens": [item(restauracao, regioes=["MESIAL", "OCLUSAL"])]},
    )
    assert resposta.status_code == 200
    estado = resposta.json()
    assert estado["dentes"]["16"]["regioes"] == {
        "MESIAL": "PLANEJADO",
        "OCLUSAL": "PLANEJADO",
    }
    assert estado["paciente"] is None
    assert quantos(sessao, Lancamento) == 0
    assert quantos(sessao, Odontograma) == 0
    # A auditoria ja tem a linha da criacao do usuario do cenario: o que nao pode
    # existir e rastro de escrita clinica.
    assert sessao.scalars(
        select(func.count())
        .select_from(Auditoria)
        .where(Auditoria.entidade.in_(["lancamento", "paciente"]))
    ).one() == 0


def test_a_previa_respeita_a_ordem_de_forca_das_cores(cliente, cenario):
    """Mesma regra do odontograma gravado: planejado nao some atras de realizado."""
    _, _, _, restauracao, _ = cenario
    estado = cliente.post(
        "/api/odontograma/previa",
        json={
            "itens": [
                item(restauracao, status="REALIZADO"),
                item(restauracao, status="PLANEJADO"),
            ]
        },
    ).json()
    assert estado["dentes"]["16"]["regioes"]["MESIAL"] == "PLANEJADO"


def test_a_previa_poe_boca_toda_na_lista_de_boca(cliente, cenario):
    _, _, _, _, consulta = cenario
    estado = cliente.post(
        "/api/odontograma/previa",
        json={
            "itens": [
                item(
                    consulta,
                    escopo="BOCA",
                    dente=None,
                    regioes=[],
                    status="REALIZADO",
                )
            ]
        },
    ).json()
    assert estado["boca"][0]["procedimento"] == "Consulta"


def test_a_previa_recusa_escopo_invalido(cliente, cenario):
    _, _, _, _, consulta = cenario
    resposta = cliente.post(
        "/api/odontograma/previa",
        json={"itens": [item(consulta, escopo="BOCA", regioes=[])]},
    )
    assert resposta.status_code == 422
    assert "dente" in resposta.json()["detail"].lower()


def test_a_previa_recusa_tratamento_de_outra_clinica(sessao, cliente):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    categoria = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    alheio = Procedimento(
        clinica_id=outra.id, codigo="99", nome="Alheio", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(alheio)
    sessao.flush()
    resposta = cliente.post("/api/odontograma/previa", json={"itens": [item(alheio)]})
    assert resposta.status_code == 404


# --- concluir: agora sim grava -------------------------------------------------


def test_concluir_em_paciente_existente_grava_tudo_de_uma_vez(sessao, cliente, cenario):
    _, _, paciente, restauracao, consulta = cenario
    resposta = cliente.post(
        "/api/atendimento",
        json={
            "paciente_id": paciente.id,
            "itens": [
                item(restauracao),
                item(
                    consulta, escopo="BOCA", dente=None, regioes=[],
                    status="REALIZADO", valor="90.00",
                ),
            ],
        },
    )
    assert resposta.status_code == 201
    assert resposta.json()["paciente_id"] == paciente.id
    assert resposta.json()["lancamentos"] == 2
    assert quantos(sessao, Lancamento) == 2


def test_o_atendimento_concluido_vai_para_o_odontograma_do_paciente(cliente, cenario):
    _, _, paciente, restauracao, _ = cenario
    cliente.post(
        "/api/atendimento",
        json={"paciente_id": paciente.id, "itens": [item(restauracao)]},
    )
    estado = cliente.get(f"/api/odontograma/{paciente.id}").json()
    assert estado["dentes"]["16"]["regioes"]["MESIAL"] == "PLANEJADO"


def test_um_item_invalido_no_meio_nao_grava_nenhum(sessao, cliente, cenario):
    """Ou entra o atendimento inteiro, ou nao entra nada."""
    _, _, paciente, restauracao, consulta = cenario
    resposta = cliente.post(
        "/api/atendimento",
        json={
            "paciente_id": paciente.id,
            "itens": [item(restauracao), item(consulta, escopo="BOCA", regioes=[])],
        },
    )
    assert resposta.status_code == 422
    assert quantos(sessao, Lancamento) == 0


def test_atendimento_sem_item_nenhum_e_recusado(cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        "/api/atendimento", json={"paciente_id": paciente.id, "itens": []}
    )
    assert resposta.status_code == 422


def test_atendimento_sem_dizer_de_quem_e_recusado(cliente, cenario):
    _, _, _, restauracao, _ = cenario
    resposta = cliente.post("/api/atendimento", json={"itens": [item(restauracao)]})
    assert resposta.status_code == 422


def test_paciente_de_outra_clinica_da_404(sessao, cliente, cenario):
    _, _, _, restauracao, _ = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add(alheio)
    sessao.flush()
    resposta = cliente.post(
        "/api/atendimento",
        json={"paciente_id": alheio.id, "itens": [item(restauracao)]},
    )
    assert resposta.status_code == 404
    assert quantos(sessao, Lancamento) == 0


def test_cada_lancamento_do_atendimento_deixa_rastro_na_auditoria(
    sessao, cliente, cenario
):
    _, usuario, paciente, restauracao, _ = cenario
    cliente.post(
        "/api/atendimento",
        json={
            "paciente_id": paciente.id,
            "itens": [item(restauracao), item(restauracao, dente=26)],
        },
    )
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "lancamento")
    ).all()
    assert len(linhas) == 2
    assert {linha.acao for linha in linhas} == {"CRIAR"}
    assert {linha.usuario_id for linha in linhas} == {usuario.id}


# --- concluir cadastrando a pessoa na hora -------------------------------------


def test_concluir_cadastrando_o_paciente_na_hora(sessao, cliente, cenario):
    _, _, _, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/atendimento",
        json={
            "novo": {
                "nome": "Joana Ribeiro",
                "telefone": "(51) 99999-1234",
                "nascimento": "1980-03-14",
            },
            "itens": [item(restauracao)],
        },
    )
    assert resposta.status_code == 201
    criado = sessao.get(Paciente, resposta.json()["paciente_id"])
    assert criado.nome == "Joana Ribeiro"
    assert criado.nascimento.isoformat() == "1980-03-14"
    assert quantos(sessao, Lancamento) == 1


def test_nome_parecido_avisa_antes_de_criar_e_nao_grava_nada(sessao, cliente, cenario):
    """Duplicata em base de 30 anos e o erro caro: avisa, e quem atende decide."""
    _, _, _, restauracao, _ = cenario
    antes = quantos(sessao, Paciente)
    resposta = cliente.post(
        "/api/atendimento",
        json={"novo": {"nome": "amanda"}, "itens": [item(restauracao)]},
    )
    assert resposta.status_code == 200
    assert "Amanda" in [p["nome"] for p in resposta.json()["parecidos"]]
    assert quantos(sessao, Paciente) == antes
    assert quantos(sessao, Lancamento) == 0


def test_confirmando_o_aviso_cadastra_mesmo_assim(sessao, cliente, cenario):
    _, _, _, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/atendimento",
        json={
            "novo": {"nome": "amanda"},
            "confirmar": True,
            "itens": [item(restauracao)],
        },
    )
    assert resposta.status_code == 201
    assert quantos(sessao, Lancamento) == 1


def test_cadastrar_sem_nome_e_recusado(sessao, cliente, cenario):
    _, _, _, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/atendimento",
        json={"novo": {"nome": "   "}, "itens": [item(restauracao)]},
    )
    assert resposta.status_code == 422
    assert quantos(sessao, Lancamento) == 0


def test_o_paciente_cadastrado_na_hora_entra_sem_codigo_do_dentalis(
    sessao, cliente, cenario
):
    _, _, _, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/atendimento",
        json={"novo": {"nome": "Joana Ribeiro"}, "itens": [item(restauracao)]},
    )
    criado = sessao.get(Paciente, resposta.json()["paciente_id"])
    assert criado.codigo_legado is None


# --- a lista de pacientes nao e mais desvio do odontograma ----------------------


def test_a_lista_de_pacientes_nao_pede_mais_para_escolher(cliente):
    assert "Escolha um paciente" not in cliente.get("/pacientes").text


# --- contrato do rascunho ------------------------------------------------------


def test_o_rascunho_pede_a_pintura_ao_servidor_em_vez_de_decidir_a_cor():
    """A regra de qual cor vence tem teste em Python. Se o JS decidir sozinho,
    passa a existir em dois lugares — e um deles fica sem teste."""
    fonte = JS.read_text(encoding="utf-8")
    assert "/api/odontograma/previa" in fonte
    for proibido in ("#DC2626", "#16A34A", "FORCA"):
        assert proibido not in fonte, f"o rascunho comecou a pintar sozinho: {proibido}"
