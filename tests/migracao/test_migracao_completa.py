import os

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.clinico.models import (
    Condicao,
    Lancamento,
    LancamentoRegiao,
    ObservacaoClinica,
    Odontograma,
    PerguntaAnamnese,
    RespostaAnamnese,
)
from app.pacientes.models import Paciente
from app.shared.dentes import TODOS_FDI
from app.shared.tipos import TipoCondicao
from migracao.conferencia import ConferenciaFalhou, conferir
from migracao.extrato import Extrato

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture
def tudo_migrado(sessao):
    from migracao import anamnese, catalogo, condicoes, lancamentos, pacientes

    clinica = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        catalogo.migrar(sessao, extrato, clinica.id)
        pacientes.migrar(sessao, extrato, clinica.id)
        lancamentos.migrar(sessao, extrato, clinica.id)
        condicoes.migrar(sessao, extrato, clinica.id)
        anamnese.migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica


def test_traz_as_9629_condicoes(sessao, tudo_migrado):
    assert sessao.query(Condicao).count() == 9_629


def test_condicao_guarda_o_codigo_de_icone_original(sessao, tudo_migrado):
    """Os 309 codigos nao foram traduzidos ainda — precisam da Dra. Katia. Ate la,
    entram como OUTRO com o codigo preservado."""
    sem_icone = sessao.query(Condicao).filter(Condicao.icone_legado.is_(None)).count()
    assert sem_icone == 0
    assert sessao.query(Condicao).filter_by(tipo=TipoCondicao.OUTRO).count() == 9_629
    top = (
        sessao.query(Condicao.icone_legado, func.count())
        .group_by(Condicao.icone_legado)
        .order_by(func.count().desc())
        .first()
    )
    assert top[0] == "OICO14"
    assert top[1] == 2_859


def test_condicao_com_dente_sentinela_nao_vira_dente_invalido(sessao, tudo_migrado):
    """ARQICONE tem NUMDENTE ate '88'. De 81 para cima nao e dente: a condicao
    entra sem dente, nunca com um numero fora da notacao FDI."""
    dentes = {d for (d,) in sessao.query(Condicao.dente).distinct()}
    assert dentes - {None} <= set(TODOS_FDI)
    sem_dente = sessao.query(Condicao).filter(Condicao.dente.is_(None)).count()
    assert sem_dente == 5_522


def test_traz_as_37_perguntas_e_2046_respostas(sessao, tudo_migrado):
    assert sessao.query(PerguntaAnamnese).count() == 37
    assert sessao.query(RespostaAnamnese).count() == 2_046


def test_traz_as_80_observacoes_com_texto(sessao, tudo_migrado):
    assert sessao.query(ObservacaoClinica).count() == 80


def test_a_conferencia_aprova_a_migracao_completa(sessao, tudo_migrado):
    assert conferir(sessao, tudo_migrado.id) == []


def test_a_conferencia_reprova_quando_falta_registro(sessao, tudo_migrado):
    """Este teste e o motivo de a conferencia existir: ela tem de gritar."""
    algum = sessao.scalars(select(Paciente).limit(1)).one()
    sessao.query(LancamentoRegiao).filter(
        LancamentoRegiao.lancamento_id.in_(
            select(Lancamento.id)
            .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
            .where(Odontograma.paciente_id == algum.id)
        )
    ).delete(synchronize_session=False)
    sessao.flush()

    divergencias = conferir(sessao, tudo_migrado.id)
    assert divergencias
    assert any("lancamento_regiao" in d for d in divergencias)


def test_conferencia_falhou_e_uma_excecao_com_a_lista_dentro():
    erro = ConferenciaFalhou(["paciente: esperado 5561, encontrado 5560"])
    assert erro.divergencias == ["paciente: esperado 5561, encontrado 5560"]
    assert "5560" in str(erro)


def test_a_anamnese_de_quem_so_existe_no_orcamento_nao_se_perde(sessao, tudo_migrado):
    """As 22 respostas de '1104/OR' (LAUTILDA) apontam para um cadastro que so
    existe no ARQORCAM, nunca virou paciente. Resposta de anamnese e dado de saude:
    junta-la a outra pessoa seria pior do que criar o cadastro que faltava."""
    lautilda = sessao.scalars(
        select(Paciente).where(Paciente.codigo_legado == "1104/OR")
    ).one()
    assert "cadastro_so_no_orcamento" in lautilda.revisar_motivo
    respostas = (
        sessao.query(RespostaAnamnese).filter_by(paciente_id=lautilda.id).count()
    )
    assert respostas == 22
