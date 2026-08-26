from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import rotas as auth_rotas
from app.auth.sessao import PrecisaLogar, redirecionar_para_login


def criar_app() -> FastAPI:
    app = FastAPI(title="BDDente", docs_url=None, redoc_url=None)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.add_exception_handler(PrecisaLogar, redirecionar_para_login)
    app.include_router(auth_rotas.router)

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = criar_app()
