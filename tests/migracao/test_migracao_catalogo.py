import os

import pytest

from app.auth.models import Clinica
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.shared.tipos import Escopo, Regiao
from migracao.catalogo import migrar
from migracao.extrato import Extrato

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO),
    reason=f"extrato nao disponivel em {EXTRATO} (nunca e versionado — dado de paciente)",
)


@pytest.fixture
def clinica(sessao):
    c = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(c)
    sessao.flush()
    return c


@pytest.fixture
def migrado(sessao, clinica):
    with Extrato(EXTRATO) as extrato:
        resultado = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return resultado


def test_traz_as_12_categorias_reais(sessao, migrado, clinica):
    """ARQESPE tem 13 linhas, mas a '00 Todas as Intervencoes' e um filtro de tela,
    nao uma categoria."""
    assert migrado.categorias == 12
    nomes = {c.nome for c in sessao.query(Categoria).filter_by(clinica_id=clinica.id)}
    assert "Dentística" in nomes
    assert "Endodontia" in nomes
    assert not any(n.startswith("Todas") for n in nomes)


def test_traz_os_7_convenios(sessao, migrado):
    assert migrado.convenios == 7
    codigos = {c.codigo for c in sessao.query(Convenio)}
    assert codigos == {"001", "002", "003", "004", "005", "006", "051"}
    particular = sessao.query(Convenio).filter_by(codigo="001").one()
    assert particular.nome == "PARTICULAR"


def test_convenio_sem_nome_no_legado_ganha_rotulo_do_codigo(sessao, migrado):
    """003 a 006 nao tem nome em TABELAS. Inventar um nome seria mentir; usamos o
    codigo, visivelmente provisorio."""
    assert sessao.query(Convenio).filter_by(codigo="004").one().nome == "Convenio 004"


def test_traz_os_476_procedimentos_distintos_e_606_precos(sessao, migrado):
    """A V_PROCEDIMENTO tem 612 linhas, mas 6 sao o titulo da tabela de preco
    gravado como servico CODSERV '00' ("TABELA DE ORTO", "UNIODONTO"...). Nenhuma
    delas aparece em lancamento; nao sao procedimentos."""
    assert migrado.procedimentos == 476
    assert migrado.precos == 606


def test_todo_procedimento_tem_categoria(sessao, migrado):
    assert sessao.query(Procedimento).filter_by(categoria_id=None).count() == 0


def test_todo_preco_aponta_para_procedimento_e_convenio_existentes(sessao, migrado):
    total = sessao.query(Preco).count()
    validos = (
        sessao.query(Preco)
        .join(Procedimento, Preco.procedimento_id == Procedimento.id)
        .join(Convenio, Preco.convenio_id == Convenio.id)
        .count()
    )
    assert validos == total == 606


def test_escopo_sugerido_vem_do_habito_real_dela(sessao, migrado):
    """Restauracao classe II e feita em parede; consulta e na boca toda. Nao e
    opiniao de quem programou: e a maioria das 44.812 ocorrencias."""
    por_nome = {
        p.nome.upper(): p for p in sessao.query(Procedimento).all()
    }
    # O nome no catalogo dela junta as classes: "RESTAURACAO RESINA FOTOATIVADA
    # CLASSE II E III". E o procedimento de restauracao em parede.
    restauracao = next(p for n, p in por_nome.items() if "CLASSE II" in n)
    assert restauracao.escopo_sugerido is Escopo.REGIOES
    assert set(restauracao.regioes_sugeridas) <= set(Regiao)
    assert restauracao.regioes_sugeridas  # nao vazio

    consulta = next(p for n, p in por_nome.items() if n.startswith("CONSULTA"))
    assert consulta.escopo_sugerido is Escopo.BOCA
    assert consulta.regioes_sugeridas == []


def test_procedimento_sem_uso_no_historico_recebe_escopo_padrao(sessao, migrado):
    """477 procedimentos no catalogo, so 177 aparecem em lancamentos. Os outros nao
    tem habito para copiar — ficam em DENTE, o meio-termo."""
    sem_regioes = sessao.query(Procedimento).filter(
        Procedimento.escopo_sugerido == Escopo.DENTE
    ).count()
    assert sem_regioes > 0


def test_rodar_duas_vezes_nao_duplica(sessao, clinica, migrado):
    with Extrato(EXTRATO) as extrato:
        segundo = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert segundo.categorias == migrado.categorias
    assert sessao.query(Categoria).filter_by(clinica_id=clinica.id).count() == 12
    assert sessao.query(Procedimento).count() == 476
    assert sessao.query(Preco).count() == 606
