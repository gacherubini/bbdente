"""Editar o preco de cada convenio direto na tela do tratamento.

Antes era um preco por vez: escolher o convenio num select e digitar o valor.
Agora a lista de precos vigentes e editavel — um campo por convenio, todos
salvos junto com o resto do formulario.

As duas regras que estes testes guardam:

- **preco antigo nunca some.** Mudar o valor grava vigencia nova; o lancamento de
  2015 foi cobrado ao preco de 2015 e o extrato tem de continuar explicavel.
- **so nasce linha para quem mudou.** Salvar o formulario sem tocar nos precos
  nao pode criar nada, senao a tabela de precos vira o registro de quantas vezes
  alguem clicou em Salvar.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
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
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    particular = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    uniodonto = Convenio(clinica_id=clinica.id, codigo="051", nome="UNIODONTO")
    sem_tabela = Convenio(clinica_id=clinica.id, codigo="003", nome="Convenio 003")
    sessao.add_all([categoria, particular, uniodonto, sem_tabela])
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    sessao.add(restauracao)
    sessao.flush()
    sessao.add_all([
        Preco(procedimento_id=restauracao.id, convenio_id=particular.id,
              valor=Decimal("180.00"), vigente_desde=HOJE - timedelta(days=400)),
        Preco(procedimento_id=restauracao.id, convenio_id=uniodonto.id,
              valor=Decimal("62.16"), vigente_desde=HOJE - timedelta(days=400)),
    ])
    sessao.flush()
    return {
        "clinica": clinica, "usuario": usuario, "procedimento": restauracao,
        "categoria": categoria, "particular": particular, "uniodonto": uniodonto,
        "sem_tabela": sem_tabela,
    }


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def quantos_precos(sessao) -> int:
    return sessao.scalars(select(func.count()).select_from(Preco)).one()


def vigencias(sessao, procedimento_id, convenio_id) -> list[Decimal]:
    return sorted(
        sessao.scalars(
            select(Preco.valor).where(
                Preco.procedimento_id == procedimento_id,
                Preco.convenio_id == convenio_id,
            )
        )
    )


def formulario(cenario, precos=None, **campos) -> dict:
    """O formulario inteiro da tela de edicao, com um campo de preco por convenio.

    Os convenios vao em `preco_convenio_id` e os valores em `preco_valor`, na
    mesma ordem — e o par que o navegador manda ao repetir os campos.
    """
    ordem = ["particular", "uniodonto", "sem_tabela"]
    valores = {"particular": "180,00", "uniodonto": "62,16", "sem_tabela": ""}
    valores.update(precos or {})
    corpo = {
        "codigo": cenario["procedimento"].codigo,
        "nome": cenario["procedimento"].nome,
        "categoria_id": str(cenario["categoria"].id),
        "escopo_sugerido": "REGIOES",
        "ativo": "1",
        "preco_convenio_id": [str(cenario[c].id) for c in ordem],
        "preco_valor": [valores[c] for c in ordem],
    }
    corpo.update(campos)
    return corpo


def postar(cliente, cenario, precos=None, **campos):
    return cliente.post(
        f"/tratamentos/{cenario['procedimento'].id}",
        data=formulario(cenario, precos, **campos),
    )


PAR = re.compile(
    r'name="preco_convenio_id" value="(\d+)".*?name="preco_valor"[^>]*value="([^"]*)"',
    re.S,
)


def campos_de_preco(cliente, cenario) -> dict[int, str]:
    """Os pares (convenio, valor) que a tela desenhou, na ordem em que aparecem."""
    html = cliente.get(f"/tratamentos/{cenario['procedimento'].id}").text
    return {int(convenio): valor for convenio, valor in PAR.findall(html)}


# --- a tela --------------------------------------------------------------------


def test_a_tela_traz_um_campo_de_valor_por_convenio(cliente, cenario):
    campos = campos_de_preco(cliente, cenario)
    assert set(campos) == {
        cenario["particular"].id,
        cenario["uniodonto"].id,
        cenario["sem_tabela"].id,
    }


def test_o_campo_ja_vem_com_o_preco_vigente(cliente, cenario):
    campos = campos_de_preco(cliente, cenario)
    assert campos[cenario["particular"].id] == "180,00"
    assert campos[cenario["uniodonto"].id] == "62,16"


def test_convenio_sem_preco_vem_com_o_campo_vazio(cliente, cenario):
    """Vazio, nao 0,00: 'sem tabela' e 'de graca' sao coisas diferentes."""
    assert campos_de_preco(cliente, cenario)[cenario["sem_tabela"].id] == ""


# --- salvar --------------------------------------------------------------------


def test_mudar_um_preco_cria_vigencia_nova_e_mantem_a_antiga(sessao, cliente, cenario):
    resposta = postar(cliente, cenario, {"particular": "200,00"})
    assert resposta.status_code == 303
    assert vigencias(sessao, cenario["procedimento"].id, cenario["particular"].id) == [
        Decimal("180.00"),
        Decimal("200.00"),
    ]


def test_da_para_mudar_varios_precos_de_uma_vez(sessao, cliente, cenario):
    postar(cliente, cenario, {"particular": "200,00", "uniodonto": "70,00"})
    assert quantos_precos(sessao) == 4
    assert vigencias(sessao, cenario["procedimento"].id, cenario["uniodonto"].id) == [
        Decimal("62.16"),
        Decimal("70.00"),
    ]


def test_salvar_sem_tocar_nos_precos_nao_cria_nenhuma_linha(sessao, cliente, cenario):
    """Senao a tabela de precos vira o registro de quantas vezes alguem clicou."""
    postar(cliente, cenario)
    assert quantos_precos(sessao) == 2
    postar(cliente, cenario)
    assert quantos_precos(sessao) == 2


def test_so_nasce_linha_para_o_convenio_que_mudou(sessao, cliente, cenario):
    postar(cliente, cenario, {"particular": "200,00"})
    assert quantos_precos(sessao) == 3
    assert vigencias(sessao, cenario["procedimento"].id, cenario["uniodonto"].id) == [
        Decimal("62.16")
    ]


def test_convenio_sem_tabela_pode_ganhar_preco(sessao, cliente, cenario):
    postar(cliente, cenario, {"sem_tabela": "45,60"})
    assert vigencias(sessao, cenario["procedimento"].id, cenario["sem_tabela"].id) == [
        Decimal("45.60")
    ]


def test_campo_vazio_nao_apaga_o_preco_que_ja_existe(sessao, cliente, cenario):
    """Vazio e 'nao mexer'. Apagar preco nao existe: o historico precisa dele."""
    postar(cliente, cenario, {"particular": ""})
    assert vigencias(sessao, cenario["procedimento"].id, cenario["particular"].id) == [
        Decimal("180.00")
    ]


def test_preco_com_ponto_de_milhar_entra_certo(sessao, cliente, cenario):
    postar(cliente, cenario, {"particular": "1.250,50"})
    assert Decimal("1250.50") in vigencias(
        sessao, cenario["procedimento"].id, cenario["particular"].id
    )


def test_cada_preco_novo_deixa_linha_na_auditoria(sessao, cliente, cenario):
    postar(cliente, cenario, {"particular": "200,00", "sem_tabela": "45,60"})
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "preco", Auditoria.acao == "CRIAR")
    ).all()
    assert len(linhas) == 2
    assert {linha.dados_depois["valor"] for linha in linhas} == {"200.00", "45.60"}
    assert all(linha.usuario_id == cenario["usuario"].id for linha in linhas)


# --- valor invalido ------------------------------------------------------------


def test_valor_invalido_volta_o_formulario_com_erro(sessao, cliente, cenario):
    resposta = postar(cliente, cenario, {"uniodonto": "setenta reais"})
    assert resposta.status_code == 200
    assert "nao e um valor" in resposta.text


def test_valor_invalido_nao_grava_pela_metade(sessao, cliente, cenario):
    """O primeiro preco da lista e valido; o segundo nao. Nenhum dos dois entra."""
    postar(cliente, cenario, {"particular": "200,00", "uniodonto": "setenta reais"})
    assert quantos_precos(sessao) == 2
    sessao.refresh(cenario["procedimento"])
    assert vigencias(sessao, cenario["procedimento"].id, cenario["particular"].id) == [
        Decimal("180.00")
    ]


def test_valor_invalido_nao_grava_nem_o_resto_do_tratamento(sessao, cliente, cenario):
    postar(
        cliente, cenario, {"particular": "nada disso"}, nome="Restauracao em resina"
    )
    sessao.refresh(cenario["procedimento"])
    assert cenario["procedimento"].nome == "Restauracao"


def test_preco_negativo_e_recusado(sessao, cliente, cenario):
    resposta = postar(cliente, cenario, {"particular": "-10,00"})
    assert resposta.status_code == 200
    assert quantos_precos(sessao) == 2
