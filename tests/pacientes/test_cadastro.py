"""Cadastro de paciente novo pela tela — a mesma regua de telefone da migracao."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.catalogo.models import Convenio
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.service import criar, semelhantes


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    outra = Clinica(nome="Outra")
    sessao.add_all([clinica, outra])
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    convenio = Convenio(clinica_id=clinica.id, codigo="002", nome="UNIODONTO")
    sessao.add(convenio)
    sessao.flush()
    return clinica, outra, usuario, convenio


def _telefones(sessao, paciente_id: int) -> list[PacienteTelefone]:
    return list(
        sessao.scalars(
            select(PacienteTelefone)
            .where(PacienteTelefone.paciente_id == paciente_id)
            .order_by(PacienteTelefone.id)
        )
    )


def test_cria_paciente_so_com_o_nome(sessao, base):
    clinica, _, usuario, _ = base
    paciente = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="Joana Silva"
    )
    assert paciente.id is not None
    assert paciente.nome == "Joana Silva"
    assert paciente.cadastrado_em == date.today()
    # Paciente novo nao tem codigo do Dentalis — codigo_legado so existe no historico.
    assert paciente.codigo_legado is None
    assert paciente.excluido_em is None


def test_guarda_nascimento_e_convenio_quando_vierem(sessao, base):
    clinica, _, usuario, convenio = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Joana Silva",
        nascimento=date(1990, 3, 2),
        convenio_id=convenio.id,
    )
    sessao.flush()
    gravado = sessao.get(Paciente, paciente.id)
    assert gravado.nascimento == date(1990, 3, 2)
    assert gravado.convenio_id == convenio.id


@pytest.mark.parametrize("nome", ["", "   ", "\t\n"])
def test_nome_vazio_e_recusado_e_nada_e_gravado(sessao, base, nome):
    clinica, _, usuario, _ = base
    with pytest.raises(ValueError):
        criar(sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome=nome)
    assert sessao.scalars(select(func.count()).select_from(Paciente)).one() == 0


def test_telefone_vira_linha_com_digitos_e_original_guardado(sessao, base):
    clinica, _, usuario, _ = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Joana Silva",
        telefone="51 99999-0001",
    )
    telefones = _telefones(sessao, paciente.id)
    assert len(telefones) == 1
    assert telefones[0].numero == "51999990001"
    assert telefones[0].numero_original == "51 99999-0001"
    assert telefones[0].principal is True


def test_varios_numeros_num_campo_so_viram_varias_linhas(sessao, base):
    clinica, _, usuario, _ = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Joana Silva",
        telefone="32671690/99684152",
    )
    telefones = _telefones(sessao, paciente.id)
    assert [t.numero for t in telefones] == ["32671690", "99684152"]
    assert [t.principal for t in telefones] == [True, False]
    assert {t.numero_original for t in telefones} == {"32671690/99684152"}


def test_telefone_curto_grava_e_marca_para_revisao(sessao, base):
    clinica, _, usuario, _ = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Joana Silva",
        telefone="2490143",
    )
    assert [t.numero for t in _telefones(sessao, paciente.id)] == ["2490143"]
    assert "telefone_incompleto" in paciente.revisar_motivo


def test_telefone_longo_demais_entra_marcado_como_suspeito(sessao, base):
    clinica, _, usuario, _ = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Joana Silva",
        telefone="325155109633",
    )
    assert [t.numero for t in _telefones(sessao, paciente.id)] == ["325155109633"]
    assert "telefone_suspeito" in paciente.revisar_motivo


def test_sem_telefone_nao_grava_linha_nem_marca_nada(sessao, base):
    clinica, _, usuario, _ = base
    paciente = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="Joana Silva"
    )
    assert _telefones(sessao, paciente.id) == []
    assert list(paciente.revisar_motivo or []) == []


def test_criar_deixa_rastro_na_auditoria_sem_segredo(sessao, base):
    clinica, _, usuario, convenio = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Joana Silva",
        telefone="51 99999-0001",
        nascimento=date(1990, 3, 2),
        convenio_id=convenio.id,
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "paciente")
    ).all()
    assert len(linhas) == 1
    linha = linhas[0]
    assert linha.acao == "CRIAR"
    assert linha.entidade_id == paciente.id
    assert linha.clinica_id == clinica.id and linha.usuario_id == usuario.id
    assert linha.dados_depois["nome"] == "Joana Silva"
    assert linha.dados_depois["convenio_id"] == convenio.id
    assert linha.dados_depois["telefone"] == "51 99999-0001"
    chaves = " ".join(linha.dados_depois).lower()
    assert "senha" not in chaves and "hash" not in chaves and "token" not in chaves


def test_criar_nao_faz_commit(sessao, base):
    """Quem chama decide gravar. Se criar() commitasse, o ponto de salvamento
    abaixo nao teria mais o que desfazer e o paciente sobreviveria."""
    clinica, _, usuario, _ = base
    ponto = sessao.begin_nested()
    criar(sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="Joana Silva")
    ponto.rollback()
    assert sessao.scalars(select(func.count()).select_from(Paciente)).one() == 0


@pytest.fixture
def ja_cadastrados(sessao, base):
    """Nomes tirados do banco real (5.561 cadastros) — sao eles que reprovaram a
    versao anterior de semelhantes(), que casava por pedaco do nome."""
    clinica, outra, usuario, _ = base
    sessao.add_all(
        [
            Paciente(clinica_id=clinica.id, nome=nome)
            for nome in (
                "MARIA SILVA",
                "MARIA DA SILVA",
                "MARIA SANTOS",
                "MARIA SILVA SANTOS",
                "JOSÉ MENDONÇA",
                "ABNER LIMA DA SILVA",
                "ADAIL ARAUJO ABREU NETO",
                "ADA IRENE REGHELIN DE AZAMBUJA",
                "ADALBERTO FERNANDES JORGE",
                "ADA MARIA DA COSTA OSORIO",
                "ADÃO MARCIEL DE OLIVEIRA",
                "ADEMAR BITENCOURT DE MARSEA",
                "ADEMAR FRONCHETTI",
                "ADRIANA DE JESUS",
                "ALBANO JOSÉ SCHEIBLER",
            )
        ]
    )
    sessao.add_all(
        [
            Paciente(
                clinica_id=clinica.id,
                nome="MARIA SILVA EXCLUIDA",
                excluido_em=date(2020, 1, 1),
            ),
            Paciente(clinica_id=outra.id, nome="MARIA SILVA"),
        ]
    )
    sessao.flush()
    return clinica, outra, usuario


def _nomes(sessao, clinica_id: int, nome: str, **kw) -> list[str]:
    return [
        linha.nome
        for linha in semelhantes(sessao, clinica_id=clinica_id, nome=nome, **kw)
    ]


def test_primeiro_nome_solto_nao_arrasta_a_base_inteira(sessao, ja_cadastrados):
    """'Ana' casava com qualquer nome que tivesse 'n' no meio. Aviso que sempre
    aparece e quase nunca e a pessoa vira aviso que ninguem le."""
    clinica, *_ = ja_cadastrados
    nomes = _nomes(sessao, clinica.id, "Ana")
    assert "ABNER LIMA DA SILVA" not in nomes
    assert "ADAIL ARAUJO ABREU NETO" not in nomes
    assert "ADA IRENE REGHELIN DE AZAMBUJA" not in nomes


def test_maria_solta_nao_traz_quem_so_tem_as_letras(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    nomes = _nomes(sessao, clinica.id, "MARIA")
    assert "ADEMAR BITENCOURT DE MARSEA" not in nomes
    assert "ADA MARIA DA COSTA OSORIO" not in nomes


def test_nome_inteiro_em_minusculo_acha_o_cadastro(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    assert _nomes(sessao, clinica.id, "adail araujo abreu neto") == [
        "ADAIL ARAUJO ABREU NETO"
    ]


def test_espaco_repetido_nao_atrapalha(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    assert "MARIA SILVA" in _nomes(sessao, clinica.id, "maria  silva")


def test_acha_o_mesmo_nome_com_particula_no_meio(sessao, ja_cadastrados):
    """'MARIA SILVA' e 'MARIA DA SILVA' sao a mesma pessoa com o 'da' digitado."""
    clinica, *_ = ja_cadastrados
    assert "MARIA DA SILVA" in _nomes(sessao, clinica.id, "MARIA SILVA")


def test_nao_acha_quem_tem_outro_sobrenome_final(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    nomes = _nomes(sessao, clinica.id, "MARIA SILVA")
    assert "MARIA SANTOS" not in nomes
    # Sobrenome final diferente e, na pratica, outra pessoa.
    assert "MARIA SILVA SANTOS" not in nomes


def test_acento_nao_separa_a_mesma_pessoa(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    assert _nomes(sessao, clinica.id, "jose mendonca") == ["JOSÉ MENDONÇA"]
    assert "ALBANO JOSÉ SCHEIBLER" not in _nomes(sessao, clinica.id, "jose mendonca")


def test_semelhantes_ignora_excluido_e_outra_clinica(sessao, ja_cadastrados):
    clinica, outra, _ = ja_cadastrados
    linhas = semelhantes(sessao, clinica_id=clinica.id, nome="MARIA SILVA")
    assert "MARIA SILVA EXCLUIDA" not in [linha.nome for linha in linhas]
    ids_da_outra = {
        p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == outra.id))
    }
    assert not ids_da_outra & {linha.id for linha in linhas}


def test_semelhantes_respeita_o_limite(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    assert len(semelhantes(sessao, clinica_id=clinica.id, nome="MARIA SILVA", limite=1)) == 1


def test_semelhantes_com_nome_vazio_nao_traz_ninguem(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    assert semelhantes(sessao, clinica_id=clinica.id, nome="   ") == []


def test_semelhantes_traz_a_linha_pronta_para_a_tela(sessao, ja_cadastrados):
    clinica, *_ = ja_cadastrados
    linha = next(
        linha
        for linha in semelhantes(sessao, clinica_id=clinica.id, nome="MARIA SILVA")
        if linha.nome == "MARIA SILVA"
    )
    assert linha.id is not None
    assert linha.telefone is None
    assert linha.pendentes == 0


def test_paciente_recem_criado_aparece_em_semelhantes(sessao, base):
    clinica, _, usuario, _ = base
    criar(sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="João Mendonça")
    assert _nomes(sessao, clinica.id, "JOAO MENDONCA") == ["João Mendonça"]
