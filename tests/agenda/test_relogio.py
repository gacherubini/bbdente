"""O relógio que faz cada lembrete sair na hora dele.

Não há mais "hora do disparo": há a hora de cada paciente. Este laço bate de 15
em 15 minutos, e o que ele precisa garantir é chato e essencial — **nunca
morrer**. Relógio morto não avisa que morreu; a clínica só descobriria pelas
faltas, semanas depois.
"""

import asyncio
import inspect
import logging
import threading
from contextlib import suppress

import pytest
from fastapi.testclient import TestClient

from app import main as modulo_do_app
from app.agenda import configuracoes, relogio, tarefas
from app.main import criar_app


def _bater_ate(batida, *, quantas: int) -> list[str]:
    """Roda o laço até ele bater `quantas` vezes e devolve em que thread bateu."""
    marcas: list[str] = []

    def registrar():
        marcas.append(threading.current_thread().name)
        batida()

    async def correr():
        tarefa = asyncio.create_task(
            relogio.acompanhar(intervalo_s=0, batida=registrar)
        )
        while len(marcas) < quantas:
            await asyncio.sleep(0.01)
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa

    # Prazo curto: um laço que não bate trava a suíte inteira em silêncio.
    asyncio.run(asyncio.wait_for(correr(), timeout=5))
    return marcas


# --- nunca morrer ------------------------------------------------------------


def test_uma_batida_que_explode_nao_derruba_o_relogio(caplog):
    """Banco reiniciando, deploy no meio, rede caindo: erra esta batida e segue.

    É a garantia inteira do laço, e por isso mora numa função sozinha, sem
    `asyncio` em volta — dá para exercitar direto.
    """

    def explode():
        raise RuntimeError("banco fora do ar")

    # O nível vai explícito: outro teste da suíte pode ter mexido no logging, e
    # este teste falhando por causa disso esconderia a garantia que ele protege.
    with caplog.at_level(logging.ERROR, logger=relogio.registro.name):
        relogio.bater_sem_derrubar(explode)  # não levanta

    assert "banco fora do ar" in caplog.text
    assert any(linha.levelname == "ERROR" for linha in caplog.records), (
        "engolir em silêncio troca um relógio morto por um relógio surdo"
    )


def test_o_laco_continua_batendo_depois_de_uma_falha():
    contagem: list[int] = []

    def as_vezes_explode():
        contagem.append(1)
        if len(contagem) == 1:
            raise RuntimeError("a primeira falhou")

    marcas = _bater_ate(
        lambda: relogio.bater_sem_derrubar(as_vezes_explode), quantas=3
    )

    assert len(marcas) >= 3


def test_a_batida_nunca_roda_no_laco_de_eventos():
    """`despachar` dorme de 20 a 90 segundos entre um envio e outro — é o ritmo
    humano que evita o número ser bloqueado. Se essa pausa acontecesse no laço de
    eventos, a agenda inteira ficaria travada enquanto o lembrete de alguém sai.
    A batida vai para uma thread, e isto aqui é o que prova que vai."""
    marcas = _bater_ate(lambda: None, quantas=2)

    assert marcas, "o laço não bateu nenhuma vez"
    assert all(nome != "MainThread" for nome in marcas)


# --- quem liga o relógio -----------------------------------------------------


@pytest.fixture
def relogio_falso(monkeypatch):
    """Um laço que só anota que foi ligado e fica esperando, como o de verdade."""
    vida: list[str] = []

    async def acompanhar_de_mentira(**_):
        vida.append("subiu")
        try:
            await asyncio.Event().wait()  # nunca termina sozinho
        except asyncio.CancelledError:
            vida.append("caiu")
            raise

    monkeypatch.setattr(relogio, "acompanhar", acompanhar_de_mentira)
    return vida


def test_o_app_dos_testes_nao_liga_o_relogio(relogio_falso):
    """Teste que monta o app montaria o laço junto, e ele falaria com o banco de
    verdade por fora da transação que o teste reverte — mandando mensagem de
    mentira sobre paciente de mentira em horário nenhum."""
    with TestClient(criar_app()):
        pass

    assert relogio_falso == []


def test_ligar_o_relogio_sobe_o_laco_e_desligar_o_derruba(relogio_falso):
    """E ele morre junto com o app: laço que sobrevive ao desligamento vira um
    segundo relógio quando o app volta."""
    with TestClient(criar_app(com_relogio=True)):
        pass

    assert relogio_falso == ["subiu", "caiu"]


def test_o_app_que_o_uvicorn_carrega_e_o_que_tem_relogio():
    """Contrato: `app.main:app` — o que o `Dockerfile` manda o uvicorn abrir — é
    montado COM relógio. Sem isto, tudo aqui passaria e nada bateria em produção.
    """
    fonte = inspect.getsource(modulo_do_app)

    assert "app = criar_app(com_relogio=True)" in fonte


# --- um caminho só -----------------------------------------------------------


@pytest.mark.parametrize(
    "modulo", [relogio, tarefas, configuracoes], ids=["relogio", "endpoint", "botao"]
)
def test_os_tres_caminhos_chamam_a_mesma_funcao(modulo):
    """Contrato: o relógio, o gatilho manual e o botão "Enviar agora" passam por
    `lembretes.rodar`, nunca por uma cópia parecida.

    Se fossem três cópias, uma acabaria divergindo — e a que divergisse seria
    justamente a de emergência, que só roda no dia ruim.
    """
    fonte = inspect.getsource(modulo)

    assert "rodar(" in fonte
    assert "despachar(" not in fonte, "chamou despachar direto em vez de rodar()"
