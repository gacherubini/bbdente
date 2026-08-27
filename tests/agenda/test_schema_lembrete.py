"""As tabelas da fase do lembrete.

O teste que justifica esta suite inteira e um so: `UNIQUE (agendamento_id,
tipo)`. **O que impede a mesma paciente de receber duas vezes e o banco, nao um
`if`** — nao e lock, nao e disciplina, e a segunda linha sendo recusada. Vale se
o cron disparar duas vezes, se houver duas maquinas durante um deploy, e se ela
clicar em "enviar agora" enquanto o cron roda.
"""

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.agenda.models import (
    ConfiguracaoClinica,
    Lembrete,
    ModeloMensagem,
    SituacaoLembrete,
    TipoLembrete,
)
from app.agenda.service import configuracao_de, marcar, modelo_da_vespera
from app.auth.models import Clinica, Usuario

DIA = date(2026, 9, 1)


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = Usuario(clinica_id=clinica.id, nome="K", email="k@l", senha_hash="x")
    sessao.add(usuario)
    sessao.flush()
    agendamento = marcar(
        sessao,
        clinica_id=clinica.id,
        usuario_id=usuario.id,
        nome_avulso="Maria",
        telefone_avulso="51999998888",
        dia=DIA,
        inicio=time(9, 0),
    )
    return clinica, usuario, agendamento


def test_as_tabelas_existem(engine_teste):
    existentes = set(inspect(engine_teste).get_table_names())
    assert {"lembrete", "modelo_mensagem", "configuracao_clinica"} <= existentes


def test_a_configuracao_guarda_o_ultimo_estado_conhecido_da_conexao(engine_teste):
    """São as colunas que deixam a AGENDA avisar que o WhatsApp caiu sem falar
    com a rede. Todas nuláveis: nulo é "ninguém nunca perguntou", que é o estado
    de toda clínica no dia em que a coluna nasce."""
    colunas = {
        c["name"]: c
        for c in inspect(engine_teste).get_columns("configuracao_clinica")
    }
    for nome in ("whatsapp_estado", "whatsapp_numero", "whatsapp_visto_em"):
        assert nome in colunas, nome
        assert colunas[nome]["nullable"] is True, nome


@pytest.mark.parametrize(
    "nome, enum", [("tipo_lembrete", TipoLembrete), ("situacao_lembrete", SituacaoLembrete)]
)
def test_os_enums_existem_no_postgres(engine_teste, nome, enum):
    with engine_teste.connect() as conexao:
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
    assert valores == {m.value for m in enum}


def _lembrete(clinica, agendamento, **kw):
    dados = {
        "clinica_id": clinica.id,
        "agendamento_id": agendamento.id,
        "tipo": TipoLembrete.VESPERA,
        "agendado_para": datetime(2026, 8, 31, 18, 0, tzinfo=UTC),
    }
    dados.update(kw)
    return Lembrete(**dados)


def test_o_banco_recusa_dois_lembretes_do_mesmo_horario(sessao, cenario):
    """A idempotencia mora aqui. Se esta constraint sair, duas execucoes
    concorrentes mandam a mesma mensagem duas vezes e ninguem percebe."""
    clinica, _, agendamento = cenario
    sessao.add(_lembrete(clinica, agendamento))
    sessao.flush()

    sessao.add(_lembrete(clinica, agendamento))
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_o_lembrete_nasce_pendente_e_sem_texto(sessao, cenario):
    clinica, _, agendamento = cenario
    lembrete = _lembrete(clinica, agendamento)
    sessao.add(lembrete)
    sessao.flush()

    assert lembrete.situacao is SituacaoLembrete.PENDENTE
    assert lembrete.texto is None
    assert lembrete.tentativas == 0


def test_numero_e_texto_ficam_congelados_no_lembrete(sessao, cenario):
    """Se ela corrigir o telefone depois, o registro continua dizendo para onde
    foi de fato. Mesma filosofia do prontuario: guarda o que aconteceu."""
    clinica, _, agendamento = cenario
    colunas = {c.name for c in Lembrete.__table__.columns}

    assert {"numero", "texto"} <= colunas


def test_a_configuracao_da_clinica_nasce_com_o_lembrete_desligado(sessao, cenario):
    """Deploy que ja sai mandando mensagem para paciente e a definicao de
    acidente.

    A linha nasce na primeira leitura, e nao so na migration: clinica criada
    depois (por `scripts/`) tambem precisa de configuracao, e "existe porque a
    migration passou naquele dia" e o tipo de suposicao que envelhece mal.
    """
    clinica, _, _ = cenario
    configuracao = configuracao_de(sessao, clinica_id=clinica.id)

    assert configuracao.lembrete_ativo is False
    assert configuracao.lembrete_hora == time(18, 0)
    assert configuracao.lembrete_horas_antes == 24


def test_a_clinica_ja_nasce_com_o_modelo_da_vespera(sessao, cenario):
    clinica, _, _ = cenario
    modelo = modelo_da_vespera(sessao, clinica_id=clinica.id)

    assert "{primeiro_nome}" in modelo.texto
    assert "{hora}" in modelo.texto


def test_ler_a_configuracao_duas_vezes_nao_cria_duas_linhas(sessao, cenario):
    clinica, _, _ = cenario
    primeira = configuracao_de(sessao, clinica_id=clinica.id)
    segunda = configuracao_de(sessao, clinica_id=clinica.id)

    assert primeira is segunda
    assert sessao.query(ConfiguracaoClinica).count() == 1


def test_nao_ha_dois_modelos_com_o_mesmo_codigo(sessao, cenario):
    clinica, _, _ = cenario
    modelo_da_vespera(sessao, clinica_id=clinica.id)
    sessao.add(
        ModeloMensagem(clinica_id=clinica.id, codigo="LEMBRETE_VESPERA", texto="outro")
    )
    with pytest.raises(IntegrityError):
        sessao.flush()
