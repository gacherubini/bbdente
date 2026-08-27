"""O texto da mensagem, e a barreira do que nunca pode entrar nele.

Dado de saude e dado pessoal sensivel, e mensagem de WhatsApp e lida na tela de
bloqueio, no onibus, pelo marido, pela chefe. **"Consulta amanha as 14h" e um
compromisso; "canal no dente 36 amanha as 14h" e prontuario exposto na
notificacao do celular.**

Os dois testes de contrato no fim sao os que importam daqui a dois anos: eles
falham se alguem acrescentar um campo clinico ao contexto, com o motivo escrito
no docstring para ser lido ANTES de alargar.
"""

from datetime import UTC, date, datetime, time

import pytest

from app.agenda.mensagem import (
    VARIAVEIS_PERMITIDAS,
    ContextoDaMensagem,
    ModeloInvalido,
    de_agendamento,
    renderizar,
    validar,
)

CONTEXTO = ContextoDaMensagem(
    primeiro_nome="Maria",
    nome="MARIA DA SILVA",
    dia="quinta-feira, 27 de agosto",
    dia_relativo="amanhã",
    hora="14:00",
    clinica="Consultório Dra. Kátia",
    dentista="Dra. Kátia",
    endereco="Rua X, 100",
    telefone_clinica="(51) 3333-3333",
)


def test_renderiza_as_nove_variaveis():
    texto = " ".join("{" + nome + "}" for nome in sorted(VARIAVEIS_PERMITIDAS))

    saida = renderizar(texto, CONTEXTO)

    assert "{" not in saida
    assert "Maria" in saida and "14:00" in saida


def test_variavel_que_nao_existe_nao_vira_mensagem():
    """As duas alternativas sao piores: mandar `Olá {primeiro_nome}` para a
    paciente e a assinatura do robo malfeito, e apagar o marcador em silencio
    produz frase truncada sem ninguem saber por que."""
    with pytest.raises(ModeloInvalido):
        renderizar("Oi {primeiro_nome}, seu {tratamento}", CONTEXTO)


def test_variavel_permitida_mas_vazia_tambem_barra():
    """"Te espero em , amanha" e tao quebrado quanto. Uma regra so."""
    sem_endereco = ContextoDaMensagem(**{**vars(CONTEXTO), "endereco": ""})

    with pytest.raises(ModeloInvalido):
        renderizar("{clinica} — {endereco}", sem_endereco)


def test_variavel_vazia_que_o_texto_nao_usa_nao_atrapalha():
    sem_endereco = ContextoDaMensagem(**{**vars(CONTEXTO), "endereco": ""})

    assert renderizar("Oi {primeiro_nome}", sem_endereco) == "Oi Maria"


def test_chave_solta_no_texto_nao_derruba():
    """Ela escreve o texto a mao. Uma chave solta e erro de digitacao, e a
    mensagem tem de recusar em vez de estourar de um jeito diferente."""
    with pytest.raises(ModeloInvalido):
        renderizar("Oi {primeiro_nome", CONTEXTO)


def test_validar_lista_as_desconhecidas_para_a_tela():
    """Na hora de salvar o modelo o erro custa menos, e e a unica barreira que
    impede alguem de escrever `{observacao}` achando que vai funcionar."""
    assert validar("{primeiro_nome} {tratamento} {valor}") == ["tratamento", "valor"]
    assert validar("{primeiro_nome} e {hora}") == []


def _agendamento(inicio: time = time(14, 0), dia: date = date(2026, 8, 27)):
    return de_agendamento(
        nome="MARIA DA SILVA",
        dia=dia,
        inicio=inicio,
        agora=datetime(2026, 8, 26, 18, 0, tzinfo=UTC),
        clinica="Consultório Dra. Kátia",
        dentista="Dra. Kátia",
        endereco="Rua X, 100",
        telefone_clinica="(51) 3333-3333",
    )


def test_o_primeiro_nome_e_o_padrao():
    """"MARIA DA SILVA SANTOS, seu horario" soa como cobranca de banco."""
    assert _agendamento().primeiro_nome == "Maria"


def test_o_dia_sai_por_extenso_em_portugues():
    assert _agendamento().dia == "quinta-feira, 27 de agosto"


def test_dia_relativo_e_amanha_na_vespera():
    assert _agendamento().dia_relativo == "amanhã"


def test_dia_relativo_e_hoje_quando_o_disparo_atrasou():
    """A maquina nao acordou ontem e o processo so rodou as 5h da manha. Um
    lembrete atrasado que diz a verdade ainda ajuda; um que chega tarde dizendo
    "amanha" e pior que nenhum."""
    contexto = de_agendamento(
        nome="MARIA",
        dia=date(2026, 8, 27),
        inicio=time(14, 0),
        agora=datetime(2026, 8, 27, 5, 0, tzinfo=UTC),
        clinica="C",
        dentista="D",
        endereco="E",
        telefone_clinica="T",
    )

    assert contexto.dia_relativo == "hoje"


def test_horario_avulso_usa_o_nome_que_foi_digitado():
    contexto = de_agendamento(
        nome="Maria, indicação da Ana",
        dia=date(2026, 8, 27),
        inicio=time(14, 0),
        agora=datetime(2026, 8, 26, 18, 0, tzinfo=UTC),
        clinica="C",
        dentista="D",
        endereco="E",
        telefone_clinica="T",
    )

    assert contexto.primeiro_nome == "Maria,"
    assert contexto.nome == "Maria, indicação da Ana"


# --- contratos: os dois testes que importam daqui a dois anos ---------------

PROIBIDAS = {
    "tratamento", "procedimento", "dente", "regiao", "diagnostico", "anamnese",
    "valor", "divida", "parcela", "cpf", "nascimento", "observacao",
    "telefone_paciente",
}


def test_o_contexto_nao_ganha_campo_fora_da_lista():
    """Se este teste falhar porque alguem acrescentou um campo, LEIA o docstring
    de `ContextoDaMensagem` antes de mudar a lista. Dado clinico, dinheiro e
    documento nao tem campo aqui, e por isso nao tem como chegar na mensagem —
    inclusive `agendamento.observacao`, que e texto livre e e onde a informacao
    clinica vaza ("canal 36", "avaliar extracao")."""
    assert VARIAVEIS_PERMITIDAS == {
        "primeiro_nome", "nome", "dia", "dia_relativo", "hora",
        "clinica", "dentista", "endereco", "telefone_clinica",
    }
    assert not (VARIAVEIS_PERMITIDAS & PROIBIDAS)


def test_a_mensagem_nao_alcanca_o_prontuario_nem_o_dinheiro():
    """Barreira estrutural: `renderizar` recebe `ContextoDaMensagem`, nunca um
    `dict`. Um `dict` deixaria alguem escrever `**vars(agendamento)` em 2027 e
    passar no review."""
    from pathlib import Path

    fonte = Path("app/agenda/mensagem.py").read_text(encoding="utf-8")

    for proibido in ("clinico.models", "financeiro.models", "catalogo.models"):
        assert proibido not in fonte
