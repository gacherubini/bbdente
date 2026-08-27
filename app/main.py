import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agenda import configuracoes as agenda_configuracoes
from app.agenda import relogio as agenda_relogio
from app.agenda import rotas as agenda_rotas
from app.agenda import tarefas as agenda_tarefas
from app.auth import rotas as auth_rotas
from app.auth.sessao import PrecisaLogar, redirecionar_para_login
from app.catalogo import rotas as catalogo_rotas
from app.clinico import api as clinico_api
from app.clinico import rotas as clinico_rotas
from app.financeiro import rotas as financeiro_rotas
from app.pacientes import api as pacientes_api
from app.pacientes import rotas as pacientes_rotas


@asynccontextmanager
async def _com_relogio(app: FastAPI):
    """Sobe o relogio dos lembretes junto do app e o derruba junto."""
    tarefa = asyncio.create_task(agenda_relogio.acompanhar())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


def criar_app(*, com_relogio: bool = False) -> FastAPI:
    """O app. O relogio nasce DESLIGADO de proposito.

    Teste que monta o app monta o laco junto, e ele iria falar com o banco de
    verdade por fora da transacao que o teste reverte — mandando mensagem de
    mentira sobre paciente de mentira em horario nenhum. Quem liga o relogio e o
    `app` la embaixo, que e o que o uvicorn carrega em producao.
    """
    app = FastAPI(
        title="BDDente",
        docs_url=None,
        redoc_url=None,
        lifespan=_com_relogio if com_relogio else None,
    )
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.add_exception_handler(PrecisaLogar, redirecionar_para_login)
    app.include_router(auth_rotas.router)
    app.include_router(pacientes_api.router)
    app.include_router(pacientes_rotas.router)
    app.include_router(clinico_api.router)
    app.include_router(clinico_rotas.router)
    app.include_router(catalogo_rotas.router)
    app.include_router(financeiro_rotas.router)
    app.include_router(agenda_rotas.router)
    app.include_router(agenda_tarefas.router)
    app.include_router(agenda_configuracoes.router)

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/pacientes", status_code=303)

    return app


app = criar_app(com_relogio=True)
