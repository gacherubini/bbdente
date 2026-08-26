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


def test_o_ambiente_do_pg_dump_herda_o_path_da_maquina():
    """O backup roda na maquina da clinica (Windows) apontando para o banco do Fly
    por `fly proxy`. Um PATH fixo de Linux fazia o pg_dump nem ser encontrado."""
    import os
    from urllib.parse import urlparse

    from scripts.backup import ambiente

    env = ambiente(urlparse("postgresql://bddente:segredo@localhost:5432/bddente"))
    assert env["PGPASSWORD"] == "segredo"
    assert env.get("PATH") == os.environ.get("PATH")


def test_o_deploy_aplica_a_migration_antes_de_trocar_o_codigo():
    """`fly ssh console -C "alembic upgrade head"` roda dentro da imagem que JA
    esta no ar — a anterior, que nao contem o arquivo da migration nova. O comando
    responde sucesso e nao faz nada, e o codigo novo sobe procurando uma coluna que
    nao existe. O `release_command` roda o Alembic na imagem NOVA e antes dela
    receber transito; se falhar, o Fly aborta o deploy e a versao velha continua.
    """
    conteudo = Path("fly.toml").read_text(encoding="utf-8")
    assert "release_command" in conteudo
    assert "alembic upgrade head" in conteudo
