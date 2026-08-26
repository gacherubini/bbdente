from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Condicao, Lancamento, Odontograma
from app.clinico.service import (
    EscopoInvalido,
    estado_do_odontograma,
    excluir_lancamento,
    historico,
    lancar,
)
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento, TipoCondicao


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


# --- estado --------------------------------------------------------------------

def test_odontograma_vazio_traz_os_32_dentes(sessao, cenario):
    clinica, _, paciente, *_ = cenario
    estado = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )
    assert len(estado["dentes"]) == 32
    assert estado["dentes"]["16"]["regioes"] == {}
    assert estado["boca"] == []
    assert estado["paciente"]["nome"] == "Amanda"


def test_cada_dente_traz_sua_anatomia(sessao, cenario):
    clinica, _, paciente, *_ = cenario
    dentes = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]
    assert dentes["16"]["raizes"] == 3
    assert dentes["36"]["raizes"] == 2
    assert dentes["11"]["raizes"] == 1
    assert dentes["11"]["anterior"] is True
    assert dentes["16"]["anterior"] is False
    assert dentes["11"]["canais"] == ["CANAL_CENTRAL"]


def test_lancamento_em_regiao_aparece_no_estado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL, Regiao.OCLUSAL], status=StatusLancamento.PLANEJADO,
        valor=Decimal("180.00"),
    )
    sessao.flush()
    dente = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]["16"]
    assert dente["regioes"] == {"MESIAL": "PLANEJADO", "OCLUSAL": "PLANEJADO"}


def test_planejado_vence_realizado_na_mesma_regiao(sessao, cenario):
    """O que esta por fazer nunca some atras do que ja foi feito."""
    clinica, usuario, paciente, restauracao, _ = cenario
    for status in (StatusLancamento.REALIZADO, StatusLancamento.PLANEJADO):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.REGIOES, dente=16, regioes=[Regiao.OCLUSAL], status=status,
        )
    sessao.flush()
    dente = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]["16"]
    assert dente["regioes"]["OCLUSAL"] == "PLANEJADO"


def test_escopo_boca_vai_para_a_lista_boca_nao_para_um_dente(sessao, cenario):
    clinica, usuario, paciente, _, consulta = cenario
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=consulta.id, escopo=Escopo.BOCA,
        status=StatusLancamento.REALIZADO,
    )
    sessao.flush()
    estado = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )
    assert len(estado["boca"]) == 1
    assert estado["boca"][0]["procedimento"] == "Consulta"
    assert all(not d["regioes"] for d in estado["dentes"].values())


def test_condicao_existente_aparece_no_dente(sessao, cenario):
    clinica, _, paciente, *_ = cenario
    odo = Odontograma(paciente_id=paciente.id, numero=1)
    sessao.add(odo)
    sessao.flush()
    sessao.add(
        Condicao(odontograma_id=odo.id, dente=26, tipo=TipoCondicao.OUTRO,
                 regioes=[], icone_legado="OICO14")
    )
    sessao.flush()
    dentes = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]
    assert dentes["26"]["condicoes"] == ["OICO14"]


def test_lancamento_excluido_some_do_estado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.OCLUSAL], status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    assert excluir_lancamento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, lancamento_id=lancamento.id
    )
    sessao.flush()
    dentes = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]
    assert dentes["16"]["regioes"] == {}


def test_exclusao_e_logica_o_registro_continua_no_banco(sessao, cenario):
    """Prontuario tem guarda minima de 10 anos. Nada e apagado de verdade."""
    clinica, usuario, paciente, restauracao, _ = cenario
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.DENTE, dente=16,
        status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    excluir_lancamento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, lancamento_id=lancamento.id
    )
    sessao.flush()
    guardado = sessao.get(Lancamento, lancamento.id)
    assert guardado is not None
    assert guardado.excluido_em is not None


# --- regras de escopo ----------------------------------------------------------

def test_escopo_boca_com_dente_e_recusado(sessao, cenario):
    clinica, usuario, paciente, _, consulta = cenario
    with pytest.raises(EscopoInvalido):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=consulta.id,
            escopo=Escopo.BOCA, dente=16, status=StatusLancamento.REALIZADO,
        )


def test_escopo_regioes_sem_regiao_e_recusado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    with pytest.raises(EscopoInvalido):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.REGIOES, dente=16, regioes=[],
            status=StatusLancamento.PLANEJADO,
        )


def test_dente_fora_da_notacao_fdi_e_recusado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    with pytest.raises(EscopoInvalido):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.DENTE, dente=19, status=StatusLancamento.PLANEJADO,
        )


def test_qualquer_tratamento_pode_ir_em_qualquer_regiao(sessao, cenario):
    """Nao ha validacao de compatibilidade: o historico real mostra o mesmo
    tratamento em escopos diferentes, e travar rejeitaria dados verdadeiros."""
    clinica, usuario, paciente, _, consulta = cenario
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=consulta.id, escopo=Escopo.REGIOES, dente=11,
        regioes=[Regiao.CANAL_CENTRAL], status=StatusLancamento.PLANEJADO,
    )
    assert lancamento.id is not None


# --- auditoria e API -----------------------------------------------------------

def test_todo_lancamento_deixa_rastro_na_auditoria(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.DENTE, dente=16,
        status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "lancamento")
    ).all()
    assert len(linhas) == 1
    assert linhas[0].acao == "CRIAR"
    assert linhas[0].usuario_id == usuario.id


def test_get_do_estado_devolve_json(cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.get(f"/api/odontograma/{paciente.id}")
    assert resposta.status_code == 200
    assert len(resposta.json()["dentes"]) == 32


def test_post_de_lancamento_grava_e_devolve_o_estado_novo(cliente, cenario):
    _, _, paciente, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/lancamento",
        json={
            "paciente_id": paciente.id,
            "procedimento_id": restauracao.id,
            "escopo": "REGIOES",
            "dente": 16,
            "regioes": ["MESIAL", "OCLUSAL"],
            "status": "PLANEJADO",
            "valor": "180.00",
        },
    )
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["estado"]["dentes"]["16"]["regioes"]["MESIAL"] == "PLANEJADO"
    assert corpo["lancamento_id"] > 0


def test_post_invalido_devolve_422_com_explicacao(cliente, cenario):
    _, _, paciente, _, consulta = cenario
    resposta = cliente.post(
        "/api/lancamento",
        json={
            "paciente_id": paciente.id, "procedimento_id": consulta.id,
            "escopo": "BOCA", "dente": 16, "regioes": [], "status": "REALIZADO",
        },
    )
    assert resposta.status_code == 422
    assert "dente" in resposta.json()["detail"].lower()


def test_api_sem_sessao_e_recusada(sessao, cenario):
    _, _, paciente, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get(f"/api/odontograma/{paciente.id}").status_code == 303


def test_paciente_de_outra_clinica_da_404(cliente, sessao, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add(alheio)
    sessao.flush()
    assert cliente.get(f"/api/odontograma/{alheio.id}").status_code == 404


def test_historico_vem_ordenado_do_mais_recente_para_o_mais_antigo(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    for dia in (10, 20, 15):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.DENTE, dente=16, status=StatusLancamento.REALIZADO,
            data=date(2026, 5, dia),
        )
    sessao.flush()
    datas = [
        item["data"] for item in historico(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    ]
    assert datas == sorted(datas, reverse=True)
