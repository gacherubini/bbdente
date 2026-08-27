"""Reservar e despachar o lembrete da véspera.

O teste mais importante desta suíte é `test_rodar_duas_vezes_manda_uma_vez_so`.
Tudo aqui existe para que a mesma paciente nunca receba a mesma mensagem duas
vezes: **no máximo uma vez, nunca ao menos uma vez.** Mandar duas vezes queima a
paciente e é exatamente o padrão que a detecção do WhatsApp procura.

Nada aqui toca a rede: o provedor é de mentira e registra o que enviaria.
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.agenda import lembretes, service
from app.agenda.models import Lembrete, SituacaoAgendamento, SituacaoLembrete
from app.agenda.whatsapp.fake import ProvedorFake
from app.auth.models import Auditoria, Clinica, Usuario
from app.pacientes import service as pacientes

# A consulta é amanhã às 14h, e o relógio bate exatamente no vencimento dela:
# 24 horas antes, às 14h de hoje. Não existe mais "a hora do disparo" — cada
# lembrete tem a sua, e é a hora da consulta no dia anterior.
CONSULTA = date(2026, 9, 1)
AGORA = datetime(2026, 8, 31, 14, 0)


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
    """O app ficou fora do ar e o relógio só voltou a bater às 5h da manhã.

    Atraso NOSSO não descarta lembrete: o horário foi marcado com folga, e um
    lembrete atrasado que diz a verdade ainda ajuda. Quem é descartado é o
    horário marcado depois do vencimento — o teste `marcado_em_cima` abaixo.
    """
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
    # As tres na MESMA hora de proposito: e assim que tres lembretes vencem na
    # mesma batida e formam fila. Horas diferentes virariam batidas diferentes.
    for i in range(3):
        paciente = _paciente(sessao, cenario, nome=f"PACIENTE {i}")
        _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(14, 0))
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
        _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(14, 0))

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


# --- cada lembrete tem a sua hora --------------------------------------------
#
# O modelo antigo era uma leva por dia: às 18h saía tudo que coubesse nas
# próximas 24 horas. Quem tinha consulta às 22h recebia 28 horas antes, e quem
# tinha às 8h recebia 14 horas antes — ninguém recebia as 24 horas prometidas.
# Agora o vencimento é por consulta: consulta − antecedência, e o relógio bate
# de 15 em 15 minutos até passar por ele.


def _marcado_em(sessao, agendamento, momento):
    """Reescreve quando o horário foi marcado. É `server_default=now()` no banco,
    então só dá para testar marcação tardia mexendo aqui."""
    agendamento.criado_em = momento
    sessao.flush()
    return agendamento


def test_consulta_das_21h_nao_sai_na_batida_das_18h(sessao, cenario):
    """O defeito que motivou a mudança, escrito como teste.

    Às 18h ela nem é candidata: faltam 27 horas, e a janela da reserva é a
    antecedência. É a própria janela que faz o horário — o lembrete nasce na
    batida em que vence, e não antes.
    """
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(21, 0))

    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 18, 0))

    assert provedor.enviadas == []
    assert sessao.query(Lembrete).count() == 0


def test_consulta_das_21h_sai_na_batida_das_21h(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(21, 0))

    _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 18, 0))
    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 21, 0))

    assert len(provedor.enviadas) == 1
    assert "21:00" in provedor.enviadas[0][1]


def test_duas_consultas_do_mesmo_dia_saem_em_batidas_diferentes(sessao, cenario):
    """A da manhã e a da noite não viajam juntas: cada uma tem o seu vencimento."""
    cedo = _paciente(sessao, cenario, nome="CEDO", telefone="51999990001")
    tarde = _paciente(sessao, cenario, nome="TARDE", telefone="51999990002")
    _marcar(sessao, cenario, paciente_id=cedo.id, inicio=time(8, 0))
    _marcar(sessao, cenario, paciente_id=tarde.id, inicio=time(19, 0))

    provedor = ProvedorFake()
    _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 8, 0), provedor=provedor)
    assert [numero for numero, _ in provedor.enviadas] == ["5551999990001"]

    _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 19, 0), provedor=provedor)
    assert [numero for numero, _ in provedor.enviadas] == [
        "5551999990001",
        "5551999990002",
    ]


def test_o_lembrete_guarda_a_hora_em_que_vence(sessao, cenario):
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(21, 0))

    lembretes.reservar(
        sessao, clinica_id=cenario["clinica"].id, agora=datetime(2026, 8, 31, 21, 0)
    )

    # Vai e volta pelo `timestamptz` do Postgres, que guarda em UTC: se a
    # conversão errar, a hora gravada volta três horas fora do lugar.
    lembrete = sessao.query(Lembrete).one()
    assert lembretes.parede(lembrete.agendado_para) == datetime(2026, 8, 31, 21, 0)


def test_antecedencia_diferente_de_24h_muda_o_vencimento(sessao, cenario):
    """A antecedência é o único controle do horário agora — e ela vale por
    lembrete, não por leva."""
    cenario["configuracao"].lembrete_horas_antes = 48
    sessao.flush()
    paciente = _paciente(sessao, cenario)
    _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(14, 0))

    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 8, 30, 14, 0))

    assert len(provedor.enviadas) == 1


# --- marcado em cima da hora --------------------------------------------------


def test_marcado_depois_do_vencimento_nao_recebe(sessao, cenario):
    """Marcaram às 12h de hoje uma consulta para as 9h de amanhã: 21 horas de
    antecedência, e o vencimento das 24h já tinha passado às 9h da manhã.

    Não manda. E o motivo vai para a tela, que é o que permite alguém ligar.
    """
    paciente = _paciente(sessao, cenario)
    agendamento = _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(9, 0))
    _marcado_em(sessao, agendamento, datetime(2026, 8, 31, 12, 0).astimezone())

    provedor, _ = _rodar(sessao, cenario)

    assert provedor.enviadas == []
    lembrete = sessao.query(Lembrete).one()
    assert lembrete.situacao is SituacaoLembrete.DESCARTADO
    assert lembrete.motivo == "marcado_em_cima"


def test_atraso_do_proprio_relogio_nao_vira_marcado_em_cima(sessao, cenario):
    """A distinção que faz a tela não mentir.

    Mesma consulta das 9h com o vencimento vencido há 5 horas — mas desta vez o
    horário foi marcado semana passada. Quem atrasou fomos nós, não ela: manda,
    e não vai para a tela como se ela tivesse marcado em cima da hora.
    """
    paciente = _paciente(sessao, cenario)
    agendamento = _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(9, 0))
    _marcado_em(sessao, agendamento, datetime(2026, 8, 24, 10, 0).astimezone())

    provedor, _ = _rodar(sessao, cenario)

    assert len(provedor.enviadas) == 1


def test_criado_em_vem_do_banco_em_utc_e_nao_pode_virar_descarte(sessao, cenario):
    """UTC−3, o erro que seria silencioso.

    O Postgres devolve `timestamptz` em UTC; o consultório vive três horas
    atrás. Marcar às 7h da manhã do dia 31 é `10:00+00:00` no banco. Se alguém
    comparar sem converter, 10:00 passa a ser "depois" do vencimento das 8h e a
    paciente é descartada por um erro de fuso — sem exceção, sem log, sem nada.
    """
    paciente = _paciente(sessao, cenario)
    agendamento = _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(8, 0))
    # 10:00 UTC == 07:00 na parede da clínica: uma hora ANTES do vencimento.
    _marcado_em(sessao, agendamento, datetime(2026, 8, 31, 10, 0, tzinfo=UTC))

    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 8, 0))

    assert len(provedor.enviadas) == 1


def test_parede_converte_utc_para_a_hora_do_consultorio(sessao):
    """A função sozinha, sem banco: é ela que carrega a regra de fuso."""
    assert lembretes.parede(datetime(2026, 8, 31, 10, 0, tzinfo=UTC)) == datetime(
        2026, 8, 31, 7, 0
    )


# --- remarcar -----------------------------------------------------------------


def test_remarcar_para_depois_adia_o_envio(sessao, cenario):
    """O vencimento é recalculado do horário vivo, nunca lido do que ficou
    gravado: senão a mensagem sai cinco dias antes, na hora do horário velho."""
    paciente = _paciente(sessao, cenario)
    agendamento = _marcar(sessao, cenario, paciente_id=paciente.id, inicio=time(14, 0))
    lembretes.reservar(sessao, clinica_id=cenario["clinica"].id, agora=AGORA)

    service.remarcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        agendamento_id=agendamento.id,
        dia=CONSULTA + timedelta(days=5),
        inicio=time(14, 0),
        duracao_min=30,
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
    assert lembrete.situacao is SituacaoLembrete.PENDENTE
    # E a fila se corrige sozinha, sem ninguém mexer em `remarcar`.
    assert lembretes.parede(lembrete.agendado_para) == datetime(2026, 9, 5, 14, 0)


def test_remarcado_para_perto_ainda_avisa(sessao, cenario):
    """Remarcar não é marcar em cima da hora: quem já estava na agenda com folga
    teve o horário MUDADO, e é justamente quem mais precisa ser avisada."""
    paciente = _paciente(sessao, cenario)
    agendamento = _marcar(
        sessao, cenario, paciente_id=paciente.id, dia=CONSULTA + timedelta(days=5)
    )
    service.remarcar(
        sessao,
        clinica_id=cenario["clinica"].id,
        usuario_id=cenario["usuario"].id,
        agendamento_id=agendamento.id,
        dia=CONSULTA,
        inicio=time(14, 0),
        duracao_min=30,
    )

    provedor, _ = _rodar(sessao, cenario, agora=datetime(2026, 8, 31, 20, 0))

    assert len(provedor.enviadas) == 1
