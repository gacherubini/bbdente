from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import criar_app


def test_a_raiz_leva_para_a_lista_de_pacientes():
    with TestClient(criar_app(), follow_redirects=False) as c:
        resposta = c.get("/")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes"


def test_a_saude_continua_respondendo_sem_sessao():
    """E o que o Fly.io consulta para saber se o container subiu."""
    with TestClient(criar_app()) as c:
        assert c.get("/saude").json() == {"status": "ok"}


@pytest.mark.parametrize("arquivo", ["fly.toml", "docs/OPERACAO.md",
                                     "scripts/backup.py", "scripts/restaurar.py"])
def test_os_arquivos_de_operacao_existem(arquivo):
    assert Path(arquivo).exists(), arquivo


def test_o_fly_toml_aponta_para_o_health_check_certo():
    conteudo = Path("fly.toml").read_text(encoding="utf-8")
    assert "/saude" in conteudo
    assert "force_https" in conteudo


def test_o_manual_de_operacao_cobre_o_teste_de_restauracao():
    """Backup nunca restaurado nao conta como backup."""
    texto = Path("docs/OPERACAO.md").read_text(encoding="utf-8").lower()
    for assunto in ("backup", "restaura", "trimestral"):
        assert assunto in texto


def test_o_env_example_nao_tem_segredo_de_verdade():
    texto = Path(".env.example").read_text(encoding="utf-8")
    assert "SECRET_KEY=" in texto
    linha = next(x for x in texto.splitlines() if x.startswith("SECRET_KEY="))
    assert len(linha.split("=", 1)[1]) < 80  # e uma instrucao, nao uma chave


def test_a_imagem_leva_os_scripts_que_o_manual_manda_rodar_dentro_dela():
    """O OPERACAO.md manda criar o primeiro usuario com
    `fly ssh console -C "python -m scripts.criar_usuario ..."`. Sem `scripts/`
    dentro da imagem isso falha com ModuleNotFoundError e ninguem consegue o
    primeiro login em producao — nao ha cadastro publico, de proposito.
    """
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "COPY scripts" in dockerfile
