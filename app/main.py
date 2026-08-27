from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agenda import rotas as agenda_rotas
from app.auth import rotas as auth_rotas
from app.auth.sessao import PrecisaLogar, redirecionar_para_login
from app.catalogo import rotas as catalogo_rotas
from app.clinico import api as clinico_api
from app.clinico import rotas as clinico_rotas
from app.financeiro import rotas as financeiro_rotas
from app.pacientes import api as pacientes_api
from app.pacientes import rotas as pacientes_rotas


def criar_app() -> FastAPI:
    app = FastAPI(title="BDDente", docs_url=None, redoc_url=None)
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

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/pacientes", status_code=303)

    return app


app = criar_app()
