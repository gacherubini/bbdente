"""O relogio que faz cada lembrete sair na hora dele.

Antes existia uma leva por dia: as 18h saia tudo que coubesse nas proximas 24
horas. Quem tinha consulta as 22h era avisado 28 horas antes; quem tinha as 8h,
14 horas antes. **Ninguem recebia as 24 horas prometidas.**

Agora o vencimento e por consulta — `consulta - antecedencia` — e este laco bate
de 15 em 15 minutos ate passar por ele. Nao ha "hora do disparo": ha a hora de
cada paciente.

Por que dentro do app e nao um servico de cron de fora: o relogio precisa bater
o dia inteiro, e o Evolution ja obriga a maquina a ficar de pe (`fly.toml`,
`min_machines_running = 1`). Com a maquina acordada de qualquer forma, um cron de
terceiro seria mais uma conta para manter, mais um segredo e mais uma coisa para
quebrar em silencio.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from app.agenda.lembretes import Resumo, rodar
from app.agenda.tarefas import provedor_atual
from app.auth.service import ids_de_clinica
from app.shared.db import Sessao

# 15 minutos: a consulta das 21h e avisada entre 21h00 e 21h15 da vespera. Quinze
# minutos dentro de um aviso de 24 horas nao mudam nada para a paciente, e sao
# 96 batidas por dia em vez de 1440.
INTERVALO_S = 15 * 60

registro = logging.getLogger(__name__)


def bater() -> list[Resumo]:
    """Uma batida, com sessao propria — uma passada por clinica que existe.

    `datetime.now()` sem fuso e o certo aqui, e e o unico lugar do modulo que le
    o relogio: o container roda com `TZ=America/Sao_Paulo`, entao isto e a hora
    da parede do consultorio (§4 do plano). Quem le hora de banco converte com
    `lembretes.parede()`.

    **Quais clinicas sao, quem responde e o banco.** Ate 28/08/2026 este modulo
    supunha `clinica_id = 1`; a clinica de producao tinha outro id, e cada uma
    das 96 batidas do dia morria em `ForeignKeyViolation` sem olhar um horario.
    Nenhum lembrete saiu, por dias, e a tela nao tinha como saber. Um id de
    configuracao e um palpite sobre chave primaria — e o palpite que ACERTA um
    id existente e pior, porque ai o relogio roda calado para a clinica errada.

    A mesma hora para todas: uma batida e um instante, e duas clinicas nao podem
    discordar sobre que horas sao dentro dela.
    """
    agora = datetime.now()
    provedor = provedor_atual()
    with Sessao() as sessao:
        clinicas = ids_de_clinica(sessao)
        if not clinicas:
            registro.warning("nenhuma clinica no banco; a batida nao tem para quem ir")
        return [
            rodar(sessao, clinica_id=clinica_id, agora=agora, provedor=provedor)
            for clinica_id in clinicas
        ]


def bater_sem_derrubar(batida: Callable[[], Resumo] = bater) -> None:
    """A batida que nunca levanta excecao.

    E a peca inteira da resiliencia do laco, e por isso mora sozinha: banco
    reiniciando, deploy no meio, rede caindo — nada disso pode matar o relogio,
    porque um relogio morto nao avisa que morreu. Ele erra esta batida, registra,
    e tenta de novo em quinze minutos.
    """
    try:
        batida()
    except Exception:  # noqa: BLE001 — engolir e o requisito, nao um descuido
        registro.exception("a batida do relogio falhou; tento de novo no proximo")


async def acompanhar(
    *, intervalo_s: int = INTERVALO_S, batida: Callable[[], None] | None = None
) -> None:
    """O laco. Roda enquanto o app estiver de pe.

    A batida vai para uma THREAD, e isso nao e detalhe: `despachar` dorme de 20 a
    90 segundos entre um envio e outro (o ritmo humano que evita o bloqueio do
    numero) e o SQLAlchemy daqui e sincrono. No laco de eventos, essa pausa
    congelaria o app inteiro — a tela da agenda ficaria travada enquanto o
    lembrete de alguem sai.
    """
    batida = bater_sem_derrubar if batida is None else batida
    while True:
        await asyncio.to_thread(batida)
        await asyncio.sleep(intervalo_s)
