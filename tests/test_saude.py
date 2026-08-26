from fastapi.testclient import TestClient

from app.main import criar_app


def test_saude_responde_ok():
    cliente = TestClient(criar_app())

    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
