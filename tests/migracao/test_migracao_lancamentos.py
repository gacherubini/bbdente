import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.clinico.models import Lancamento, LancamentoRegiao, Odontograma
from app.pacientes.models import Paciente
from app.shared.dentes import TODOS_FDI
from app.shared.tipos import Escopo, StatusLancamento
from migracao.extrato import Extrato
from migracao.lancamentos import migrar

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture(scope="module")
def _aviso():
    """Esta migracao le 44.812 linhas: leva alguns segundos. E proposital que rode
    contra o volume real — e o unico jeito de saber que aguenta."""


@pytest.fixture
def migrado(sessao):
    from migracao.catalogo import migrar as migrar_catalogo
    from migracao.pacientes import migrar as migrar_pacientes

    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        migrar_catalogo(sessao, extrato, clinica.id)
        migrar_pacientes(sessao, extrato, clinica.id)
        resultado = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica, resultado


def test_traz_os_44812_lancamentos(sessao, migrado):
    _, resultado = migrado
    assert resultado.lancamentos == 44_812
    assert sessao.query(Lancamento).count() == 44_812


def test_traz_exatamente_29350_regioes(sessao, migrado):
    """Cada POSDENTE e uma unica celula da grade, entao e exatamente uma regiao por
    lancamento migrado com escopo REGIOES."""
    _, resultado = migrado
    assert resultado.regioes == 29_350
    assert sessao.query(LancamentoRegiao).count() == 29_350


def test_a_soma_dos_valores_bate_ao_centavo(sessao, migrado):
    total = sessao.query(func.coalesce(func.sum(Lancamento.valor), 0)).scalar()
    assert Decimal(total) == Decimal("3461389.07")


def test_distribuicao_por_escopo(sessao, migrado):
    contagem = dict(
        sessao.query(Lancamento.escopo, func.count()).group_by(Lancamento.escopo).all()
    )
    assert contagem[Escopo.REGIOES] == 29_350
    assert contagem[Escopo.BOCA] == 7_638
    assert contagem[Escopo.DENTE] == 7_824


def test_distribuicao_por_status(sessao, migrado):
    contagem = dict(
        sessao.query(Lancamento.status, func.count()).group_by(Lancamento.status).all()
    )
    assert contagem[StatusLancamento.REALIZADO] == 37_034
    assert contagem[StatusLancamento.PLANEJADO] == 7_764 + 14  # 'E' + os 14 'J'


def test_todo_dente_gravado_e_fdi_valido(sessao, migrado):
    dentes = {
        d for (d,) in sessao.query(Lancamento.dente).distinct() if d is not None
    }
    assert dentes <= set(TODOS_FDI)


def test_boca_nao_tem_dente_e_o_resto_tem(sessao, migrado):
    assert (
        sessao.query(Lancamento)
        .filter(Lancamento.escopo == Escopo.BOCA, Lancamento.dente.isnot(None))
        .count()
        == 0
    )
    assert (
        sessao.query(Lancamento)
        .filter(Lancamento.escopo != Escopo.BOCA, Lancamento.dente.is_(None))
        .count()
        == 0
    )


def test_regiao_so_existe_quando_o_escopo_e_regioes(sessao, migrado):
    fora = (
        sessao.query(LancamentoRegiao)
        .join(Lancamento, LancamentoRegiao.lancamento_id == Lancamento.id)
        .filter(Lancamento.escopo != Escopo.REGIOES)
        .count()
    )
    assert fora == 0


def test_nenhum_lancamento_orfao(sessao, migrado):
    total = sessao.query(Lancamento).count()
    ligados = (
        sessao.query(Lancamento)
        .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
        .join(Paciente, Odontograma.paciente_id == Paciente.id)
        .count()
    )
    assert ligados == total


def test_os_39_registros_contraditorios_entram_marcados(sessao, migrado):
    """POSDENTE dizia 'boca toda' mas o dente estava preenchido."""
    marcados = sessao.scalars(
        select(Lancamento).where(
            Lancamento.revisar_motivo.any("boca_com_dente_preenchido")
        )
    ).all()
    assert len(marcados) == 39
    assert all(m.escopo is Escopo.BOCA and m.dente is None for m in marcados)


def test_o_unico_posdente_corrompido_entra_como_dente_inteiro_marcado(sessao, migrado):
    marcados = sessao.scalars(
        select(Lancamento).where(Lancamento.revisar_motivo.any("posdente_ilegivel"))
    ).all()
    assert len(marcados) == 1
    assert marcados[0].escopo is Escopo.DENTE
    assert marcados[0].dente is not None


def test_os_dois_codserv_desconhecidos_viram_procedimento_marcado(sessao, migrado):
    """CODSERV 'P1' e 'P4' nao existem em nenhuma tabela de preco. Criamos um
    procedimento visivelmente provisorio em vez de descartar o lancamento."""
    from app.catalogo.models import Procedimento

    desconhecidos = sessao.scalars(
        select(Procedimento).where(Procedimento.nome.like("DESCONHECIDO%"))
    ).all()
    assert {p.codigo for p in desconhecidos} == {"P1", "P4"}


def test_multiplos_odontogramas_por_paciente_sao_preservados(sessao, migrado):
    """NUMODO no Dentalis vai de 1 a 5."""
    numeros = {n for (n,) in sessao.query(Odontograma.numero).distinct()}
    assert numeros >= {1, 2}
    com_varios = (
        sessao.query(Odontograma.paciente_id)
        .group_by(Odontograma.paciente_id)
        .having(func.count() > 1)
        .count()
    )
    assert com_varios > 0


def test_rodar_duas_vezes_nao_duplica(sessao, migrado):
    clinica, _ = migrado
    with Extrato(EXTRATO) as extrato:
        migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert sessao.query(Lancamento).count() == 44_812
    assert sessao.query(LancamentoRegiao).count() == 29_350
