"""Reservar e despachar o lembrete da véspera.

O teste mais importante desta suíte é `test_rodar_duas_vezes_manda_uma_vez_so`.
Tudo aqui existe para que a mesma paciente nunca receba a mesma mensagem duas
vezes: **no máximo uma vez, nunca ao menos uma vez.** Mandar duas vezes queima a
paciente e é exatamente o padrão que a detecção do WhatsApp procura.

Nada aqui toca a rede: o provedor é de mentira e registra o que enviaria.
"""

from datetime import date, datetime, time, timedelta

import pytest

from app.agenda import lembretes, service
from app.agenda.models import Lembrete, SituacaoAgendamento, SituacaoLembrete
from app.agenda.whatsapp.fake import ProvedorFake
from app.auth.models import Auditoria, Clinica, Usuario
from app.pacientes import service as pacientes

# A consulta é amanhã às 14h; o disparo roda hoje às 18h.
CONSULTA = date(2026, 9, 1)
AGORA = datetime(2026, 8, 31, 18, 0)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="Consultório Dra. Kátia")
    sessao.add(clinica)
    sessao.flush()
    usuario = Usuario(clinica_id=clinica.id, nome="Dra. Kátia", email="k@l", senha_hash="x")
    sessao.add(usuario)
    sessao.flush()
    configuracao = service.configuracao_de(sessao, clinica_id=clinica.id)
    configuracao.lembrete_ativo = True
    configuracao.endereco = "Rua X, 100"
    configuracao.telefone_clinica = "(51) 3333-3333"
    service.modelo_da_vespera(sessao, clinica_id=clinica.id)
    sessao.flush()
    return {"clinica": clinica, "usuario": usuario, "configuracao": configuracao}


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


def _marcar(sessao, cenario, **kwargs):
    dados = {"dia": CONSULTA, "inicio": time(14, 0)}
    dados.update(kwargs)
    return service.marcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        **dados,
    )


def _rodar(sessao, cenario, *, agora=AGORA, provedor=None):
    provedor = provedor or ProvedorFake()
    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=agora)
    resumo = lembretes.despachar(
        sessao,
        clinica_id=cenario["clinica"].id,
        agora=agora,
        provedor=provedor,
        pausar=lambda: None,
    )
    return provedor, resumo


# --- o coração ---------------------------------------------------------------

def test_rodar_duas_vezes_manda_uma_vez_so(sessao, cenario):
    """O teste que justifica o `UNIQUE (agendamento_id, tipo)` existir."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario)
    _rodar(sessao, cenario, provedor=provedor)

    assert len(provedor.enviadas) == 1


def test_reservar_duas_vezes_nao_cria_duas_linhas(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=AGORA)
    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=AGORA)

    assert sessao.query(Lembrete).count() == 1


def test_a_mensagem_sai_com_o_nome_o_dia_e_a_hora(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario)
    numero, texto = provedor.enviadas[0]

    assert numero == "5551999998888"
    assert "Maria" in texto and "14:00" in texto and "amanhã" in texto


def test_o_texto_que_saiu_fica_congelado_no_lembrete(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    _rodar(sessao, cenario)

    lembrete = sessao.query(Lembrete).one()
    assert lembrete.situacao is SituacaoLembrete.ENVIADO
    assert "Maria" in lembrete.texto
    assert lembrete.numero == "5551999998888"
    assert lembrete.enviado_em is not None


def test_todo_envio_deixa_linha_na_auditoria(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    _rodar(sessao, cenario)

    assert sessao.query(Auditoria).filter_by(entidade="lembrete", acao="ENVIAR").count() == 1


# --- quem não recebe, e por quê ---------------------------------------------

def _motivo(sessao):
    return sessao.query(Lembrete).one().motivo


def test_sem_permissao_nao_recebe_e_fica_registrado(sessao, cenario):
    """NULL não é "não": é "nunca perguntamos" — e mesmo assim não recebe. A
    linha DESCARTADA existe para a tela poder dizer quem ficou de fora."""
    paciente = _paciente(sessao, cenario, aceita=None)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert _motivo(sessao) == "sem_permissao"


def test_quem_pediu_para_nao_receber_nao_recebe(sessao, cenario):
    paciente = _paciente(sessao, cenario, aceita=False)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert _motivo(sessao) == "sem_permissao"


def test_telefone_imprestavel_da_ficha_vira_descarte(sessao, cenario):
    paciente = _paciente(sessao, cenario, telefone="36535051")
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert _motivo(sessao) == "sem_numero"


def test_avulso_com_telefone_recebe(sessao, cenario):
    """O telefone foi ditado agora, ao telefone, para marcar esta consulta."""
    _marcar(sessao, cenario, nome_avulso="Maria, indicação da Ana",
            telefone_avulso="51999997777")

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas[0][0] == "5551999997777"


def test_avulso_sem_telefone_nao_recebe_e_nao_e_erro(sessao, cenario):
    _marcar(sessao, cenario, nome_avulso="Joana")

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert _motivo(sessao) == "sem_numero"


def test_avulso_que_recusou_nao_recebe(sessao, cenario):
    _marcar(sessao, cenario, nome_avulso="Joana", telefone_avulso="51999997777",
            avisar_avulso=False)

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert _motivo(sessao) == "avulso_recusou"


# --- tempo -------------------------------------------------------------------

def test_consulta_de_hoje_a_nove_horas_sai_dizendo_hoje(sessao, cenario):
    """A máquina não acordou ontem e o processo só rodou às 5h da manhã. Um
    lembrete atrasado que diz a verdade ainda ajuda."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id, dia=CONSULTA, inicio=time(14, 0))

    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 9, 1, 5, 0))

    assert "hoje" in provedor.enviadas[0][1]


def test_consulta_daqui_a_tres_horas_expira(sessao, cenario):
    """Lembrete que chega em cima da hora não evita falta nenhuma — e a paciente
    já saiu de casa ou já perdeu."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 9, 1, 11, 0))

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).one().situacao is SituacaoLembrete.EXPIRADO


def test_consulta_de_depois_de_amanha_ainda_nao_entra_na_fila(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id, dia=CONSULTA + timedelta(days=3))

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).count() == 0


def test_desmarcou_depois_de_reservado_nao_recebe(sessao, cenario):
    """Desmarcou às 17h, não recebe às 18h."""
    paciente = _paciente(sessao, cenario)
    agendamento = _marcar(sessao, cenario, paciente_id=paciente.id)
    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=AGORA)
    service.mudar_situacao(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        agendamento_id=agendamento.id,
        situacao=SituacaoAgendamento.DESMARCADO,
    )

    provedor = ProvedorFake()
    lembretes.despachar(
        sessao,
        clinica_id=cenario["clinica"].id,
        agora=AGORA,
        provedor=provedor,
        pausar=lambda: None,
    )

    assert provedor.enviadas == []
    lembrete = sessao.query(Lembrete).one()
    assert lembrete.situacao is SituacaoLembrete.CANCELADO
    assert lembrete.motivo == "desmarcado"


# --- falha, chave geral e limites -------------------------------------------

def test_falha_do_provedor_nao_reenvia_sozinha(sessao, cenario):
    """Robô insistindo é robô banido. Falhou, aparece na tela, ela liga."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    quebrado = ProvedorFake(erro="número sem WhatsApp")

    _rodar(sessao, cenario, provedor=quebrado)
    lembrete = sessao.query(Lembrete).one()
    assert lembrete.situacao is SituacaoLembrete.FALHOU
    assert lembrete.tentativas == 1

    _rodar(sessao, cenario, provedor=quebrado)
    assert sessao.query(Lembrete).one().tentativas == 1


def test_uma_falha_no_meio_da_fila_nao_impede_as_seguintes(sessao, cenario):
    """Uma paciente com número ruim não pode impedir as outras de receberem."""
    for i in range(3):
        paciente = _paciente(sessao, cenario, nome=f"PACIENTE {i}")
        _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(14 + i, 0))
    provedor = ProvedorFake(falhar_na=2)

    _rodar(sessao, cenario, provedor=provedor)

    assert len(provedor.enviadas) == 2
    assert sessao.query(Lembrete).filter_by(situacao=SituacaoLembrete.FALHOU).count() == 1


def test_a_chave_geral_desligada_nao_cria_nem_manda_nada(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    cenario["configuracao"].lembrete_ativo = False
    sessao.flush()

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).count() == 0


def test_religar_depois_de_uma_semana_nao_dispara_acumulado(sessao, cenario):
    """A fila é derivada da agenda, não acumulada: voltar a ligar não despeja
    mensagem sobre consulta que já passou."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    cenario["configuracao"].lembrete_ativo = False
    sessao.flush()
    _rodar(sessao, cenario)

    cenario["configuracao"].lembrete_ativo = True
    sessao.flush()
    provedor, _ = _rodar(sessao, cenario, agora=AGORA + timedelta(days=7))

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).count() == 0


def test_o_teto_diario_segura_o_excesso(sessao, cenario):
    """Volume e ritmo humanos são a mitigação que a via não oficial exige."""
    cenario["configuracao"].lembrete_teto_diario = 2
    sessao.flush()
    for i in range(4):
        paciente = _paciente(sessao, cenario, nome=f"PACIENTE {i}")
        _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(9 + i, 0))

    provedor, _ = _rodar(sessao, cenario)

    assert len(provedor.enviadas) == 2
    assert (
        sessao.query(Lembrete).filter_by(motivo="teto_diario").count() == 2
    )


def test_horario_de_outra_clinica_nunca_entra(sessao, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    outro_usuario = Usuario(clinica_id=outra.id, nome="O", email="o@l", senha_hash="x")
    sessao.add(outro_usuario)
    sessao.flush()
    service.marcar(
        sessao,
        clinica_id=outra.id,
        usuario_id=outro_usuario.id,
        nome_avulso="Alheia",
        telefone_avulso="51999997777",
        dia=CONSULTA,
        inicio=time(14, 0),
    )

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).count() == 0


def test_modelo_quebrado_nao_manda_texto_quebrado(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    modelo = service.modelo_da_vespera(sessao, clinica_id=cenario["clinica"].id)
    modelo.texto = "Oi {primeiro_nome}, seu {tratamento} é amanhã"
    sessao.flush()

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    lembrete = sessao.query(Lembrete).one()
    assert lembrete.situacao is SituacaoLembrete.FALHOU
    assert lembrete.motivo == "modelo_invalido"


def test_linha_em_envio_nunca_e_retomada(sessao, cenario):
    """A mensagem saiu e o processo morreu antes do commit. Não sei se saiu — e
    na dúvida não manda: vai para a tela, para uma pessoa decidir."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)
    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=AGORA)
    presa = sessao.query(Lembrete).one()
    presa.situacao = SituacaoLembrete.ENVIANDO
    sessao.flush()

    provedor = ProvedorFake()
    lembretes.despachar(
        sessao,
        clinica_id=cenario["clinica"].id,
        agora=AGORA,
        provedor=provedor,
        pausar=lambda: None,
    )

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).one().situacao is SituacaoLembrete.ENVIANDO


def test_a_mensagem_diz_o_nome_da_clinica_e_da_dentista(sessao, cenario):
    """`{dentista}` sai do usuário ativo, não do nome da clínica: a mensagem é
    assinada por quem atende."""
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id)

    provedor, _ = _rodar(sessao, cenario)
    texto = provedor.enviadas[0][1]

    assert "Dra. Kátia" in texto
    assert "Consultório Dra. Kátia" in texto
    assert "(51) 3333-3333" in texto


def test_a_mensagem_nunca_leva_a_anotacao_do_horario(sessao, cenario):
    """A observação é texto livre e é onde a informação clínica vaza. Este teste
    é a prova de fogo do `ContextoDaMensagem`."""
    paciente = _paciente(sessao, cenario)
    _marcar(
        sessao,
        cenario,
        paciente_id=paciente.id,
        observacao="canal no dente 36, avaliar extração — R$ 1.200 em aberto",
    )

    provedor, _ = _rodar(sessao, cenario)
    texto = provedor.enviadas[0][1]

    for vazamento in ("canal", "36", "extração", "1.200"):
        assert vazamento not in texto
