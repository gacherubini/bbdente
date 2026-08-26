from fastapi import FastAPI


def criar_app() -> FastAPI:
    """Fabrica da aplicacao. Cada modulo monta suas rotas aqui."""
    app = FastAPI(title="BDDente", docs_url=None, redoc_url=None)

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = criar_app()
