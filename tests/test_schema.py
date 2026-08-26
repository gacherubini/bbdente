from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.auth.models import Clinica, Usuario
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.clinico.models import Lancamento, LancamentoRegiao, Odontograma
from app.pacientes.models import Paciente
from app.shared.tipos import Escopo, Regiao, StatusLancamento

TABELAS_ESPERADAS = {
    "clinica", "usuario", "auditoria",
    "paciente", "paciente_telefone", "paciente_endereco",
    "categoria", "convenio", "procedimento", "preco",
    "odontograma", "lancamento", "lancamento_regiao", "condicao",
    "pergunta_anamnese", "resposta_anamnese", "observacao_clinica",
    "parcela",
}


def test_todas_as_tabelas_da_spec_existem(engine_teste):
    existentes = set(inspect(engine_teste).get_table_names())
    assert TABELAS_ESPERADAS <= existentes


def test_enums_nativos_do_postgres_existem_com_os_valores_certos(engine_teste):
    with engine_teste.connect() as conexao:
        for nome, membros in [
            ("escopo", Escopo),
            ("regiao", Regiao),
            ("status_lancamento", StatusLancamento),
        ]:
            valores = {
                linha[0]
                for linha in conexao.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = :n"
                    ),
                    {"n": nome},
                )
            }
            assert valores == {m.value for m in membros}, nome


def test_grava_e_le_um_lancamento_completo(sessao):
    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()

    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([categoria, convenio])
    sessao.flush()

    procedimento = Procedimento(
        clinica_id=clinica.id,
        codigo="21",
        nome="Restauracao Classe II",
        categoria_id=categoria.id,
        escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.MESIAL, Regiao.OCLUSAL],
    )
    sessao.add(procedimento)
    sessao.flush()
    sessao.add(
        Preco(
            procedimento_id=procedimento.id,
            convenio_id=convenio.id,
            valor=Decimal("180.00"),
            vigente_desde=date(2026, 1, 1),
        )
    )

    paciente = Paciente(clinica_id=clinica.id, nome="Fulana de Tal")
    sessao.add(paciente)
    sessao.flush()
    odontograma = Odontograma(paciente_id=paciente.id, numero=1)
    sessao.add(odontograma)
    sessao.flush()

    lancamento = Lancamento(
        clinica_id=clinica.id,
        odontograma_id=odontograma.id,
        dente=16,
        escopo=Escopo.REGIOES,
        procedimento_id=procedimento.id,
        status=StatusLancamento.PLANEJADO,
        valor=Decimal("180.00"),
    )
    sessao.add(lancamento)
    sessao.flush()
    sessao.add_all(
        [
            LancamentoRegiao(lancamento_id=lancamento.id, regiao=Regiao.MESIAL),
            LancamentoRegiao(lancamento_id=lancamento.id, regiao=Regiao.OCLUSAL),
        ]
    )
    sessao.flush()

    lido = sessao.get(Lancamento, lancamento.id)
    assert lido is not None
    assert lido.dente == 16
    assert lido.escopo is Escopo.REGIOES
    assert {r.regiao for r in lido.regioes} == {Regiao.MESIAL, Regiao.OCLUSAL}
    assert lido.excluido_em is None


def test_array_de_enum_faz_ida_e_volta(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    categoria = Categoria(clinica_id=clinica.id, codigo="05", nome="Endodontia", ordem=5)
    sessao.add(categoria)
    sessao.flush()
    p = Procedimento(
        clinica_id=clinica.id,
        codigo="90",
        nome="Tratamento de canal",
        categoria_id=categoria.id,
        escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.CANAL_MESIAL, Regiao.CANAL_CENTRAL, Regiao.CANAL_DISTAL],
    )
    sessao.add(p)
    sessao.flush()
    sessao.expire(p)
    assert sessao.get(Procedimento, p.id).regioes_sugeridas == [
        Regiao.CANAL_MESIAL,
        Regiao.CANAL_CENTRAL,
        Regiao.CANAL_DISTAL,
    ]


def test_escopo_boca_exige_dente_nulo(sessao):
    """O banco recusa a contradicao 'boca toda, mas num dente especifico'."""
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    categoria = Categoria(clinica_id=clinica.id, codigo="01", nome="Diagnostico", ordem=1)
    sessao.add(categoria)
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="1", nome="Consulta",
        categoria_id=categoria.id, escopo_sugerido=Escopo.BOCA, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=clinica.id, nome="F")
    sessao.add_all([proc, paciente])
    sessao.flush()
    odo = Odontograma(paciente_id=paciente.id, numero=1)
    sessao.add(odo)
    sessao.flush()

    sessao.add(
        Lancamento(
            clinica_id=clinica.id, odontograma_id=odo.id, dente=16,
            escopo=Escopo.BOCA, procedimento_id=proc.id,
            status=StatusLancamento.REALIZADO, valor=Decimal("0"),
        )
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_usuario_tem_email_unico(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    for _ in range(2):
        sessao.add(
            Usuario(clinica_id=clinica.id, email="k@exemplo.com", senha_hash="x", nome="K")
        )
    with pytest.raises(IntegrityError):
        sessao.flush()
