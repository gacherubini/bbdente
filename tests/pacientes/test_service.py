from datetime import date
from decimal import Decimal

import pytest

from app.auth.models import Clinica
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.clinico.models import Lancamento, Odontograma
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.service import Filtro, buscar, contagens, obter
from app.shared.tipos import Escopo, StatusLancamento


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="002", nome="UNIODONTO")
    sessao.add_all([categoria, convenio])
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(proc)
    sessao.flush()

    amanda = Paciente(
        clinica_id=clinica.id, codigo_legado="6612/PT", nome="Amanda Ribeiro Nogueira",
        nascimento=date(1990, 3, 2), ultimo_atendimento=date(2024, 6, 25),
    )
    itagiba = Paciente(
        clinica_id=clinica.id, codigo_legado="3799/PT", nome="Itagiba Pereira Bastos",
        nascimento=date(1937, 1, 5), ultimo_atendimento=date(2024, 6, 26),
        convenio_id=convenio.id,
    )
    antigo = Paciente(
        clinica_id=clinica.id, codigo_legado="0001/PT", nome="Paciente Antigo",
        ultimo_atendimento=date(2001, 5, 1),
    )
    excluido = Paciente(
        clinica_id=clinica.id, codigo_legado="0002/PT", nome="Ja Excluido",
        excluido_em=date(2020, 1, 1),
    )
    sessao.add_all([amanda, itagiba, antigo, excluido])
    sessao.flush()

    sessao.add(
        PacienteTelefone(
            paciente_id=amanda.id, numero="51999990001",
            numero_original="51999990001", principal=True,
        )
    )
    sessao.add(
        PacienteTelefone(
            paciente_id=itagiba.id, numero="2490143",
            numero_original="2490-143", principal=True,
        )
    )
    odo = Odontograma(paciente_id=itagiba.id, numero=1)
    sessao.add(odo)
    sessao.flush()
    for _ in range(3):
        sessao.add(
            Lancamento(
                clinica_id=clinica.id, odontograma_id=odo.id, dente=16,
                escopo=Escopo.DENTE, procedimento_id=proc.id,
                status=StatusLancamento.PLANEJADO, valor=Decimal("100.00"),
            )
        )
    sessao.add(
        Lancamento(
            clinica_id=clinica.id, odontograma_id=odo.id, dente=17,
            escopo=Escopo.DENTE, procedimento_id=proc.id,
            status=StatusLancamento.REALIZADO, valor=Decimal("50.00"),
        )
    )
    sessao.flush()
    return clinica, amanda, itagiba, antigo, excluido


def test_busca_vazia_traz_os_ativos_em_ordem_alfabetica(sessao, cenario):
    clinica, amanda, itagiba, antigo, _ = cenario
    linhas = buscar(sessao, clinica_id=clinica.id, filtro=Filtro.ATIVOS)
    nomes = [linha.nome for linha in linhas]
    assert nomes == ["Amanda Ribeiro Nogueira", "Itagiba Pereira Bastos"]


def test_excluido_nunca_aparece_em_nenhum_filtro(sessao, cenario):
    clinica, *_ = cenario
    for filtro in Filtro:
        nomes = [linha.nome for linha in buscar(sessao, clinica_id=clinica.id, filtro=filtro)]
        assert "Ja Excluido" not in nomes


def test_filtro_todos_inclui_quem_nao_vem_ha_anos(sessao, cenario):
    clinica, *_ = cenario
    nomes = [linha.nome for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)]
    assert "Paciente Antigo" in nomes


@pytest.mark.parametrize(
    "termo", ["amanda", "AMANDA", "ribeiro", "Ribeiro Nogueira", "6612", "51999990001"]
)
def test_busca_por_nome_parcial_telefone_e_codigo(sessao, cenario, termo):
    clinica, *_ = cenario
    linhas = buscar(sessao, clinica_id=clinica.id, termo=termo, filtro=Filtro.TODOS)
    assert [linha.nome for linha in linhas] == ["Amanda Ribeiro Nogueira"]


def test_busca_sem_resultado_devolve_lista_vazia(sessao, cenario):
    clinica, *_ = cenario
    assert buscar(sessao, clinica_id=clinica.id, termo="zzzzz", filtro=Filtro.TODOS) == []


def test_conta_pendentes_e_valor_em_aberto(sessao, cenario):
    clinica, _, itagiba, *_ = cenario
    linha = next(
        linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
        if linha.id == itagiba.id
    )
    assert linha.pendentes == 3
    assert linha.em_aberto == Decimal("300.00")


def test_filtro_com_pendencia_so_traz_quem_tem(sessao, cenario):
    clinica, _, itagiba, *_ = cenario
    linhas = buscar(sessao, clinica_id=clinica.id, filtro=Filtro.COM_PENDENCIA)
    assert [linha.id for linha in linhas] == [itagiba.id]


def test_idade_e_calculada_e_ausente_quando_nao_ha_nascimento(sessao, cenario):
    clinica, *_ = cenario
    por_nome = {
        linha.nome: linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
    }
    assert por_nome["Amanda Ribeiro Nogueira"].idade == date.today().year - 1990 - (
        (date.today().month, date.today().day) < (3, 2)
    )
    assert por_nome["Paciente Antigo"].idade is None


def test_telefone_vem_formatado_e_o_curto_vem_marcado(sessao, cenario):
    clinica, *_ = cenario
    por_nome = {
        linha.nome: linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
    }
    assert por_nome["Amanda Ribeiro Nogueira"].telefone == "(51) 99999-0001"
    assert por_nome["Amanda Ribeiro Nogueira"].telefone_suspeito is False
    assert por_nome["Itagiba Pereira Bastos"].telefone_suspeito is True


def test_convenio_vem_pelo_service_do_catalogo(sessao, cenario):
    clinica, _, itagiba, *_ = cenario
    linha = next(
        linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
        if linha.id == itagiba.id
    )
    assert linha.convenio == "UNIODONTO"


def test_paciente_sem_convenio_aparece_como_particular(sessao, cenario):
    clinica, amanda, *_ = cenario
    linha = next(
        linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
        if linha.id == amanda.id
    )
    assert linha.convenio is None


def test_obter_respeita_a_clinica_e_a_exclusao(sessao, cenario):
    clinica, amanda, _, _, excluido = cenario
    assert obter(sessao, clinica_id=clinica.id, paciente_id=amanda.id) is not None
    assert obter(sessao, clinica_id=clinica.id, paciente_id=excluido.id) is None
    assert obter(sessao, clinica_id=clinica.id + 999, paciente_id=amanda.id) is None


def test_contagens_do_cabecalho(sessao, cenario):
    clinica, *_ = cenario
    numeros = contagens(sessao, clinica_id=clinica.id)
    assert numeros["total"] == 3  # o excluido nao conta
    assert numeros["com_pendencia"] == 1
