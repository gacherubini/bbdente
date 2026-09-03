"""Excluir um cadastro de paciente.

Existe por um motivo concreto: o banco de producao ficou com quatro cadastros da
MESMA pessoa. A tela dava `Internal Server Error` no redirect depois de gravar, a
recepcao achava que nao tinha salvo e cadastrava de novo. Sem uma forma de
excluir, a duplicata fica na lista para sempre.

Tres regras nascem aqui:

- **Excluir e logico, como todo o resto** (`excluido_em`). Regra 1 do AGENTS.md:
  guarda minima de 10 anos do CFO, dado de saude e dado sensivel da LGPD.
- **O nome nao some do historico.** `nomes_de` e `contatos_de` continuam
  devolvendo quem era, porque a lista de cobranca e a agenda de tres anos atras
  nao podem virar linhas anonimas por causa de uma exclusao de hoje.
- **Horario futuro cai junto.** Cadastro excluido que continua ocupando vaga na
  grade — e recebendo lembrete no WhatsApp — e pior que nao ter excluido.
  O passado fica: aquilo aconteceu.
"""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agenda import service as agenda
from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.clinico.models import Lancamento, Odontograma
from app.financeiro.models import Parcela
from app.main import criar_app
from app.pacientes import service
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, StatusLancamento

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
SEMANA_QUE_VEM = HOJE + timedelta(days=7)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    convenio = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    categoria = Categoria(
        clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4
    )
    sessao.add_all([convenio, categoria])
    sessao.flush()
    procedimento = Procedimento(
        clinica_id=clinica.id,
        codigo="21",
        nome="Restauracao",
        categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE,
        regioes_sugeridas=[],
    )
    sessao.add(procedimento)
    sessao.flush()

    # As duas AVANI do caso real: a boa e a duplicata criada pelo retry.
    boa = service.criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="AVANI GURSKI",
        telefone="51999990001",
        nascimento=date(1953, 4, 10),
    )
    duplicata = service.criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="AVANI GURSKI",
        nascimento=date(1953, 4, 10),
    )
    sessao.flush()
    return clinica, usuario, boa, duplicata, procedimento


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        yield c


# --------------------------------------------------------------------------
# A service


def test_excluir_marca_a_data_e_tira_da_lista(sessao, cenario):
    clinica, usuario, _, duplicata, _ = cenario

    service.excluir(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=duplicata.id,
    )
    sessao.flush()

    assert duplicata.excluido_em is not None
    assert service.obter(
        sessao, clinica_id=clinica.id, paciente_id=duplicata.id
    ) is None
    achados = service.buscar(sessao, clinica_id=clinica.id, termo="AVANI")
    assert duplicata.id not in {linha.id for linha in achados}


def test_a_linha_continua_no_banco(sessao, cenario):
    """Exclusao logica: a linha fica, so para de aparecer."""
    clinica, usuario, _, duplicata, _ = cenario
    paciente_id = duplicata.id

    service.excluir(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente_id
    )
    sessao.flush()

    ainda_la = sessao.get(Paciente, paciente_id)
    assert ainda_la is not None
    assert ainda_la.nome == "AVANI GURSKI"


def test_excluir_nao_derruba_a_contagem_do_cabecalho(sessao, cenario):
    clinica, usuario, _, duplicata, _ = cenario
    antes = service.contagens(sessao, clinica_id=clinica.id)["total"]

    service.excluir(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=duplicata.id,
    )
    sessao.flush()

    assert service.contagens(sessao, clinica_id=clinica.id)["total"] == antes - 1


def test_excluir_grava_auditoria_com_o_retrato_de_antes(sessao, cenario):
    clinica, usuario, _, duplicata, _ = cenario

    service.excluir(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=duplicata.id,
    )
    sessao.flush()

    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "paciente",
            Auditoria.entidade_id == duplicata.id,
            Auditoria.acao == "EXCLUIR",
        )
    ).one()
    assert linha.usuario_id == usuario.id
    assert linha.dados_antes["nome"] == "AVANI GURSKI"


def test_paciente_de_outra_clinica_nao_e_excluido(sessao, cenario):
    clinica, usuario, _, duplicata, _ = cenario
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()

    with pytest.raises(LookupError):
        service.excluir(
            sessao,
            clinica_id=outra.id,
            usuario_id=usuario.id,
            paciente_id=duplicata.id,
        )


def test_excluir_duas_vezes_nao_reescreve_a_data(sessao, cenario):
    clinica, usuario, _, duplicata, _ = cenario
    service.excluir(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=duplicata.id
    )
    sessao.flush()

    with pytest.raises(LookupError):
        service.excluir(
            sessao,
            clinica_id=clinica.id,
            usuario_id=usuario.id,
            paciente_id=duplicata.id,
        )


def test_o_nome_continua_disponivel_para_o_historico(sessao, cenario):
    """A cobranca de 2019 e o cartao da agenda de tres anos atras nao viram
    linha anonima porque alguem excluiu o cadastro hoje."""
    clinica, usuario, _, duplicata, _ = cenario

    service.excluir(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=duplicata.id
    )
    sessao.flush()

    nomes = service.nomes_de(
        sessao, clinica_id=clinica.id, paciente_ids=[duplicata.id]
    )
    assert nomes[duplicata.id] == "AVANI GURSKI"
    contatos = service.contatos_de(
        sessao, clinica_id=clinica.id, paciente_ids=[duplicata.id]
    )
    assert contatos[duplicata.id].nome == "AVANI GURSKI"


# --------------------------------------------------------------------------
# Os vinculos, que alimentam o aviso


def test_ficha_limpa_nao_tem_vinculo(sessao, cenario):
    clinica, _, _, duplicata, _ = cenario
    vinculos = service.vinculos_de(
        sessao, clinica_id=clinica.id, paciente_id=duplicata.id
    )
    assert vinculos.tratamentos == 0
    assert vinculos.agendamentos == 0
    assert vinculos.parcelas_em_aberto == 0
    assert not vinculos.tem_historico


def test_vinculos_contam_tratamento_agendamento_e_divida(sessao, cenario):
    clinica, usuario, boa, _, procedimento = cenario

    odontograma = Odontograma(paciente_id=boa.id, numero=1)
    sessao.add(odontograma)
    sessao.flush()
    sessao.add(
        Lancamento(
            clinica_id=clinica.id,
            odontograma_id=odontograma.id,
            dente=11,
            escopo=Escopo.DENTE,
            procedimento_id=procedimento.id,
            status=StatusLancamento.REALIZADO,
            data_realizada=ONTEM,
            valor=Decimal("150.00"),
        )
    )
    agenda.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        dia=SEMANA_QUE_VEM,
        inicio=time(14, 0),
        paciente_id=boa.id,
    )
    sessao.add(
        Parcela(
            clinica_id=clinica.id,
            paciente_id=boa.id,
            vencimento=ONTEM,
            valor_cobrado=Decimal("150.00"),
            valor_pago=Decimal("0.00"),
        )
    )
    sessao.flush()

    vinculos = service.vinculos_de(
        sessao, clinica_id=clinica.id, paciente_id=boa.id
    )
    assert vinculos.tratamentos == 1
    assert vinculos.agendamentos == 1
    assert vinculos.parcelas_em_aberto == 1
    assert vinculos.tem_historico


def test_parcela_quitada_nao_conta_como_divida(sessao, cenario):
    clinica, _, boa, _, _ = cenario
    sessao.add(
        Parcela(
            clinica_id=clinica.id,
            paciente_id=boa.id,
            vencimento=ONTEM,
            valor_cobrado=Decimal("150.00"),
            valor_pago=Decimal("150.00"),
            pago_em=ONTEM,
        )
    )
    sessao.flush()

    vinculos = service.vinculos_de(
        sessao, clinica_id=clinica.id, paciente_id=boa.id
    )
    assert vinculos.parcelas_em_aberto == 0


# --------------------------------------------------------------------------
# A tela


def test_a_tela_de_confirmacao_mostra_os_numeros(sessao, cliente, cenario):
    clinica, usuario, boa, _, procedimento = cenario
    odontograma = Odontograma(paciente_id=boa.id, numero=1)
    sessao.add(odontograma)
    sessao.flush()
    sessao.add(
        Lancamento(
            clinica_id=clinica.id,
            odontograma_id=odontograma.id,
            dente=11,
            escopo=Escopo.DENTE,
            procedimento_id=procedimento.id,
            status=StatusLancamento.REALIZADO,
            data_realizada=ONTEM,
            valor=Decimal("150.00"),
        )
    )
    sessao.flush()

    resposta = cliente.get(f"/pacientes/{boa.id}/excluir")

    assert resposta.status_code == 200
    assert "AVANI GURSKI" in resposta.text
    assert "1 tratamento" in resposta.text


def test_a_tela_de_confirmacao_nao_exclui_nada(sessao, cliente, cenario):
    _, _, _, duplicata, _ = cenario
    cliente.get(f"/pacientes/{duplicata.id}/excluir")
    assert duplicata.excluido_em is None


def test_o_post_exclui_e_volta_para_a_lista(sessao, cliente, cenario):
    _, _, _, duplicata, _ = cenario

    resposta = cliente.post(f"/pacientes/{duplicata.id}/excluir")

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes"
    assert duplicata.excluido_em is not None


def test_o_post_derruba_o_horario_futuro(sessao, cliente, cenario):
    """Cadastro excluido nao pode continuar ocupando vaga nem recebendo lembrete."""
    clinica, usuario, _, duplicata, _ = cenario
    futuro = agenda.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        dia=SEMANA_QUE_VEM,
        inicio=time(9, 0),
        paciente_id=duplicata.id,
    )
    sessao.flush()

    cliente.post(f"/pacientes/{duplicata.id}/excluir")

    assert futuro.excluido_em is not None


def test_o_post_preserva_o_horario_passado(sessao, cliente, cenario):
    """Aquilo aconteceu — o passado da agenda e historico, nao vaga ocupada."""
    clinica, usuario, _, duplicata, _ = cenario
    passado = agenda.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        dia=ONTEM,
        inicio=time(9, 0),
        paciente_id=duplicata.id,
    )
    sessao.flush()

    cliente.post(f"/pacientes/{duplicata.id}/excluir")

    assert passado.excluido_em is None


def test_excluido_some_da_lista_de_pacientes(sessao, cliente, cenario):
    _, _, _, duplicata, _ = cenario
    cliente.post(f"/pacientes/{duplicata.id}/excluir")
    sessao.flush()

    resposta = cliente.get("/pacientes?q=AVANI")

    assert resposta.status_code == 200
    assert resposta.text.count(f"/odontograma/{duplicata.id}") == 0


def test_excluir_paciente_que_nao_existe_da_404(cliente):
    assert cliente.post("/pacientes/999999/excluir").status_code == 404
    assert cliente.get("/pacientes/999999/excluir").status_code == 404


def test_a_grade_da_semana_nao_quebra_com_paciente_excluido(sessao, cliente, cenario):
    """O cartao do passado continua com nome, nao vira linha em branco."""
    clinica, usuario, _, duplicata, _ = cenario
    agenda.marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        dia=ONTEM,
        inicio=time(9, 0),
        paciente_id=duplicata.id,
    )
    sessao.flush()
    cliente.post(f"/pacientes/{duplicata.id}/excluir")
    sessao.flush()

    grade = agenda.grade(
        sessao,
        clinica_id=clinica.id,
        periodo=agenda.semana_de(ONTEM),
    )
    cartoes = [c for dia in grade.cartoes.values() for c in dia]
    assert [c.nome for c in cartoes] == ["AVANI GURSKI"]
