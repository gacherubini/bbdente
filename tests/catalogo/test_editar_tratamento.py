"""Editar tratamento e preco.

Duas regras que estes testes guardam:

- **preco antigo nunca some.** Trocar preco grava vigencia nova; o lancamento de
  2015 foi cobrado ao preco de 2015 e o extrato tem de continuar explicavel.
- **inativar nao apaga.** O tratamento sai das listas novas e continua desenhado
  no historico de quem ja o recebeu.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.catalogo.service import arvore, definir_preco
from app.main import criar_app
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo

HOJE = date.today()


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    dentistica = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    protese = Categoria(clinica_id=clinica.id, codigo="06", nome="Protese", ordem=6)
    particular = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([dentistica, protese, particular])
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=dentistica.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    sessao.add(restauracao)
    sessao.flush()
    return clinica, usuario, restauracao, dentistica, protese, particular


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def quantos_precos(sessao) -> int:
    return sessao.scalars(select(func.count()).select_from(Preco)).one()


def formulario(cenario, **extra) -> dict:
    _, _, restauracao, dentistica, _, _ = cenario
    corpo = {
        "codigo": restauracao.codigo,
        "nome": restauracao.nome,
        "categoria_id": str(dentistica.id),
        "escopo_sugerido": "REGIOES",
        "ativo": "1",
    }
    corpo.update(extra)
    return corpo


# --- a tela --------------------------------------------------------------------


def test_a_tela_de_edicao_abre_com_o_tratamento_preenchido(cliente, cenario):
    _, _, restauracao, *_ = cenario
    resposta = cliente.get(f"/tratamentos/{restauracao.id}")
    assert resposta.status_code == 200
    assert "Restauracao" in resposta.text


def test_tratamento_inexistente_da_404(cliente):
    assert cliente.get("/tratamentos/999999").status_code == 404


def test_tratamento_de_outra_clinica_da_404(sessao, cliente):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    cat = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    sessao.add(cat)
    sessao.flush()
    alheio = Procedimento(
        clinica_id=outra.id, codigo="21", nome="Alheio", categoria_id=cat.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(alheio)
    sessao.flush()
    assert cliente.get(f"/tratamentos/{alheio.id}").status_code == 404


# --- editar o tratamento -------------------------------------------------------


def test_editar_o_nome_grava_e_volta_para_a_lista(sessao, cliente, cenario):
    _, _, restauracao, *_ = cenario
    resposta = cliente.post(
        f"/tratamentos/{restauracao.id}",
        data=formulario(cenario, nome="Restauracao em resina"),
    )
    assert resposta.status_code == 303
    sessao.refresh(restauracao)
    assert restauracao.nome == "Restauracao em resina"


def test_a_edicao_deixa_antes_e_depois_na_auditoria(sessao, cliente, cenario):
    _, usuario, restauracao, *_ = cenario
    cliente.post(
        f"/tratamentos/{restauracao.id}",
        data=formulario(cenario, nome="Restauracao em resina"),
    )
    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "procedimento", Auditoria.acao == "ATUALIZAR"
        )
    ).one()
    assert linha.dados_antes["nome"] == "Restauracao"
    assert linha.dados_depois["nome"] == "Restauracao em resina"
    assert linha.usuario_id == usuario.id


def test_mudar_de_categoria_funciona(sessao, cliente, cenario):
    _, _, restauracao, _, protese, _ = cenario
    cliente.post(
        f"/tratamentos/{restauracao.id}",
        data=formulario(cenario, categoria_id=str(protese.id)),
    )
    sessao.refresh(restauracao)
    assert restauracao.categoria_id == protese.id


def test_nome_vazio_e_recusado(sessao, cliente, cenario):
    _, _, restauracao, *_ = cenario
    resposta = cliente.post(
        f"/tratamentos/{restauracao.id}", data=formulario(cenario, nome="   ")
    )
    assert resposta.status_code == 200
    sessao.refresh(restauracao)
    assert restauracao.nome == "Restauracao"


def test_codigo_de_outro_tratamento_e_recusado(sessao, cliente, cenario):
    clinica, _, restauracao, dentistica, _, _ = cenario
    outro = Procedimento(
        clinica_id=clinica.id, codigo="22", nome="Coroa", categoria_id=dentistica.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(outro)
    sessao.flush()
    resposta = cliente.post(
        f"/tratamentos/{restauracao.id}", data=formulario(cenario, codigo="22")
    )
    assert resposta.status_code == 200
    assert "22" in resposta.text
    sessao.refresh(restauracao)
    assert restauracao.codigo == "21"


# --- inativar ------------------------------------------------------------------


def test_inativar_tira_das_listas_novas_sem_apagar(sessao, cliente, cenario):
    clinica, _, restauracao, *_ = cenario
    cliente.post(f"/tratamentos/{restauracao.id}", data=formulario(cenario, ativo=""))
    sessao.refresh(restauracao)
    assert restauracao.ativo is False
    assert sessao.get(Procedimento, restauracao.id) is not None
    nomes = [
        p["nome"]
        for categoria in arvore(sessao, clinica_id=clinica.id)
        for p in categoria["procedimentos"]
    ]
    assert "Restauracao" not in nomes


# --- preco ---------------------------------------------------------------------


def test_salvar_preco_novo_cria_vigencia_e_mantem_a_antiga(sessao, cliente, cenario):
    clinica, usuario, restauracao, _, _, particular = cenario
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id,
        procedimento_id=restauracao.id, convenio_id=particular.id,
        valor=Decimal("120.00"), vigente_desde=HOJE - timedelta(days=400),
    )
    sessao.flush()

    cliente.post(
        f"/tratamentos/{restauracao.id}",
        data=formulario(cenario, convenio_id=str(particular.id), valor="180,00"),
    )
    assert quantos_precos(sessao) == 2
    guardados = sessao.scalars(
        select(Preco).where(Preco.procedimento_id == restauracao.id)
    )
    valores = sorted(p.valor for p in guardados)
    assert valores == [Decimal("120.00"), Decimal("180.00")]


def test_salvar_o_mesmo_preco_de_novo_nao_cria_linha(sessao, cliente, cenario):
    """Senao a tabela de precos vira o registro de quantas vezes alguem clicou."""
    _, _, restauracao, _, _, particular = cenario
    dados = formulario(cenario, convenio_id=str(particular.id), valor="180,00")
    cliente.post(f"/tratamentos/{restauracao.id}", data=dados)
    assert quantos_precos(sessao) == 1
    cliente.post(f"/tratamentos/{restauracao.id}", data=dados)
    assert quantos_precos(sessao) == 1


def test_preco_com_virgula_e_ponto_de_milhar_entra_certo(sessao, cliente, cenario):
    _, _, restauracao, _, _, particular = cenario
    cliente.post(
        f"/tratamentos/{restauracao.id}",
        data=formulario(cenario, convenio_id=str(particular.id), valor="1.250,50"),
    )
    preco = sessao.scalars(select(Preco)).one()
    assert preco.valor == Decimal("1250.50")


def test_preco_negativo_e_recusado(sessao, cliente, cenario):
    _, _, restauracao, _, _, particular = cenario
    resposta = cliente.post(
        f"/tratamentos/{restauracao.id}",
        data=formulario(cenario, convenio_id=str(particular.id), valor="-10,00"),
    )
    assert resposta.status_code == 200
    assert quantos_precos(sessao) == 0


def test_salvar_sem_mexer_no_preco_nao_cria_nada(sessao, cliente, cenario):
    _, _, restauracao, *_ = cenario
    cliente.post(f"/tratamentos/{restauracao.id}", data=formulario(cenario))
    assert quantos_precos(sessao) == 0
