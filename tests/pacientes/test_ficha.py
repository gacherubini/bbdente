"""A ficha alem do essencial: CPF, endereco, indicacao e observacao.

Os tres primeiros ja vinham do ARQCLIEN e moravam no banco sem tela nenhuma; a
observacao nasce agora. As regras que este arquivo trava:

- **CPF errado entra marcado, nunca recusado** — a mesma regua do telefone.
- **Editar endereco atualiza a linha residencial**, nunca cria uma segunda.
- **Corrigir tira a marca**, como ja acontecia com telefone.
"""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.pacientes.models import Paciente, PacienteEndereco
from app.pacientes.service import Endereco, atualizar, criar


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    return clinica, usuario


def _enderecos(sessao, paciente_id: int) -> list[PacienteEndereco]:
    return list(
        sessao.scalars(
            select(PacienteEndereco)
            .where(PacienteEndereco.paciente_id == paciente_id)
            .order_by(PacienteEndereco.id)
        )
    )


def test_criar_guarda_a_ficha_inteira(sessao, base):
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Amanda Rosa",
        cpf="529.982.247-25",
        indicacao="Dra. Katia",
        observacao="Prefere atendimento de manha.",
        endereco=Endereco(
            logradouro="Rua das Flores, 120",
            bairro="Centro",
            cidade="Porto Alegre",
            uf="rs",
            cep="90010000",
        ),
    )
    sessao.flush()

    assert paciente.cpf == "529.982.247-25"
    assert paciente.indicacao == "Dra. Katia"
    assert paciente.observacao == "Prefere atendimento de manha."
    assert paciente.revisar_motivo == []

    (endereco,) = _enderecos(sessao, paciente.id)
    assert endereco.tipo == "RESIDENCIAL"
    assert endereco.logradouro == "Rua das Flores, 120"
    assert endereco.bairro == "Centro"
    assert endereco.cidade == "Porto Alegre"
    assert endereco.uf == "RS"
    assert endereco.cep == "90010-000"


def test_cpf_com_digito_errado_grava_e_marca_para_revisao(sessao, base):
    """Quem cadastra esta com a pessoa na frente: nao trava, marca."""
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Bruno Lima",
        cpf="529.982.247-26",
    )
    sessao.flush()

    assert paciente.cpf == "529.982.247-26"
    assert "cpf_suspeito" in paciente.revisar_motivo


def test_sem_cpf_nao_marca_nada(sessao, base):
    """Nao informar CPF e legitimo — a maioria dos 5.561 migrados nao tem."""
    clinica, usuario = base
    paciente = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="Carla Souza"
    )
    sessao.flush()
    assert paciente.cpf is None
    assert paciente.revisar_motivo == []


def test_sem_endereco_nao_cria_linha_vazia(sessao, base):
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Diego Alves",
        endereco=Endereco(),
    )
    sessao.flush()
    assert _enderecos(sessao, paciente.id) == []


def test_editar_o_endereco_atualiza_a_linha_em_vez_de_criar_outra(sessao, base):
    """A pessoa mudou de rua: e o mesmo endereco residencial corrigido, e nao um
    segundo endereco. Duas linhas RESIDENCIAL fariam a ficha mostrar as duas."""
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Elisa Prado",
        endereco=Endereco(logradouro="Rua A, 1", cidade="Canoas", uf="RS"),
    )
    sessao.flush()

    atualizar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        nome="Elisa Prado",
        endereco=Endereco(logradouro="Rua B, 2", cidade="Gravatai", uf="RS"),
    )
    sessao.flush()

    (endereco,) = _enderecos(sessao, paciente.id)
    assert endereco.logradouro == "Rua B, 2"
    assert endereco.cidade == "Gravatai"


def test_editar_sem_mandar_endereco_nao_apaga_o_que_estava_la(sessao, base):
    """Chamada que nao fala de endereco nao mexe em endereco."""
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Fabio Nunes",
        endereco=Endereco(logradouro="Rua C, 3"),
    )
    sessao.flush()

    atualizar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        nome="Fabio Nunes",
    )
    sessao.flush()

    (endereco,) = _enderecos(sessao, paciente.id)
    assert endereco.logradouro == "Rua C, 3"


def test_o_endereco_comercial_migrado_fica_intocado(sessao, base):
    """A tela edita so o residencial; o comercial do Dentalis continua no banco."""
    clinica, usuario = base
    paciente = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, nome="Gisele Mota"
    )
    sessao.flush()
    sessao.add(
        PacienteEndereco(
            paciente_id=paciente.id, tipo="COMERCIAL", logradouro="Av. Trabalho, 900"
        )
    )
    sessao.flush()

    atualizar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        nome="Gisele Mota",
        endereco=Endereco(logradouro="Rua Casa, 10"),
    )
    sessao.flush()

    tipos = {e.tipo: e.logradouro for e in _enderecos(sessao, paciente.id)}
    assert tipos == {"COMERCIAL": "Av. Trabalho, 900", "RESIDENCIAL": "Rua Casa, 10"}


def test_corrigir_o_cpf_tira_a_marca(sessao, base):
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Helena Dias",
        cpf="529.982.247-26",
    )
    sessao.flush()
    assert "cpf_suspeito" in paciente.revisar_motivo

    atualizar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        nome="Helena Dias",
        cpf="529.982.247-25",
    )
    sessao.flush()
    assert paciente.revisar_motivo == []


def test_marca_que_a_tela_nao_sabe_conferir_continua(sessao, base):
    """`possivel_duplicata` nao e assunto do CPF: quem nao sabe verificar, nao apaga."""
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Igor Paz",
        cpf="529.982.247-26",
    )
    paciente.revisar_motivo = [*paciente.revisar_motivo, "possivel_duplicata"]
    sessao.flush()

    atualizar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        nome="Igor Paz",
        cpf="529.982.247-25",
    )
    sessao.flush()
    assert paciente.revisar_motivo == ["possivel_duplicata"]


def test_a_auditoria_registra_os_campos_novos(sessao, base):
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Julia Reis",
        cpf="529.982.247-25",
        observacao="Alergica a latex.",
    )
    sessao.flush()

    atualizar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
        nome="Julia Reis",
        cpf="529.982.247-25",
        observacao="Alergica a latex e a dipirona.",
        endereco=Endereco(logradouro="Rua Nova, 5"),
    )
    sessao.flush()

    linha = sessao.scalars(
        select(Auditoria)
        .where(Auditoria.entidade == "paciente", Auditoria.acao == "ATUALIZAR")
        .order_by(Auditoria.id.desc())
    ).first()
    assert linha.dados_antes["observacao"] == "Alergica a latex."
    assert linha.dados_depois["observacao"] == "Alergica a latex e a dipirona."
    assert linha.dados_antes["endereco"] is None
    assert linha.dados_depois["endereco"] == "Rua Nova, 5"


def test_criar_com_ficha_nao_faz_commit(sessao, base):
    """Quem chama decide gravar — igual ao resto do modulo."""
    clinica, usuario = base
    criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Lucas Braga",
        cpf="529.982.247-25",
        endereco=Endereco(logradouro="Rua Z, 9"),
    )
    sessao.rollback()
    assert sessao.scalars(
        select(func.count()).select_from(Paciente).where(Paciente.nome == "Lucas Braga")
    ).one() == 0


def test_nascimento_continua_funcionando_com_a_ficha_junto(sessao, base):
    """Guarda contra regressao: os campos novos nao podem atropelar os antigos."""
    clinica, usuario = base
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Marina Luz",
        telefone="3268-0798",
        nascimento=date(1980, 3, 14),
        cpf="111.444.777-35",
    )
    sessao.flush()
    assert paciente.nascimento == date(1980, 3, 14)
    assert [t.numero for t in paciente.telefones] == ["32680798"]
