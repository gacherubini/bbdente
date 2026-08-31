"""Editar um lancamento ja feito — inclusive o alvo dele.

Ate 31/08/2026 esta edicao mexia so em valor, situacao, data e observacao: dente,
regiao e procedimento estavam de fora porque "trocar o alvo nao e correcao, e
outro tratamento". Na pratica corrigir um dente errado custava excluir e lancar
de novo, e quem estava com a paciente na cadeira nao fazia isso — ficava com o
dado errado na tela. A decisao caiu; a auditoria continua guardando os dois lados,
que era o que ela protegia.

O alvo anda junto: quem manda `escopo` esta trocando o alvo inteiro (procedimento,
dente e faces). Quem nao manda `escopo` esta corrigindo so o resto, e o alvo fica
como estava — e por isso a linha do historico pode continuar salvando so o valor.

E a data e uma so por vez: um lancamento planejado tem data planejada, um
realizado tem data realizada. Guardar as duas seria guardar uma contradicao.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Lancamento, LancamentoRegiao
from app.clinico.service import excluir_lancamento, lancar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento


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
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([restauracao, paciente])
    sessao.flush()
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL], status=StatusLancamento.PLANEJADO,
        data=date(2026, 5, 10), valor=Decimal("180.00"),
    )
    sessao.flush()
    return clinica, usuario, paciente, restauracao, lancamento


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        yield c


def corpo(**extra) -> dict:
    dados = {"status": "PLANEJADO", "valor": "180.00", "data": "2026-05-10"}
    dados.update(extra)
    return dados


def alvo(**extra) -> dict:
    """O corpo que o painel manda quando esta corrigindo o alvo inteiro."""
    dados = corpo(escopo="REGIOES", dente=16, regioes=["MESIAL"])
    dados.update(extra)
    return dados


def regioes_de(sessao, lancamento) -> set:
    return set(
        sessao.scalars(
            select(LancamentoRegiao.regiao).where(
                LancamentoRegiao.lancamento_id == lancamento.id
            )
        ).all()
    )


def outro_procedimento(sessao, clinica_id: int, nome: str = "Endodontia") -> Procedimento:
    categoria = sessao.scalars(
        select(Categoria).where(Categoria.clinica_id == clinica_id)
    ).first()
    procedimento = Procedimento(
        clinica_id=clinica_id, codigo="99", nome=nome, categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(procedimento)
    sessao.flush()
    return procedimento


# --- editar --------------------------------------------------------------------


def test_editar_o_valor_grava_e_devolve_o_estado_novo(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00")
    )
    assert resposta.status_code == 200
    assert resposta.json()["estado"]["dentes"]["16"]["regioes"]["MESIAL"] == "PLANEJADO"
    sessao.refresh(lancamento)
    assert lancamento.valor == Decimal("250.00")


def test_a_edicao_deixa_antes_e_depois_na_auditoria(sessao, cliente, cenario):
    _, usuario, _, _, lancamento = cenario
    cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00"))
    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "lancamento", Auditoria.acao == "ATUALIZAR"
        )
    ).one()
    assert linha.dados_antes["valor"] == "180.00"
    assert linha.dados_depois["valor"] == "250.00"
    assert linha.usuario_id == usuario.id


def test_editar_a_observacao_funciona(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=corpo(observacao="paciente pediu para adiar"),
    )
    sessao.refresh(lancamento)
    assert lancamento.observacao == "paciente pediu para adiar"


# --- a data segue a situacao ---------------------------------------------------


def test_virar_realizado_move_a_data_de_planejada_para_realizada(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    assert lancamento.data_planejada == date(2026, 5, 10)

    cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=corpo(status="REALIZADO", data="2026-05-12"),
    )
    sessao.refresh(lancamento)
    assert lancamento.status is StatusLancamento.REALIZADO
    assert lancamento.data_realizada == date(2026, 5, 12)
    assert lancamento.data_planejada is None


def test_voltar_para_planejado_devolve_a_data(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(status="REALIZADO", data="2026-05-12")
    )
    cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(status="PLANEJADO", data="2026-06-01")
    )
    sessao.refresh(lancamento)
    assert lancamento.status is StatusLancamento.PLANEJADO
    assert lancamento.data_planejada == date(2026, 6, 1)
    assert lancamento.data_realizada is None


def test_lancamento_pode_ficar_sem_data(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(data=None))
    sessao.refresh(lancamento)
    assert lancamento.data_planejada is None
    assert lancamento.data_realizada is None


def test_virar_realizado_muda_a_cor_no_desenho(cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(status="REALIZADO")
    )
    dente = resposta.json()["estado"]["dentes"]["16"]
    assert dente["regioes"]["MESIAL"] == "REALIZADO"


# --- o que a edicao recusa -----------------------------------------------------


def test_valor_negativo_e_recusado(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="-10"))
    assert resposta.status_code == 422
    sessao.refresh(lancamento)
    assert lancamento.valor == Decimal("180.00")


def test_data_invalida_e_recusada(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(data="30/02/2026")
    )
    assert resposta.status_code == 422


def test_lancamento_excluido_nao_pode_ser_editado(sessao, cliente, cenario):
    """Editar o que foi apagado seria ressuscitar sem deixar claro que ressuscitou."""
    clinica, usuario, _, _, lancamento = cenario
    excluir_lancamento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, lancamento_id=lancamento.id
    )
    sessao.flush()
    resposta = cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="250"))
    assert resposta.status_code == 404


def test_lancamento_inexistente_da_404(cliente):
    assert cliente.patch("/api/lancamento/999999", json=corpo()).status_code == 404


def test_lancamento_de_outra_clinica_da_404(sessao, cliente, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    usuario_alheio = criar_usuario(
        sessao, clinica_id=outra.id, email="x@e.com", senha="senha-longa", nome="X"
    )
    categoria = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=outra.id, codigo="21", nome="Alheio", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add_all([procedimento, paciente])
    sessao.flush()
    alheio = lancar(
        sessao, clinica_id=outra.id, usuario_id=usuario_alheio.id,
        paciente_id=paciente.id, procedimento_id=procedimento.id,
        escopo=Escopo.DENTE, dente=16, status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    resposta = cliente.patch(f"/api/lancamento/{alheio.id}", json=corpo(valor="250"))
    assert resposta.status_code == 404
    sessao.refresh(alheio)
    assert alheio.valor == Decimal("0.00")


def test_sem_escopo_o_alvo_fica_como_estava(sessao, cliente, cenario):
    """A linha do historico salva so valor e data; ela nao pode mover o dente."""
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00", dente=26)
    )
    assert resposta.status_code == 200
    sessao.refresh(lancamento)
    assert lancamento.dente == 16
    assert lancamento.escopo is Escopo.REGIOES
    assert regioes_de(sessao, lancamento) == {Regiao.MESIAL}


def test_sem_sessao_e_recusada(sessao, cenario):
    _, _, _, _, lancamento = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        resposta = anonimo.patch(f"/api/lancamento/{lancamento.id}", json=corpo())
        assert resposta.status_code == 303


# --- a tela --------------------------------------------------------------------


def test_o_historico_do_odontograma_traz_o_id_de_cada_lancamento(cliente, cenario):
    """Sem o id na linha, o JavaScript nao tem como dizer qual editar."""
    _, _, paciente, _, lancamento = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert f'data-lancamento="{lancamento.id}"' in html


def test_o_historico_e_editavel_na_tela_do_paciente(cliente, cenario):
    _, _, paciente, *_ = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert "editar" in html.lower()


def test_o_lancamento_guardado_continua_no_banco_apos_editar(sessao, cliente, cenario):
    """Editar troca o valor da linha; nunca cria uma segunda nem apaga a primeira."""
    _, _, _, _, lancamento = cenario
    cliente.patch(f"/api/lancamento/{lancamento.id}", json=corpo(valor="250.00"))
    todos = sessao.scalars(select(Lancamento)).all()
    assert len(todos) == 1
    assert todos[0].id == lancamento.id


# --- trocar o alvo: dente, faces e tratamento ----------------------------------


def test_trocar_o_dente_move_o_desenho_inteiro(sessao, cliente, cenario):
    """O 16 fica limpo e o 26 acende: e uma correcao, nao um segundo tratamento."""
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(dente=26, regioes=["DISTAL"])
    )
    assert resposta.status_code == 200
    dentes = resposta.json()["estado"]["dentes"]
    assert dentes["26"]["regioes"]["DISTAL"] == "PLANEJADO"
    assert dentes["16"]["regioes"] == {}
    sessao.refresh(lancamento)
    assert lancamento.dente == 26


def test_trocar_as_faces_reescreve_as_regioes(sessao, cliente, cenario):
    """As faces velhas somem: sobram exatamente as que ela deixou marcadas."""
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=alvo(regioes=["DISTAL", "VESTIBULAR"]),
    )
    sessao.refresh(lancamento)
    assert regioes_de(sessao, lancamento) == {Regiao.DISTAL, Regiao.VESTIBULAR}


def test_trocar_o_tratamento_troca_o_nome_no_historico(sessao, cliente, cenario):
    clinica, _, paciente, _, lancamento = cenario
    endodontia = outro_procedimento(sessao, clinica.id)
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(procedimento_id=endodontia.id)
    )
    assert resposta.status_code == 200
    sessao.refresh(lancamento)
    assert lancamento.procedimento_id == endodontia.id
    assert "Endodontia" in cliente.get(f"/odontograma/{paciente.id}").text


def test_virar_boca_toda_larga_o_dente_e_as_faces(sessao, cliente, cenario):
    """O banco tem CHECK: escopo BOCA exige dente nulo. As faces vao junto."""
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=alvo(escopo="BOCA", dente=None, regioes=[]),
    )
    assert resposta.status_code == 200
    sessao.refresh(lancamento)
    assert lancamento.escopo is Escopo.BOCA
    assert lancamento.dente is None
    assert regioes_de(sessao, lancamento) == set()


def test_virar_dente_inteiro_larga_as_faces(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(escopo="DENTE", regioes=[])
    )
    assert resposta.status_code == 200
    sessao.refresh(lancamento)
    assert regioes_de(sessao, lancamento) == set()
    assert resposta.json()["estado"]["dentes"]["16"]["dente_inteiro"] == "PLANEJADO"


def test_o_alvo_antigo_e_o_novo_ficam_na_auditoria(sessao, cliente, cenario):
    """E o que sobra de prova de que o 16 mesial um dia foi lancado."""
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(dente=26, regioes=["DISTAL"])
    )
    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "lancamento", Auditoria.acao == "ATUALIZAR"
        )
    ).one()
    assert linha.dados_antes["dente"] == 16
    assert linha.dados_antes["regioes"] == ["MESIAL"]
    assert linha.dados_depois["dente"] == 26
    assert linha.dados_depois["regioes"] == ["DISTAL"]


# --- o que a troca de alvo recusa ----------------------------------------------


def test_tratamento_de_outra_clinica_e_recusado(sessao, cliente, cenario):
    """Mesma regua do lancar: nao da para puxar procedimento de outra clinica."""
    _, _, _, _, lancamento = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    categoria = Categoria(clinica_id=outra.id, codigo="04", nome="X", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    alheio = Procedimento(
        clinica_id=outra.id, codigo="21", nome="Alheio", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(alheio)
    sessao.flush()

    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(procedimento_id=alheio.id)
    )
    assert resposta.status_code == 404
    sessao.refresh(lancamento)
    assert lancamento.procedimento_id != alheio.id


def test_regioes_sem_nenhuma_face_e_recusado(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(regioes=[])
    )
    assert resposta.status_code == 422
    sessao.refresh(lancamento)
    assert regioes_de(sessao, lancamento) == {Regiao.MESIAL}


def test_dente_que_nao_existe_e_recusado(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(f"/api/lancamento/{lancamento.id}", json=alvo(dente=99))
    assert resposta.status_code == 422
    sessao.refresh(lancamento)
    assert lancamento.dente == 16


def test_boca_toda_com_dente_e_recusado(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    resposta = cliente.patch(
        f"/api/lancamento/{lancamento.id}",
        json=alvo(escopo="BOCA", dente=16, regioes=[]),
    )
    assert resposta.status_code == 422


def test_a_troca_de_alvo_nao_cria_um_segundo_lancamento(sessao, cliente, cenario):
    _, _, _, _, lancamento = cenario
    cliente.patch(
        f"/api/lancamento/{lancamento.id}", json=alvo(dente=26, regioes=["DISTAL"])
    )
    todos = sessao.scalars(select(Lancamento)).all()
    assert len(todos) == 1
    assert todos[0].id == lancamento.id


# --- a linha do historico leva o alvo para o painel ----------------------------


def test_a_linha_do_historico_carrega_o_alvo_para_o_painel(cliente, cenario):
    """Sem isso o painel nao tem como abrir ja preenchido com o que esta gravado."""
    _, _, paciente, restauracao, _ = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert f'data-procedimento-id="{restauracao.id}"' in html
    assert 'data-escopo="REGIOES"' in html
    assert 'data-regioes="MESIAL"' in html
    assert 'data-dente="16"' in html


def test_o_historico_tem_como_excluir_a_linha(cliente, cenario):
    """O `x` existia so na tela do dia; quem esta no odontograma tambem precisa."""
    _, _, paciente, *_ = cenario
    html = cliente.get(f"/odontograma/{paciente.id}").text
    assert "excluir-lancamento" in html
