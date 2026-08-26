"""Editar o cadastro do paciente.

O MVP so lia e buscava. Duas regras nascem aqui:

- **corrigir tira a marca.** Cadastro marcado com `telefone_incompleto` que ganha
  um telefone bom perde a marca — e assim a lista de 'revisar' encolhe com o
  trabalho da recepcao, em vez de crescer para sempre.
- **telefone trocado nao e apagado.** Some da ficha, continua na tabela com
  `excluido_em`. Numero antigo pode ser a unica forma de achar alguem que nao
  volta ha vinte anos.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Convenio
from app.main import criar_app
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.service import criar
from app.shared.db import obter_sessao


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    particular = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    uniodonto = Convenio(clinica_id=clinica.id, codigo="051", nome="UNIODONTO")
    sessao.add_all([particular, uniodonto])
    sessao.flush()
    paciente = criar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome="Amanda Rosa",
        telefone="3268-0798",
        nascimento=date(1980, 3, 14),
        convenio_id=particular.id,
    )
    sessao.flush()
    return clinica, usuario, paciente, particular, uniodonto


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def formulario(cenario, **extra) -> dict:
    _, _, paciente, particular, _ = cenario
    corpo = {
        "nome": paciente.nome,
        "telefone": "3268-0798",
        "nascimento": "1980-03-14",
        "convenio_id": str(particular.id),
    }
    corpo.update(extra)
    return corpo


def numeros(sessao, paciente) -> list[str]:
    sessao.expire(paciente)
    return sorted(t.numero for t in paciente.telefones)


# --- a tela --------------------------------------------------------------------


def test_a_tela_abre_com_o_cadastro_preenchido(cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.get(f"/pacientes/{paciente.id}/editar")
    assert resposta.status_code == 200
    assert "Amanda Rosa" in resposta.text
    assert "3268-0798" in resposta.text


def test_paciente_inexistente_da_404(cliente):
    assert cliente.get("/pacientes/999999/editar").status_code == 404


def test_paciente_de_outra_clinica_da_404(sessao, cliente):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add(alheio)
    sessao.flush()
    assert cliente.get(f"/pacientes/{alheio.id}/editar").status_code == 404


def test_a_tela_nao_deixa_mexer_no_codigo_do_dentalis(cliente, cenario):
    """O codigo legado e a chave do historico migrado: editar seria cortar o fio."""
    _, _, paciente, *_ = cenario
    html = cliente.get(f"/pacientes/{paciente.id}/editar").text
    assert 'name="codigo_legado"' not in html


# --- editar --------------------------------------------------------------------


def test_editar_o_nome_grava_e_volta_para_a_ficha(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, nome="Amanda Rosa da Silva"),
    )
    assert resposta.status_code == 303
    sessao.refresh(paciente)
    assert paciente.nome == "Amanda Rosa da Silva"


def test_a_edicao_deixa_antes_e_depois_na_auditoria(sessao, cliente, cenario):
    _, usuario, paciente, *_ = cenario
    cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, nome="Amanda Rosa da Silva"),
    )
    linha = sessao.scalars(
        select(Auditoria).where(
            Auditoria.entidade == "paciente", Auditoria.acao == "ATUALIZAR"
        )
    ).one()
    assert linha.dados_antes["nome"] == "Amanda Rosa"
    assert linha.dados_depois["nome"] == "Amanda Rosa da Silva"
    assert linha.usuario_id == usuario.id


def test_trocar_o_convenio_funciona(sessao, cliente, cenario):
    _, _, paciente, _, uniodonto = cenario
    cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, convenio_id=str(uniodonto.id)),
    )
    sessao.refresh(paciente)
    assert paciente.convenio_id == uniodonto.id


def test_limpar_o_nascimento_funciona(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    cliente.post(f"/pacientes/{paciente.id}/editar", data=formulario(cenario, nascimento=""))
    sessao.refresh(paciente)
    assert paciente.nascimento is None


def test_nome_vazio_e_recusado(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        f"/pacientes/{paciente.id}/editar", data=formulario(cenario, nome="  ")
    )
    assert resposta.status_code == 200
    sessao.refresh(paciente)
    assert paciente.nome == "Amanda Rosa"


def test_data_invalida_e_recusada(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        f"/pacientes/{paciente.id}/editar", data=formulario(cenario, nascimento="30/02/1980")
    )
    assert resposta.status_code == 200
    sessao.refresh(paciente)
    assert paciente.nascimento == date(1980, 3, 14)


# --- telefone ------------------------------------------------------------------


def test_trocar_o_telefone_troca_o_da_ficha(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    cliente.post(
        f"/pacientes/{paciente.id}/editar", data=formulario(cenario, telefone="51999881234")
    )
    assert numeros(sessao, paciente) == ["51999881234"]


def test_o_telefone_antigo_nao_e_apagado_do_banco(sessao, cliente, cenario):
    """Numero velho pode ser a unica forma de achar quem nao volta ha 20 anos."""
    _, _, paciente, *_ = cenario
    cliente.post(
        f"/pacientes/{paciente.id}/editar", data=formulario(cenario, telefone="51999881234")
    )
    guardados = sessao.scalars(
        select(PacienteTelefone).where(PacienteTelefone.paciente_id == paciente.id)
    ).all()
    assert {t.numero for t in guardados} == {"32680798", "51999881234"}
    antigo = next(t for t in guardados if t.numero == "32680798")
    assert antigo.excluido_em is not None


def test_dois_telefones_no_mesmo_campo_viram_duas_linhas(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, telefone="3268-0798 / 51999881234"),
    )
    assert numeros(sessao, paciente) == ["32680798", "51999881234"]


def test_salvar_o_mesmo_telefone_nao_duplica_linha(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    for _tentativa in range(3):
        cliente.post(f"/pacientes/{paciente.id}/editar", data=formulario(cenario))
    total = sessao.scalars(
        select(func.count())
        .select_from(PacienteTelefone)
        .where(PacienteTelefone.paciente_id == paciente.id)
    ).one()
    assert total == 1


def test_apagar_o_telefone_deixa_a_ficha_sem_numero(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    cliente.post(f"/pacientes/{paciente.id}/editar", data=formulario(cenario, telefone=""))
    assert numeros(sessao, paciente) == []


# --- as marcas de revisao ------------------------------------------------------


def test_corrigir_o_telefone_tira_a_marca(sessao, cliente, cenario):
    """Marca que nunca sai e marca que ninguem olha."""
    clinica, usuario, _, particular, _ = cenario
    ruim = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id,
        nome="Joao Curto", telefone="123", convenio_id=particular.id,
    )
    sessao.flush()
    assert "telefone_incompleto" in ruim.revisar_motivo

    cliente.post(
        f"/pacientes/{ruim.id}/editar",
        data={"nome": "Joao Curto", "telefone": "3268-0798",
              "nascimento": "", "convenio_id": str(particular.id)},
    )
    sessao.refresh(ruim)
    assert ruim.revisar_motivo == []


def test_telefone_ainda_ruim_mantem_a_marca(sessao, cliente, cenario):
    clinica, usuario, _, particular, _ = cenario
    ruim = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id,
        nome="Joao Curto", telefone="123", convenio_id=particular.id,
    )
    sessao.flush()
    cliente.post(
        f"/pacientes/{ruim.id}/editar",
        data={"nome": "Joao Curto", "telefone": "456",
              "nascimento": "", "convenio_id": str(particular.id)},
    )
    sessao.refresh(ruim)
    assert "telefone_incompleto" in ruim.revisar_motivo


def test_marca_que_nao_e_de_telefone_continua_intocada(sessao, cliente, cenario):
    """So as marcas que esta tela sabe conferir podem sair por ela."""
    clinica, usuario, _, particular, _ = cenario
    outro = criar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id,
        nome="Marcado", telefone="3268-0798", convenio_id=particular.id,
    )
    outro.revisar_motivo = ["cadastro_so_no_orcamento"]
    sessao.flush()
    cliente.post(
        f"/pacientes/{outro.id}/editar",
        data={"nome": "Marcado", "telefone": "3268-0798",
              "nascimento": "", "convenio_id": str(particular.id)},
    )
    sessao.refresh(outro)
    assert outro.revisar_motivo == ["cadastro_so_no_orcamento"]


# --- a ficha completa ----------------------------------------------------------


def test_a_tela_traz_os_campos_da_ficha_completa(cliente, cenario):
    _, _, paciente, *_ = cenario
    html = cliente.get(f"/pacientes/{paciente.id}/editar").text
    for campo in ("cpf", "indicacao", "observacao", "logradouro", "bairro",
                  "cidade", "uf", "cep"):
        assert f'name="{campo}"' in html


def test_salvar_a_ficha_completa_grava_tudo(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(
            cenario,
            cpf="529.982.247-25",
            indicacao="Dra. Katia",
            observacao="Prefere sabado.",
            logradouro="Rua das Flores, 120",
            bairro="Centro",
            cidade="Porto Alegre",
            uf="RS",
            cep="90010000",
        ),
    )
    assert resposta.status_code == 303
    sessao.expire(paciente)
    assert paciente.cpf == "529.982.247-25"
    assert paciente.indicacao == "Dra. Katia"
    assert paciente.observacao == "Prefere sabado."
    (endereco,) = paciente.enderecos
    assert (endereco.tipo, endereco.cidade, endereco.cep) == (
        "RESIDENCIAL", "Porto Alegre", "90010-000",
    )


def test_a_tela_reabre_com_a_ficha_preenchida(sessao, cliente, cenario):
    _, _, paciente, *_ = cenario
    cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, cpf="529.982.247-25", cidade="Porto Alegre",
                        observacao="Prefere sabado."),
    )
    html = cliente.get(f"/pacientes/{paciente.id}/editar").text
    assert "529.982.247-25" in html
    assert "Porto Alegre" in html
    assert "Prefere sabado." in html


def test_cpf_errado_grava_marcado_e_a_tela_avisa(sessao, cliente, cenario):
    """A recepcao nao fica travada com a pessoa na frente: grava e marca."""
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, cpf="529.982.247-26"),
    )
    assert resposta.status_code == 303
    sessao.expire(paciente)
    assert paciente.cpf == "529.982.247-26"
    assert "cpf_suspeito" in paciente.revisar_motivo
    assert "cpf suspeito" in cliente.get(f"/pacientes/{paciente.id}/editar").text


def test_formulario_recusado_devolve_a_ficha_digitada(sessao, cliente, cenario):
    """Nome vazio nao pode custar a observacao que a pessoa acabou de escrever."""
    _, _, paciente, *_ = cenario
    resposta = cliente.post(
        f"/pacientes/{paciente.id}/editar",
        data=formulario(cenario, nome="", observacao="Nao atende de manha.",
                        cidade="Canoas"),
    )
    assert resposta.status_code == 200
    assert "Nao atende de manha." in resposta.text
    assert "Canoas" in resposta.text
