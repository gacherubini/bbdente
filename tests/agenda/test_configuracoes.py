"""A tela de Configurações: a conexão, a chave geral e o texto da mensagem.

Ela não é aba do menu. Configuração não se acha pelo menu, se acha **pelo
problema**: quando o WhatsApp cai, o caminho é a agenda mostrar o aviso e levar
direto lá. O menu lateral é a lista das coisas que ela faz com paciente.
"""

from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agenda import service
from app.agenda.models import Lembrete, SituacaoLembrete
from app.auth.models import Auditoria, Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.main import criar_app
from app.pacientes import service as pacientes
from app.shared.db import obter_sessao


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="Consultório Dra. Kátia")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa-12", nome="K"
    )
    configuracao = service.configuracao_de(sessao, clinica_id=clinica.id)
    configuracao.endereco = "Rua X, 100"
    configuracao.telefone_clinica = "(51) 3333-3333"
    sessao.flush()
    return {"clinica": clinica, "usuario": usuario, "configuracao": configuracao}


@pytest.fixture
def cliente(sessao, cenario):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(cenario["usuario"]))
        yield c


def _horario(sessao, cenario, **kwargs):
    alvo = datetime.now() + timedelta(hours=20)
    dados = {"dia": alvo.date(), "inicio": alvo.time().replace(second=0, microsecond=0)}
    dados.update(kwargs)
    return service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        **dados,
    )


def _paciente(sessao, cenario, *, nome="MARIA SILVA", telefone="51999998888", aceita=True):
    paciente = pacientes.criar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        nome=nome,
        telefone=telefone,
    )
    if aceita is not None:
        pacientes.definir_consentimento(
            sessao,
            clinica_id=cenario["clinica"].id,
            usuario_id=cenario["usuario"].id,
            paciente_id=paciente.id,
            aceita=aceita,
        )
    return paciente


# --- onde a tela mora --------------------------------------------------------

def test_a_tela_abre(cliente):
    resposta = cliente.get("/configuracoes")

    assert resposta.status_code == 200
    assert "Lembretes" in resposta.text


def test_sem_sessao_manda_para_o_login(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        resposta = anonimo.get("/configuracoes")

    assert resposta.status_code == 303


def test_configuracoes_nao_vira_aba_no_menu(cliente):
    """Oito itens é onde uma barra lateral deixa de ser lida e passa a ser
    varrida. O oitavo roubaria atenção dos sete que importam."""
    from pathlib import Path

    base = Path("app/templates/base.html").read_text(encoding="utf-8")
    navegacao = base.split('<ul class="navegacao">')[1].split("</ul>")[0]

    assert "/configuracoes" not in navegacao
    assert "/configuracoes" in base  # mas existe, no rodapé da lateral


# --- a chave geral -----------------------------------------------------------

def test_a_chave_nasce_desligada_e_a_tela_diz_isso(cliente):
    pagina = cliente.get("/configuracoes").text

    assert "DESLIGADO" in pagina


def test_ligar_a_chave_grava_e_audita(cliente, sessao, cenario):
    resposta = cliente.post(
        "/configuracoes",
        data={"lembrete_ativo": "1", "lembrete_hora": "18:00",
              "lembrete_horas_antes": "24", "lembrete_teto_diario": "20",
              "endereco": "Rua X, 100", "telefone_clinica": "(51) 3333-3333"},
    )

    assert resposta.status_code == 303
    assert cenario["configuracao"].lembrete_ativo is True
    linha = sessao.query(Auditoria).filter_by(entidade="configuracao_clinica").one()
    assert linha.dados_antes["lembrete_ativo"] is False
    assert linha.dados_depois["lembrete_ativo"] is True


def test_desligar_a_chave_impede_o_enviar_agora(cliente, sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _horario(sessao, cenario, paciente_id=paciente.id)
    cenario["configuracao"].lembrete_ativo = False
    sessao.flush()

    cliente.post("/configuracoes/enviar-agora")

    assert sessao.query(Lembrete).count() == 0


def test_a_agenda_avisa_quando_o_lembrete_esta_desligado(cliente, sessao, cenario):
    """Silêncio que parece funcionamento é a pior forma de desligar: ela confia
    que a paciente foi avisada e a paciente não foi."""
    pagina = cliente.get("/agenda").text

    assert "lembretes de WhatsApp desligados" in pagina


def test_a_agenda_nao_avisa_quando_esta_ligado(cliente, sessao, cenario):
    cenario["configuracao"].lembrete_ativo = True
    sessao.flush()

    pagina = cliente.get("/agenda").text

    assert "lembretes de WhatsApp desligados" not in pagina


# --- enviar agora ------------------------------------------------------------

def test_enviar_agora_duas_vezes_manda_uma_vez_so(cliente, sessao, cenario):
    """É idempotente por construção, e é justamente por isso que este botão pode
    existir sem medo."""
    cenario["configuracao"].lembrete_ativo = True
    paciente = _paciente(sessao, cenario)
    _horario(sessao, cenario, paciente_id=paciente.id)
    sessao.flush()

    cliente.post("/configuracoes/enviar-agora")
    cliente.post("/configuracoes/enviar-agora")

    assert (
        sessao.query(Lembrete).filter_by(situacao=SituacaoLembrete.ENVIADO).count() == 1
    )


def test_a_tela_lista_quem_nao_vai_receber_com_o_motivo(cliente, sessao, cenario):
    """É a única parte da tela sobre a qual ela consegue agir hoje."""
    cenario["configuracao"].lembrete_ativo = True
    sem_permissao = _paciente(sessao, cenario, nome="SEM PERMISSAO", aceita=None)
    _horario(sessao, cenario, paciente_id=sem_permissao.id)
    sessao.flush()

    pagina = cliente.get("/configuracoes").text

    assert "SEM PERMISSAO" in pagina
    assert "sem permissão" in pagina
    assert f"/pacientes/{sem_permissao.id}/editar" in pagina


# --- o texto da mensagem -----------------------------------------------------

def test_a_previa_usa_dados_de_exemplo_e_nunca_uma_paciente(cliente, sessao, cenario):
    """Prévia é tela, e tela com nome de paciente vira print no grupo da
    família."""
    paciente = _paciente(sessao, cenario, nome="MARIA DE VERDADE")
    _horario(sessao, cenario, paciente_id=paciente.id)
    sessao.flush()

    pagina = cliente.get("/configuracoes").text
    previa = pagina.split("id=\"previa\"")[1].split("</pre>")[0]

    assert "MARIA DE VERDADE" not in previa
    assert "Fulana" in previa
    # O texto semeado diz "com a {dentista}": exemplo "a dentista" sairia
    # "com a a dentista" na cara dela.
    assert "a a " not in previa


def test_salvar_o_texto_grava(cliente, sessao, cenario):
    resposta = cliente.post(
        "/configuracoes/modelo",
        data={"texto": "Oi {primeiro_nome}, é {dia_relativo} às {hora}."},
    )

    assert resposta.status_code == 303
    modelo = service.modelo_da_vespera(sessao, clinica_id=cenario["clinica"].id)
    assert modelo.texto.startswith("Oi {primeiro_nome}")


def test_variavel_que_nao_existe_e_recusada_na_entrada(cliente, sessao, cenario):
    """Aqui o erro custa menos, e é a única barreira que impede alguém de
    escrever `{observacao}` achando que vai funcionar."""
    antes = service.modelo_da_vespera(sessao, clinica_id=cenario["clinica"].id).texto

    resposta = cliente.post(
        "/configuracoes/modelo",
        data={"texto": "Oi {primeiro_nome}, seu {tratamento} é amanhã"},
    )

    assert resposta.status_code == 200
    assert "tratamento" in resposta.text
    assert service.modelo_da_vespera(
        sessao, clinica_id=cenario["clinica"].id
    ).texto == antes


def test_nenhum_segredo_aparece_na_tela(cliente, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "tarefas_token", "segredo-que-nao-pode-vazar")
    monkeypatch.setattr(config, "secret_key", "outro-segredo")

    pagina = cliente.get("/configuracoes").text

    assert "segredo-que-nao-pode-vazar" not in pagina
    assert "outro-segredo" not in pagina


def test_hora_invalida_nao_derruba_a_tela(cliente, cenario):
    resposta = cliente.post(
        "/configuracoes",
        data={"lembrete_hora": "99:99", "lembrete_horas_antes": "24",
              "lembrete_teto_diario": "20"},
    )

    assert resposta.status_code == 200
    assert cenario["configuracao"].lembrete_hora == time(18, 0)
