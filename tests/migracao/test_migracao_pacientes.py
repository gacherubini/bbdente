import os

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.catalogo.models import Convenio
from app.pacientes.models import Paciente, PacienteEndereco, PacienteTelefone
from migracao.extrato import Extrato
from migracao.pacientes import migrar

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture
def migrado(sessao):
    from migracao.catalogo import migrar as migrar_catalogo

    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        migrar_catalogo(sessao, extrato, clinica.id)
        resultado = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica, resultado


def test_traz_os_5561_pacientes(sessao, migrado):
    _, resultado = migrado
    assert resultado.pacientes == 5_561
    assert sessao.query(Paciente).count() == 5_561


def test_nenhum_paciente_perde_o_codigo_legado(sessao, migrado):
    assert sessao.query(Paciente).filter(Paciente.codigo_legado.is_(None)).count() == 0
    codigos = sessao.query(func.count(func.distinct(Paciente.codigo_legado))).scalar()
    assert codigos == 5_561


def test_nenhum_paciente_fica_sem_nome(sessao, migrado):
    assert sessao.query(Paciente).filter(Paciente.nome == "").count() == 0
    assert sessao.query(Paciente).filter(Paciente.nome.is_(None)).count() == 0


def test_telefone_multiplo_vira_varias_linhas_com_o_original_guardado(sessao, migrado):
    com_varios = (
        sessao.query(PacienteTelefone.paciente_id)
        .group_by(PacienteTelefone.paciente_id)
        .having(func.count() > 1)
        .first()
    )
    assert com_varios is not None
    linhas = sessao.query(PacienteTelefone).filter_by(paciente_id=com_varios[0]).all()
    assert len({t.numero for t in linhas}) == len(linhas)
    assert all(t.numero_original for t in linhas)
    assert sum(1 for t in linhas if t.principal) == 1


def test_1574_pacientes_sem_nascimento_entram_assim_mesmo(sessao, migrado):
    """Faltar data nao e motivo para recusar o cadastro."""
    assert sessao.query(Paciente).filter(Paciente.nascimento.is_(None)).count() == 1_574


def test_data_impossivel_e_preservada_e_marcada(sessao, migrado):
    marcados = sessao.scalars(
        select(Paciente).where(Paciente.revisar_motivo.any("data_suspeita"))
    ).all()
    assert marcados, "as datas impossiveis conhecidas (1194, 2080, 9200) sumiram"
    for p in marcados:
        assert p.nascimento is not None or p.ultimo_atendimento is not None


def test_telefone_curto_e_marcado_mas_gravado(sessao, migrado):
    marcados = sessao.scalars(
        select(Paciente).where(Paciente.revisar_motivo.any("telefone_incompleto"))
    ).all()
    assert marcados
    for p in marcados:
        assert p.telefones


def test_os_dois_duplicados_conhecidos_entram_marcados(sessao, migrado):
    for codigo in ("1659/PT", "4783/PT"):
        p = sessao.scalars(
            select(Paciente).where(Paciente.codigo_legado == codigo)
        ).one()
        assert "possivel_duplicata" in p.revisar_motivo


def test_convenio_e_ligado_pelo_codigo(sessao, migrado):
    com_convenio = sessao.query(Paciente).filter(Paciente.convenio_id.isnot(None)).count()
    assert com_convenio > 0
    validos = (
        sessao.query(Paciente)
        .join(Convenio, Paciente.convenio_id == Convenio.id)
        .count()
    )
    assert validos == com_convenio


def test_endereco_residencial_e_comercial_viram_linhas_separadas(sessao, migrado):
    tipos = {t for (t,) in sessao.query(PacienteEndereco.tipo).distinct()}
    assert tipos <= {"RESIDENCIAL", "COMERCIAL"}
    assert "RESIDENCIAL" in tipos


def test_rodar_duas_vezes_nao_duplica(sessao, migrado):
    clinica, _ = migrado
    with Extrato(EXTRATO) as extrato:
        migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert sessao.query(Paciente).count() == 5_561
