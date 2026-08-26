"""Lista de convenios da clinica — o select da tela de cadastro de paciente."""

import pytest

from app.auth.models import Clinica
from app.catalogo.models import Convenio
from app.catalogo.service import convenios


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    outra = Clinica(nome="Outra")
    sessao.add_all([clinica, outra])
    sessao.flush()
    sessao.add_all(
        [
            Convenio(clinica_id=clinica.id, codigo="003", nome="UNIMED"),
            Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR"),
            Convenio(clinica_id=clinica.id, codigo="002", nome="UNIODONTO"),
            Convenio(clinica_id=outra.id, codigo="001", nome="DE OUTRA CLINICA"),
        ]
    )
    sessao.flush()
    return clinica, outra


def test_lista_os_convenios_da_clinica_ordenados_por_codigo(sessao, base):
    clinica, _ = base
    assert [nome for _, nome in convenios(sessao, clinica_id=clinica.id)] == [
        "PARTICULAR",
        "UNIODONTO",
        "UNIMED",
    ]


def test_devolve_id_e_nome_em_par(sessao, base):
    clinica, _ = base
    for convenio_id, nome in convenios(sessao, clinica_id=clinica.id):
        assert isinstance(convenio_id, int) and isinstance(nome, str)


def test_nao_vaza_convenio_de_outra_clinica(sessao, base):
    clinica, _ = base
    nomes = [nome for _, nome in convenios(sessao, clinica_id=clinica.id)]
    assert "DE OUTRA CLINICA" not in nomes


def test_clinica_sem_convenio_devolve_lista_vazia(sessao, base):
    sem_convenio = Clinica(nome="Sem convenio")
    sessao.add(sem_convenio)
    sessao.flush()
    assert convenios(sessao, clinica_id=sem_convenio.id) == []
