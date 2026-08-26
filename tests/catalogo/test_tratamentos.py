from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.catalogo.service import (
    CodigoRepetido,
    arvore,
    definir_preco,
    preco_de,
    salvar_procedimento,
)
from app.shared.tipos import Escopo, Regiao


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([categoria, convenio])
    sessao.flush()
    return clinica, usuario, categoria, convenio


def test_cria_tratamento_novo(sessao, base):
    clinica, usuario, categoria, _ = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    assert p.id is not None
    assert sessao.get(Procedimento, p.id).nome == "Clareamento"


def test_edita_tratamento_existente_sem_criar_outro(sessao, base):
    clinica, usuario, categoria, _ = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        codigo="900", nome="Clareamento a laser", categoria_id=categoria.id,
        escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[Regiao.VESTIBULAR],
    )
    sessao.flush()
    assert sessao.query(Procedimento).count() == 1
    guardado = sessao.get(Procedimento, p.id)
    assert guardado.nome == "Clareamento a laser"
    assert guardado.regioes_sugeridas == [Regiao.VESTIBULAR]


def test_codigo_repetido_na_mesma_clinica_e_recusado(sessao, base):
    clinica, usuario, categoria, _ = base
    for _ in range(1):
        salvar_procedimento(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
            nome="A", categoria_id=categoria.id,
            escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
        )
        sessao.flush()
    with pytest.raises(CodigoRepetido):
        salvar_procedimento(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
            nome="B", categoria_id=categoria.id,
            escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
        )


def test_desativar_tira_do_painel_mas_nao_apaga(sessao, base):
    """Prontuario antigo continua apontando para o tratamento: nunca se apaga."""
    clinica, usuario, categoria, _ = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Antigo", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[], ativo=False,
    )
    sessao.flush()
    assert sessao.get(Procedimento, p.id) is not None
    nomes = [
        proc["nome"]
        for cat in arvore(sessao, clinica_id=clinica.id)
        for proc in cat["procedimentos"]
    ]
    assert "Antigo" not in nomes


def test_preco_por_convenio(sessao, base):
    clinica, usuario, categoria, convenio = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        convenio_id=convenio.id, valor=Decimal("450.00"),
    )
    sessao.flush()
    assert preco_de(sessao, procedimento_id=p.id, convenio_id=convenio.id) == Decimal("450.00")


def test_preco_novo_nao_apaga_o_antigo_e_vence(sessao, base):
    """O historico de precos importa: um lancamento de 2015 foi cobrado ao preco
    de 2015."""
    clinica, usuario, categoria, convenio = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="X", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        convenio_id=convenio.id, valor=Decimal("100.00"), vigente_desde=date(2015, 1, 1),
    )
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        convenio_id=convenio.id, valor=Decimal("450.00"), vigente_desde=date(2026, 1, 1),
    )
    sessao.flush()
    from app.catalogo.models import Preco

    assert sessao.query(Preco).count() == 2
    assert preco_de(sessao, procedimento_id=p.id, convenio_id=convenio.id) == Decimal("450.00")


def test_preco_inexistente_devolve_none(sessao, base):
    clinica, usuario, categoria, convenio = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="X", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    assert preco_de(sessao, procedimento_id=p.id, convenio_id=convenio.id) is None


def test_salvar_deixa_rastro_na_auditoria(sessao, base):
    clinica, usuario, categoria, _ = base
    salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="X", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "procedimento")
    ).all()
    assert len(linhas) == 1 and linhas[0].acao == "CRIAR"


def test_a_tela_agrupa_por_categoria(sessao, base):
    from fastapi.testclient import TestClient

    from app.main import criar_app
    from app.shared.db import obter_sessao

    clinica, usuario, categoria, _ = base
    salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        html = c.get("/tratamentos").text
    assert "Dentistica" in html
    assert "Clareamento" in html
    assert 'href="/tratamentos" class="ativo"' in html
