# BDDente MVP — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o BDDente — aplicação web que substitui o Dentalis (FoxPro, 1996–2024) — com login, cadastro de pacientes, odontograma com lançamento de tratamento, catálogo e anamnese, e migrar os 30 anos de histórico clínico da Dra. Kátia sem perder um registro.

**Architecture:** Monolito modular em FastAPI. Quatro módulos (`auth`, `pacientes`, `catalogo`, `clinico`) sobre um `shared` comum, um banco PostgreSQL, um deploy. Telas em Jinja2 renderizadas no servidor; o odontograma é a única ilha interativa (SVG + JavaScript sem framework) conversando com endpoints JSON. A migração é um pacote separado (`migracao/`) que lê o extrato imutável em SQLite e termina numa conferência bloqueante.

**Tech Stack:** Python 3.12+ · FastAPI · Uvicorn · Jinja2 · SQLAlchemy 2 · psycopg 3 · Alembic · PostgreSQL 16 · argon2-cffi · itsdangerous · fpdf2 · pytest · Docker · Fly.io

**Spec:** [`docs/superpowers/specs/2026-08-25-bddente-mvp-design.md`](../specs/2026-08-25-bddente-mvp-design.md)

**Dicionário dos dados legados:** [`dados_extraidos/DICIONARIO.md`](../../../dados_extraidos/DICIONARIO.md) — leitura obrigatória antes das Tasks 4 e 6–9.

---

## Global Constraints

Estas regras valem para **toda** task. Os requisitos de cada task incluem esta seção implicitamente.

- **Python ≥ 3.12.** O código usa `enum.StrEnum` e `X | None`.
- **PostgreSQL 16.** Enums e arrays nativos são usados no schema; não há fallback para SQLite na aplicação.
- **Nunca `DELETE` no código de aplicação.** Toda exclusão é lógica, via coluna `excluido_em`. Prontuário odontológico tem guarda mínima de 10 anos (CFO); dado de saúde é dado pessoal sensível (LGPD). Um `DELETE` em código de aplicação é motivo de reprovação em review.
- **Fronteira de módulo:** um módulo só acessa outro pela `service.py` dele. Nunca importa modelo de outro módulo, nunca faz `JOIN` em tabela de outro módulo. Violação é motivo de reprovação em review.
- **`clinica_id` obrigatório** em toda tabela raiz (`usuario`, `auditoria`, `paciente`, `categoria`, `convenio`, `procedimento`, `lancamento`, `pergunta_anamnese`). Tabelas filhas herdam pelo pai. Toda consulta filtra por `clinica_id`.
- **Nomes de domínio em português**, seguindo a spec: `paciente`, `lancamento`, `regiao`, `escopo`, `condicao`. Nomes técnicos de biblioteca ficam como são.
- **Notação de dente canônica é FDI** (`11`–`18`, `21`–`28`, `31`–`38`, `41`–`48`). O índice 1–32 do Dentalis **só existe dentro de `migracao/`**, guardado como `codigo_legado`. Nenhum código fora de `migracao/` manipula índice legado.
- **Nunca versionar dado de paciente.** `dados_extraidos/`, `*.sqlite`, `*.csv`, `*.dbf` e `.env` estão no `.gitignore`. O repositório remoto é público — um `git add -A` distraído publica prontuário. Sempre `git add` com caminhos explícitos.
- **Toda escrita gera linha em `auditoria`** (quem, o quê, quando, antes, depois). Sem exceção.
- **Identidade visual:** fundo branco, `"BDDente"` em branco sobre a lateral roxa, roxo nos detalhes e estados ativos. Não é interface roxa; é interface branca com roxo. Tokens fixos: `--roxo:#7C3AED` · `--roxo-esc:#5B21B6` · `--roxo-cl:#EDE9FE` · `--roxo-brd:#C4B5FD` · `--borda:#E2E8F0` · `--texto:#0F172A` · `--texto-fraco:#64748B`. Estados clínicos: vermelho `#DC2626` = planejado · verde `#16A34A` = realizado · azul `#2563EB` = condição existente.
- **TDD sem exceção.** Todo passo de implementação é precedido por um teste que falha. Commits frequentes, um por task no mínimo.

---

## Estrutura de arquivos

```
bddente/
  pyproject.toml                  deps, pytest, ruff
  docker-compose.yml              postgres local
  Dockerfile                      imagem de deploy
  alembic.ini                     config do Alembic
  .env.example                    variaveis, sem segredo real
  fly.toml                        deploy (Task 19)

  app/
    main.py                       criar_app(), monta rotas dos modulos
    config.py                     Config (pydantic-settings)

    shared/
      db.py                       Base, engine, Sessao, obter_sessao
      tipos.py                    Escopo, Regiao, StatusLancamento, TipoCondicao
      dentes.py                   FDI: conversao, quadrante, raizes, rotulos

    auth/
      models.py                   Clinica, Usuario, Auditoria
      senha.py                    hash e verificacao argon2
      sessao.py                   cookie assinado, dependencia usuario_atual
      auditoria.py                registrar()
      service.py                  fronteira publica do modulo
      rotas.py                    GET/POST /login, POST /logout

    pacientes/
      models.py                   Paciente, PacienteTelefone, PacienteEndereco
      telefone.py                 parser de telefone legado
      service.py                  buscar(), obter(), criar(), atualizar()
      rotas.py                    GET /pacientes

    catalogo/
      models.py                   Categoria, Convenio, Procedimento, Preco
      service.py                  arvore(), procedimento(), salvar(), preco_de()
      rotas.py                    GET/POST /tratamentos

    clinico/
      models.py                   Odontograma, Lancamento, LancamentoRegiao,
                                  Condicao, PerguntaAnamnese, RespostaAnamnese,
                                  ObservacaoClinica
      service.py                  estado_do_odontograma(), lancar(), historico(),
                                  lancamentos_do_paciente(), anamnese()
      api.py                      endpoints JSON do odontograma
      rotas.py                    GET /odontograma/{paciente_id}, /anamnese, /prontuario.pdf
      prontuario.py               geracao do PDF

    templates/
      base.html                   layout, lateral roxa, navegacao
      login.html
      pacientes.html
      odontograma.html
      tratamentos.html
      anamnese.html
    static/
      bddente.css                 tokens e componentes
      odontograma.js              ilha interativa (SVG + eventos)

  migracao/
    __main__.py                   `python -m migracao` roda tudo
    extrato.py                    leitor do SQLite imutavel
    posdente.py                   decodificador POSDENTE -> escopo + regiao
    texto.py                      limpeza de texto e datas legadas
    catalogo.py                   categorias, convenios, procedimentos, precos
    pacientes.py                  pacientes, telefones, enderecos
    lancamentos.py                lancamentos + regioes
    condicoes.py                  condicoes (ARQICONE)
    anamnese.py                   perguntas, respostas, observacoes
    conferencia.py                conferencia bloqueante final

  alembic/versions/               migrations
  tests/                          espelha a arvore de app/ e migracao/
```

**Por que essa divisão.** `shared/dentes.py` e `migracao/posdente.py` são lógica pura sem banco — testáveis em milissegundos e onde mora o risco real do projeto (espelhamento mesial/distal). Ficam isolados de propósito. `migracao/` é um pacote separado da aplicação porque roda uma vez e depois vira documentação viva: nenhuma rota importa dele.

---

## Ordem das tasks

| # | Task | Entrega |
|---|---|---|
| 1 | Esqueleto do projeto | App sobe, `/saude` responde, CI verde |
| 2 | Tipos do domínio | Enums `Escopo`, `Regiao`, `StatusLancamento`, `TipoCondicao` |
| 3 | Notação de dentes | Conversão FDI, quadrante, raízes, rótulo incisal/oclusal |
| 4 | Decodificador POSDENTE | Coordenada legada → escopo + região, com teste contra dados reais |
| 5 | Schema e Alembic | Banco completo, migration sobe e desce limpa |
| 6 | Migração: catálogo | 12 categorias, 7 convênios, 612 pares procedimento×preço, escopo sugerido |
| 7 | Migração: pacientes | 5.561 pacientes com telefones, endereços e flags de revisão |
| 8 | Migração: lançamentos | 44.812 lançamentos + 29.350 regiões |
| 9 | Migração: condições, anamnese e **conferência** | 9.629 condições, 2.046 respostas, conferência bloqueante |
| 10 | Autenticação | Login, sessão, auditoria |
| 11 | Layout base | Lateral roxa, navegação, tokens de CSS |
| 12 | Tela de pacientes | Busca, filtros, flags de dado suspeito |
| 13 | API do odontograma | JSON de estado e de lançamento |
| 14 | Odontograma (SVG) | 32 dentes clicáveis, 8 regiões, cores de estado |
| 15 | Painel de lançamento | Escolher tratamento, pré-marcação, repetir em outro dente |
| 16 | Tela de tratamentos | Catálogo por categoria, criar e editar |
| 17 | Anamnese | Questionário por paciente |
| 18 | Prontuário em PDF | Exportação (direito de acesso, LGPD) |
| 19 | Deploy, backup e restore | Fly.io, backup diário, teste de restauração |

---

# Fase 0 — Fundação

### Task 1: Esqueleto do projeto

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`, `app/config.py`, `app/main.py`
- Create: `docker-compose.yml`, `Dockerfile`, `.env.example`
- Create: `.github/workflows/ci.yml`
- Test: `tests/__init__.py`, `tests/test_saude.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `app.config.Config` — classe de configuração; instância `app.config.config`. Atributos: `database_url: str`, `database_url_teste: str`, `secret_key: str`, `sessao_horas: int`, `cookie_seguro: bool`, `clinica_id_padrao: int`, `extrato_sqlite: str`.
  - `app.main.criar_app() -> FastAPI` — fábrica da aplicação. Toda task seguinte monta suas rotas aqui.

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_saude.py`:

```python
from fastapi.testclient import TestClient

from app.main import criar_app


def test_saude_responde_ok():
    cliente = TestClient(criar_app())

    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
```

Crie também `tests/__init__.py` vazio e `app/__init__.py` vazio.

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `pytest tests/test_saude.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Criar `pyproject.toml`**

```toml
[project]
name = "bddente"
version = "0.1.0"
description = "Prontuario odontologico — substituto do Dentalis"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "jinja2>=3.1",
    "sqlalchemy>=2.0.36",
    "psycopg[binary]>=3.2",
    "alembic>=1.14",
    "argon2-cffi>=23.1",
    "itsdangerous>=2.2",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.12",
    "fpdf2>=2.8",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.28", "ruff>=0.8"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*", "migracao*"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 4: Criar `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Configuracao lida de variaveis de ambiente ou do .env local."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bddente:bddente@localhost:5432/bddente"
    database_url_teste: str = "postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste"
    secret_key: str = "troque-isto-em-producao"
    sessao_horas: int = 12
    clinica_id_padrao: int = 1
    extrato_sqlite: str = "dados_extraidos/dentalis.sqlite"
    # Em producao o cookie de sessao so viaja por HTTPS. Fica False no dev local
    # porque o navegador recusa cookie secure em http://localhost.
    cookie_seguro: bool = False


config = Config()
```

- [ ] **Step 5: Criar `app/main.py`**

```python
from fastapi import FastAPI


def criar_app() -> FastAPI:
    """Fabrica da aplicacao. Cada modulo monta suas rotas aqui."""
    app = FastAPI(title="BDDente", docs_url=None, redoc_url=None)

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = criar_app()
```

- [ ] **Step 6: Instalar e rodar o teste**

Run:
```bash
pip install -e ".[dev]"
pytest tests/test_saude.py -v
```
Expected: PASS

- [ ] **Step 7: Criar o ambiente local (Postgres)**

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: bddente
      POSTGRES_PASSWORD: bddente
      POSTGRES_DB: bddente
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bddente"]
      interval: 5s
      retries: 10

volumes:
  pgdata:
```

`.env.example`:

```
DATABASE_URL=postgresql+psycopg://bddente:bddente@localhost:5432/bddente
DATABASE_URL_TESTE=postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste
SECRET_KEY=gere-com-python-c-import-secrets-print-secrets-token-hex-32
SESSAO_HORAS=12
COOKIE_SEGURO=false
CLINICA_ID_PADRAO=1
EXTRATO_SQLITE=dados_extraidos/dentalis.sqlite
```

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY app ./app
COPY migracao ./migracao
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install -e .

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Suba o banco e confirme que ele responde:

```bash
docker compose up -d
docker compose exec db psql -U bddente -c "SELECT 1"
docker compose exec db psql -U bddente -c "CREATE DATABASE bddente_teste"
```
Expected: `?column? | 1` e depois `CREATE DATABASE`

- [ ] **Step 8: Criar o CI**

`.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]

jobs:
  testes:
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres:16
        env:
          POSTGRES_USER: bddente
          POSTGRES_PASSWORD: bddente
          POSTGRES_DB: bddente_teste
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U bddente"
          --health-interval 5s --health-retries 10
    env:
      DATABASE_URL_TESTE: postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v
```

> O CI **não** roda os testes de migração (Tasks 6–9): eles dependem do extrato com dado de paciente, que nunca entra no repositório. Esses testes se marcam sozinhos como skip quando o arquivo não existe — ver Task 6, Step 1.

- [ ] **Step 9: Rodar tudo e commitar**

Run: `ruff check . && pytest -v`
Expected: PASS, zero erros de lint

```bash
git add pyproject.toml app tests docker-compose.yml Dockerfile .env.example .github
git commit -m "feat: esqueleto do projeto com FastAPI, Postgres e CI"
```

---

### Task 2: Tipos do domínio

**Files:**
- Create: `app/shared/__init__.py`, `app/shared/tipos.py`
- Test: `tests/shared/__init__.py`, `tests/shared/test_tipos.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `app.shared.tipos.Escopo` — `StrEnum` com `BOCA`, `DENTE`, `REGIOES`.
  - `app.shared.tipos.Regiao` — `StrEnum` com `MESIAL`, `DISTAL`, `VESTIBULAR`, `LINGUAL`, `OCLUSAL`, `CANAL_MESIAL`, `CANAL_CENTRAL`, `CANAL_DISTAL`.
  - `app.shared.tipos.StatusLancamento` — `StrEnum` com `PLANEJADO`, `REALIZADO`.
  - `app.shared.tipos.TipoCondicao` — `StrEnum` com `AUSENTE`, `RESTAURACAO_ANTERIOR`, `COROA`, `IMPLANTE`, `OUTRO`.
  - `app.shared.tipos.REGIOES_COROA: frozenset[Regiao]` — as 5 da coroa.
  - `app.shared.tipos.REGIOES_RAIZ: frozenset[Regiao]` — as 3 da raiz.

- [ ] **Step 1: Escrever o teste que falha**

`tests/shared/test_tipos.py`:

```python
from app.shared.tipos import (
    REGIOES_COROA,
    REGIOES_RAIZ,
    Escopo,
    Regiao,
    StatusLancamento,
    TipoCondicao,
)


def test_coroa_e_raiz_particionam_as_regioes():
    """Toda regiao pertence a exatamente um dos dois grupos — sem sobra, sem falta."""
    assert REGIOES_COROA | REGIOES_RAIZ == set(Regiao)
    assert REGIOES_COROA & REGIOES_RAIZ == set()


def test_grupos_tem_os_tamanhos_da_spec():
    assert len(REGIOES_COROA) == 5
    assert len(REGIOES_RAIZ) == 3


def test_enums_serializam_como_o_proprio_nome():
    """Sao StrEnum: o valor gravado no banco e o nome, sem traducao no meio."""
    assert Escopo.REGIOES == "REGIOES"
    assert Regiao.CANAL_MESIAL == "CANAL_MESIAL"
    assert StatusLancamento.PLANEJADO == "PLANEJADO"
    assert TipoCondicao.AUSENTE == "AUSENTE"
    for membro in (*Escopo, *Regiao, *StatusLancamento, *TipoCondicao):
        assert membro.value == membro.name
```

Crie `tests/shared/__init__.py` vazio.

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `pytest tests/shared/test_tipos.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.shared'`

- [ ] **Step 3: Escrever a implementação mínima**

`app/shared/tipos.py`:

```python
"""Vocabulario do dominio clinico. Estes valores vao para o banco como enum nativo."""

from enum import StrEnum


class Escopo(StrEnum):
    """Onde o tratamento acontece."""

    BOCA = "BOCA"        # consulta, limpeza, protese removivel — sem dente
    DENTE = "DENTE"      # extracao, coroa, radiografia — dente inteiro
    REGIOES = "REGIOES"  # restauracao, canal — uma ou mais regioes marcadas


class Regiao(StrEnum):
    """As 8 regioes de um dente. As 5 primeiras sao coroa; as 3 ultimas, raiz."""

    MESIAL = "MESIAL"
    DISTAL = "DISTAL"
    VESTIBULAR = "VESTIBULAR"
    LINGUAL = "LINGUAL"
    OCLUSAL = "OCLUSAL"  # exibida como "Incisal" nos dentes anteriores — ver shared/dentes.py
    CANAL_MESIAL = "CANAL_MESIAL"
    CANAL_CENTRAL = "CANAL_CENTRAL"
    CANAL_DISTAL = "CANAL_DISTAL"


REGIOES_COROA = frozenset(
    {Regiao.MESIAL, Regiao.DISTAL, Regiao.VESTIBULAR, Regiao.LINGUAL, Regiao.OCLUSAL}
)
REGIOES_RAIZ = frozenset({Regiao.CANAL_MESIAL, Regiao.CANAL_CENTRAL, Regiao.CANAL_DISTAL})


class StatusLancamento(StrEnum):
    PLANEJADO = "PLANEJADO"
    REALIZADO = "REALIZADO"


class TipoCondicao(StrEnum):
    """Estado pre-existente do dente. Sem preco, sem status."""

    AUSENTE = "AUSENTE"
    RESTAURACAO_ANTERIOR = "RESTAURACAO_ANTERIOR"
    COROA = "COROA"
    IMPLANTE = "IMPLANTE"
    OUTRO = "OUTRO"  # os 309 codigos legados caem aqui ate serem traduzidos
```

Crie `app/shared/__init__.py` vazio.

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `pytest tests/shared/test_tipos.py -v`
Expected: PASS (3 testes)

- [ ] **Step 5: Commitar**

```bash
git add app/shared/__init__.py app/shared/tipos.py tests/shared
git commit -m "feat: enums do dominio clinico"
```

---

### Task 3: Notação de dentes

Esta task e a Task 4 são onde mora o risco real do projeto. Errar o espelhamento mesial/distal grava 44.812 registros invertidos. Por isso são lógica pura, sem banco, com teste exaustivo.

**Files:**
- Create: `app/shared/dentes.py`
- Test: `tests/shared/test_dentes.py`

**Interfaces:**
- Consumes: `app.shared.tipos.Regiao`, `app.shared.tipos.REGIOES_RAIZ`.
- Produces:
  - `app.shared.dentes.TODOS_FDI: tuple[int, ...]` — os 32 dentes em ordem de tela (superior esquerda→direita, depois inferior).
  - `app.shared.dentes.FDI_SUPERIOR: tuple[int, ...]` e `FDI_INFERIOR: tuple[int, ...]` — 16 cada, na ordem da tela.
  - `app.shared.dentes.fdi_de_indice_legado(indice: int) -> int`
  - `app.shared.dentes.indice_legado_de_fdi(fdi: int) -> int`
  - `app.shared.dentes.e_fdi_valido(fdi: int) -> bool`
  - `app.shared.dentes.quadrante(fdi: int) -> int` — 1 a 4.
  - `app.shared.dentes.e_anterior(fdi: int) -> bool` — incisivos e caninos.
  - `app.shared.dentes.numero_de_raizes(fdi: int) -> int` — 1, 2 ou 3.
  - `app.shared.dentes.canais_do_dente(fdi: int) -> tuple[Regiao, ...]`
  - `app.shared.dentes.rotulo_regiao(regiao: Regiao, fdi: int) -> str`

- [ ] **Step 1: Escrever o teste que falha**

`tests/shared/test_dentes.py`:

```python
import pytest

from app.shared.dentes import (
    FDI_INFERIOR,
    FDI_SUPERIOR,
    TODOS_FDI,
    canais_do_dente,
    e_anterior,
    e_fdi_valido,
    fdi_de_indice_legado,
    indice_legado_de_fdi,
    numero_de_raizes,
    quadrante,
    rotulo_regiao,
)
from app.shared.tipos import REGIOES_RAIZ, Regiao


# --- conversao indice legado 1..32 <-> FDI -------------------------------------

@pytest.mark.parametrize(
    ("indice", "fdi"),
    [
        (1, 18), (8, 11),    # superior direito: da ponta ate a linha media
        (9, 21), (16, 28),   # superior esquerdo
        (17, 48), (24, 41),  # inferior direito
        (25, 31), (32, 38),  # inferior esquerdo
    ],
)
def test_indice_legado_vira_o_fdi_certo(indice, fdi):
    assert fdi_de_indice_legado(indice) == fdi


def test_conversao_ida_e_volta_para_os_32():
    for indice in range(1, 33):
        assert indice_legado_de_fdi(fdi_de_indice_legado(indice)) == indice


def test_os_32_sao_distintos_e_todos_fdi_valido():
    assert len(TODOS_FDI) == 32
    assert len(set(TODOS_FDI)) == 32
    assert all(e_fdi_valido(f) for f in TODOS_FDI)
    assert FDI_SUPERIOR + FDI_INFERIOR == TODOS_FDI


@pytest.mark.parametrize("indice", [0, -1, 33, 100])
def test_indice_fora_de_1_a_32_e_erro(indice):
    with pytest.raises(ValueError):
        fdi_de_indice_legado(indice)


@pytest.mark.parametrize("fdi", [0, 10, 19, 29, 39, 49, 50, 11.5])
def test_numero_que_nao_e_fdi_e_rejeitado(fdi):
    assert not e_fdi_valido(fdi)
    with pytest.raises(ValueError):
        indice_legado_de_fdi(fdi)


# --- quadrante e posicao -------------------------------------------------------

@pytest.mark.parametrize(
    ("fdi", "q"), [(18, 1), (11, 1), (21, 2), (28, 2), (31, 3), (38, 3), (41, 4), (48, 4)]
)
def test_quadrante_e_a_dezena(fdi, q):
    assert quadrante(fdi) == q


def test_anteriores_sao_as_posicoes_1_a_3_dos_quatro_quadrantes():
    anteriores = {f for f in TODOS_FDI if e_anterior(f)}
    assert anteriores == {11, 12, 13, 21, 22, 23, 31, 32, 33, 41, 42, 43}


# --- raizes e canais -----------------------------------------------------------

@pytest.mark.parametrize(
    ("fdi", "n"),
    [
        (16, 3), (17, 3), (18, 3), (26, 3),  # molares superiores: 3 raizes
        (36, 2), (37, 2), (46, 2), (48, 2),  # molares inferiores: 2
        (14, 2), (24, 2),                    # primeiro pre-molar superior: 2
        (15, 1), (25, 1), (34, 1), (44, 1),  # demais pre-molares: 1
        (11, 1), (13, 1), (31, 1), (43, 1),  # anteriores: 1
    ],
)
def test_numero_de_raizes(fdi, n):
    assert numero_de_raizes(fdi) == n


def test_canais_acompanham_o_numero_de_raizes():
    assert canais_do_dente(11) == (Regiao.CANAL_CENTRAL,)
    assert canais_do_dente(14) == (Regiao.CANAL_MESIAL, Regiao.CANAL_DISTAL)
    assert canais_do_dente(16) == (
        Regiao.CANAL_MESIAL,
        Regiao.CANAL_CENTRAL,
        Regiao.CANAL_DISTAL,
    )
    for fdi in TODOS_FDI:
        canais = canais_do_dente(fdi)
        assert len(canais) == numero_de_raizes(fdi)
        assert set(canais) <= REGIOES_RAIZ


# --- rotulos de tela -----------------------------------------------------------

def test_oclusal_vira_incisal_so_nos_anteriores():
    assert rotulo_regiao(Regiao.OCLUSAL, 11) == "Incisal"
    assert rotulo_regiao(Regiao.OCLUSAL, 43) == "Incisal"
    assert rotulo_regiao(Regiao.OCLUSAL, 16) == "Oclusal"
    assert rotulo_regiao(Regiao.OCLUSAL, 24) == "Oclusal"


def test_demais_rotulos_nao_dependem_do_dente():
    assert rotulo_regiao(Regiao.LINGUAL, 11) == rotulo_regiao(Regiao.LINGUAL, 16)
    assert rotulo_regiao(Regiao.VESTIBULAR, 16) == "Vestibular"
    assert rotulo_regiao(Regiao.CANAL_MESIAL, 16) == "Canal mesial"


def test_todo_par_regiao_dente_tem_rotulo_nao_vazio():
    for fdi in TODOS_FDI:
        for regiao in Regiao:
            assert rotulo_regiao(regiao, fdi).strip()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `pytest tests/shared/test_dentes.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.shared.dentes'`

- [ ] **Step 3: Escrever a implementação**

`app/shared/dentes.py`:

```python
"""Notacao FDI e anatomia basica dos 32 dentes permanentes.

A ordem das tuplas abaixo e a ordem da tela, esquerda para direita, e e a mesma
ordem do indice sequencial 1..32 do Dentalis. Essa coincidencia e o unico motivo
pelo qual a conversao de/para o legado e uma indexacao simples.
"""

from app.shared.tipos import Regiao

FDI_SUPERIOR: tuple[int, ...] = (18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28)
FDI_INFERIOR: tuple[int, ...] = (48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38)
TODOS_FDI: tuple[int, ...] = FDI_SUPERIOR + FDI_INFERIOR

_INDICE_POR_FDI: dict[int, int] = {fdi: i + 1 for i, fdi in enumerate(TODOS_FDI)}


def e_fdi_valido(fdi: object) -> bool:
    return isinstance(fdi, int) and not isinstance(fdi, bool) and fdi in _INDICE_POR_FDI


def fdi_de_indice_legado(indice: int) -> int:
    """Converte o indice sequencial 1..32 da tela do Dentalis para FDI."""
    if not 1 <= indice <= 32:
        raise ValueError(f"indice de dente legado fora de 1..32: {indice!r}")
    return TODOS_FDI[indice - 1]


def indice_legado_de_fdi(fdi: int) -> int:
    """Converte FDI para o indice sequencial 1..32 do Dentalis."""
    if not e_fdi_valido(fdi):
        raise ValueError(f"nao e um dente FDI permanente: {fdi!r}")
    return _INDICE_POR_FDI[fdi]


def quadrante(fdi: int) -> int:
    """1 = superior direito, 2 = superior esquerdo, 3 = inferior esquerdo, 4 = inferior direito."""
    if not e_fdi_valido(fdi):
        raise ValueError(f"nao e um dente FDI permanente: {fdi!r}")
    return fdi // 10


def posicao_no_quadrante(fdi: int) -> int:
    """1 = incisivo central, ate 8 = terceiro molar (siso)."""
    if not e_fdi_valido(fdi):
        raise ValueError(f"nao e um dente FDI permanente: {fdi!r}")
    return fdi % 10


def e_anterior(fdi: int) -> bool:
    """Incisivos e caninos. Neles a face de corte chama incisal, nao oclusal."""
    return posicao_no_quadrante(fdi) <= 3


def numero_de_raizes(fdi: int) -> int:
    """Anatomia padrao: molar superior 3, molar inferior 2, primeiro pre-molar
    superior 2, todo o resto 1."""
    posicao = posicao_no_quadrante(fdi)
    superior = quadrante(fdi) in (1, 2)
    if posicao >= 6:
        return 3 if superior else 2
    if posicao == 4 and superior:
        return 2
    return 1


def canais_do_dente(fdi: int) -> tuple[Regiao, ...]:
    """As regioes de raiz que existem neste dente, em ordem mesial -> distal."""
    match numero_de_raizes(fdi):
        case 1:
            return (Regiao.CANAL_CENTRAL,)
        case 2:
            return (Regiao.CANAL_MESIAL, Regiao.CANAL_DISTAL)
        case _:
            return (Regiao.CANAL_MESIAL, Regiao.CANAL_CENTRAL, Regiao.CANAL_DISTAL)


_ROTULOS: dict[Regiao, str] = {
    Regiao.MESIAL: "Mesial",
    Regiao.DISTAL: "Distal",
    Regiao.VESTIBULAR: "Vestibular",
    Regiao.LINGUAL: "Lingual",
    Regiao.OCLUSAL: "Oclusal",
    Regiao.CANAL_MESIAL: "Canal mesial",
    Regiao.CANAL_CENTRAL: "Canal central",
    Regiao.CANAL_DISTAL: "Canal distal",
}


def rotulo_regiao(regiao: Regiao, fdi: int) -> str:
    """Nome que a tela mostra. O dado gravado e sempre OCLUSAL; 'Incisal' e derivado."""
    if regiao is Regiao.OCLUSAL and e_anterior(fdi):
        return "Incisal"
    return _ROTULOS[regiao]
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `pytest tests/shared/test_dentes.py -v`
Expected: PASS (todos os parametrizados)

- [ ] **Step 5: Commitar**

```bash
git add app/shared/dentes.py tests/shared/test_dentes.py
git commit -m "feat: notacao FDI, quadrantes, raizes e rotulos de regiao"
```

---

### Task 4: Decodificador do POSDENTE

O `POSDENTE` do Dentalis **não é um código de face** — é a coordenada de um caractere na tela de terminal original. Cada dente ocupava uma célula de 5 colunas por 5 linhas, desenhada assim (para um dente superior, raiz para cima):

```
linha ndy=+3    | | |     canais
linha ndy=+2    #####     raiz
linha ndy=+1    [ V ]     vestibular
linha ndy= 0    M O D     mesial · oclusal · distal
linha ndy=-1    [ L ]     lingual
                ^ ^ ^
             dx -1 0 +1     (canais e raiz usam dx -2 / 0 / +2)
```

`ndy` é o deslocamento vertical **normalizado para que `+` aponte sempre para a raiz** — nos dentes superiores a raiz aponta para cima na tela, nos inferiores para baixo.

**Este algoritmo já foi validado contra os 44.812 registros reais:** produz exatamente 29.350 lançamentos com escopo `REGIOES` — o número da conferência bloqueante da spec — e perde 1 único registro (`POSDENTE = "13-3"`, corrompido, já conhecido).

**Files:**
- Create: `migracao/__init__.py`, `migracao/posdente.py`
- Test: `tests/migracao/__init__.py`, `tests/migracao/test_posdente.py`

**Interfaces:**
- Consumes: `app.shared.tipos.Escopo`, `app.shared.tipos.Regiao`; `app.shared.dentes.fdi_de_indice_legado`, `app.shared.dentes.quadrante`.
- Produces:
  - `migracao.posdente.Alvo` — dataclass congelada: `escopo: Escopo`, `fdi: int | None`, `regiao: Regiao | None`, `motivos: tuple[str, ...]`.
  - `migracao.posdente.decodificar(numdente: str, posdente: str) -> Alvo`
  - `migracao.posdente.centro_da_celula(indice_legado: int) -> tuple[int, int]` — devolve `(x, y)`.
  - Códigos de motivo emitidos: `"boca_com_dente_preenchido"`, `"dente_zerado_sem_sentinela"`, `"indice_de_dente_invalido"`, `"posdente_ilegivel"`, `"posdente_fora_da_grade"`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/migracao/test_posdente.py`:

```python
import pytest

from app.shared.tipos import Escopo, Regiao
from migracao.posdente import Alvo, centro_da_celula, decodificar


# --- geometria da grade --------------------------------------------------------

@pytest.mark.parametrize(
    ("indice", "centro"),
    [
        (1, (2, 9)),     # primeira celula da fileira superior
        (2, (7, 9)),     # celulas espacadas de 5 em 5 colunas
        (16, (77, 9)),   # ultima da superior
        (17, (2, 14)),   # a inferior recomeca em x=2, linha 14
        (32, (77, 14)),
    ],
)
def test_centro_da_celula(indice, centro):
    assert centro_da_celula(indice) == centro


# --- sentinelas ----------------------------------------------------------------

def test_8888_e_boca_toda():
    alvo = decodificar("00", "8888")
    assert alvo == Alvo(Escopo.BOCA, None, None, ())


def test_8888_com_dente_preenchido_entra_como_boca_mas_fica_marcado():
    """39 registros reais tem essa contradicao. Importa como BOCA e marca."""
    alvo = decodificar("16", "8888")
    assert alvo.escopo is Escopo.BOCA
    assert alvo.fdi is None
    assert "boca_com_dente_preenchido" in alvo.motivos


def test_9999_e_o_dente_inteiro():
    alvo = decodificar("1", "9999")
    assert alvo == Alvo(Escopo.DENTE, 18, None, ())


# --- as duas metades sao alinhadas a direita ------------------------------------

def test_posdente_com_espacos_e_lido_como_duas_metades_de_2_chars():
    """'9 45' e Y=9, X=45 — NAO 945. Fazer strip na string inteira quebra 17.791
    registros. Este teste existe para impedir exatamente esse bug."""
    indice = 10  # dente 22, centro x=47, y=9
    assert centro_da_celula(indice) == (47, 9)
    assert decodificar(str(indice), " 947").regiao is Regiao.OCLUSAL


# --- as 8 regioes, num dente superior direito (indice 3 = dente 16) -------------
# centro da celula: x=12, y=9. Superior, entao ndy = -(y - 9).

@pytest.mark.parametrize(
    ("y", "x", "regiao"),
    [
        (10, 12, Regiao.LINGUAL),        # ndy=-1, dx=0
        (9, 13, Regiao.MESIAL),          # ndy= 0, dx=+1  (quadrante 1: mesial a direita)
        (9, 11, Regiao.DISTAL),          # ndy= 0, dx=-1
        (9, 12, Regiao.OCLUSAL),         # ndy= 0, dx= 0
        (8, 12, Regiao.VESTIBULAR),      # ndy=+1, dx=0
        (7, 12, Regiao.CANAL_CENTRAL),   # ndy=+2, dx=0   (linha da raiz)
        (6, 14, Regiao.CANAL_MESIAL),    # ndy=+3, dx=+2
        (6, 10, Regiao.CANAL_DISTAL),    # ndy=+3, dx=-2
    ],
)
def test_as_oito_regioes_num_dente_superior_direito(y, x, regiao):
    alvo = decodificar("3", f"{y:>2}{x:>2}")
    assert alvo.escopo is Escopo.REGIOES
    assert alvo.fdi == 16
    assert alvo.regiao is regiao


# --- espelhamento: o teste que impede inverter 44.812 registros -----------------

def test_mesial_e_distal_invertem_do_outro_lado_da_linha_media():
    """Nos quadrantes 1 e 4 a linha media fica a DIREITA na tela, entao mesial e dx+1.
    Nos quadrantes 2 e 3 ela fica a ESQUERDA, entao mesial e dx-1."""
    # indice 3 = dente 16 (quadrante 1), centro x=12
    assert decodificar("3", " 913").regiao is Regiao.MESIAL
    assert decodificar("3", " 911").regiao is Regiao.DISTAL

    # indice 14 = dente 26 (quadrante 2), centro x=67 — espelhado
    assert centro_da_celula(14) == (67, 9)
    assert decodificar("14", " 966").regiao is Regiao.MESIAL
    assert decodificar("14", " 968").regiao is Regiao.DISTAL


@pytest.mark.parametrize(
    ("indice", "fdi", "quad"), [(3, 16, 1), (14, 26, 2), (30, 36, 3), (19, 46, 4)]
)
def test_espelhamento_nos_quatro_quadrantes(indice, fdi, quad):
    from app.shared.dentes import quadrante

    assert quadrante(fdi) == quad
    xc, yc = centro_da_celula(indice)
    superior = indice <= 16
    # ndy = 0 nas duas fileiras significa y == yc
    mesial_a_direita = quad in (1, 4)
    dx_mesial = 1 if mesial_a_direita else -1

    alvo = decodificar(str(indice), f"{yc:>2}{xc + dx_mesial:>2}")
    assert alvo.fdi == fdi
    assert alvo.regiao is Regiao.MESIAL

    alvo = decodificar(str(indice), f"{yc:>2}{xc - dx_mesial:>2}")
    assert alvo.regiao is Regiao.DISTAL
    assert superior == (indice <= 16)  # sanidade do parametro


def test_inferior_tem_a_raiz_para_baixo():
    """Indice 19 = dente 46, centro (12, 14). Na fileira inferior a raiz aponta para
    baixo, entao a linha dos canais tem y MAIOR que o centro, nao menor."""
    assert centro_da_celula(19) == (12, 14)
    assert decodificar("19", "1712").regiao is Regiao.CANAL_CENTRAL   # ndy=+3
    assert decodificar("19", "1312").regiao is Regiao.LINGUAL         # ndy=-1
    assert decodificar("19", "1512").regiao is Regiao.VESTIBULAR      # ndy=+1


# --- dado ruim -----------------------------------------------------------------

def test_posdente_corrompido_vira_dente_inteiro_marcado():
    """O unico registro real fora da grade tem POSDENTE '13-3'."""
    alvo = decodificar("5", "13-3")
    assert alvo.escopo is Escopo.DENTE
    assert alvo.fdi == 14
    assert "posdente_ilegivel" in alvo.motivos


def test_coordenada_valida_mas_fora_das_posicoes_conhecidas_e_marcada():
    alvo = decodificar("3", "0199")
    assert alvo.escopo is Escopo.DENTE
    assert "posdente_fora_da_grade" in alvo.motivos


def test_indice_de_dente_invalido_vira_boca_marcada():
    alvo = decodificar("99", "9999")
    assert alvo.escopo is Escopo.BOCA
    assert "indice_de_dente_invalido" in alvo.motivos


def test_dente_zerado_sem_sentinela_de_boca_e_marcado():
    alvo = decodificar("0", "9999")
    assert alvo.escopo is Escopo.BOCA
    assert "dente_zerado_sem_sentinela" in alvo.motivos


def test_alvo_e_imutavel():
    alvo = decodificar("3", " 912")
    with pytest.raises(Exception):
        alvo.regiao = Regiao.MESIAL  # type: ignore[misc]
```

Crie `tests/migracao/__init__.py` e `migracao/__init__.py` vazios.

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `pytest tests/migracao/test_posdente.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'migracao.posdente'`

- [ ] **Step 3: Escrever a implementação**

`migracao/posdente.py`:

```python
"""Decodificador do campo POSDENTE do Dentalis.

POSDENTE nao e um codigo de face: e a coordenada de um caractere na tela do
terminal original, em dois campos de 2 chars alinhados a direita.

    POSDENTE = [ Y (chars 0-1) ][ X (chars 2-3) ]      ex.: "1467" -> Y=14, X=67

Cada dente ocupa uma celula de 5 colunas. Dentro dela, a posicao relativa ao
centro diz qual regiao foi tratada (ver o desenho no plano de implementacao,
Task 4). Validado contra os 44.812 lancamentos reais: 29.350 caem em REGIOES,
7.638 em BOCA, 7.824 em DENTE, com 1 unico registro corrompido.
"""

from dataclasses import dataclass, field

from app.shared.dentes import fdi_de_indice_legado, quadrante
from app.shared.tipos import Escopo, Regiao

SENTINELA_BOCA = "8888"
SENTINELA_DENTE = "9999"

_DENTE_ZERADO = frozenset({"", "0", "00"})
_QUADRANTES_COM_MESIAL_A_DIREITA = frozenset({1, 4})


@dataclass(frozen=True, slots=True)
class Alvo:
    """Para onde um lancamento legado aponta, ja traduzido para o dominio novo."""

    escopo: Escopo
    fdi: int | None
    regiao: Regiao | None
    motivos: tuple[str, ...] = field(default=())


def centro_da_celula(indice_legado: int) -> tuple[int, int]:
    """Coordenada (x, y) do centro da celula de tela deste dente."""
    x = ((indice_legado - 1) % 16) * 5 + 2
    y = 9 if indice_legado <= 16 else 14
    return x, y


def _proximal(dx: int, fdi: int, *, canal: bool) -> Regiao:
    """Mesial e distal dependem do quadrante: a tela e espelhada na linha media.

    Nos quadrantes 1 e 4 a linha media fica a direita na tela, entao andar para a
    direita (dx > 0) aproxima da linha media, ou seja, e mesial. Nos quadrantes
    2 e 3 e o contrario.
    """
    mesial_a_direita = quadrante(fdi) in _QUADRANTES_COM_MESIAL_A_DIREITA
    e_mesial = (dx > 0) if mesial_a_direita else (dx < 0)
    if canal:
        return Regiao.CANAL_MESIAL if e_mesial else Regiao.CANAL_DISTAL
    return Regiao.MESIAL if e_mesial else Regiao.DISTAL


def _regiao_do_deslocamento(dx: int, ndy: int, fdi: int) -> Regiao | None:
    """Traduz o deslocamento dentro da celula. None = posicao desconhecida.

    ndy ja vem normalizado: positivo aponta para a raiz nas duas fileiras.
    """
    if ndy == -1 and dx == 0:
        return Regiao.LINGUAL
    if ndy == 0:
        if dx == 0:
            return Regiao.OCLUSAL
        if dx in (-1, 1):
            return _proximal(dx, fdi, canal=False)
        return None
    if ndy == 1 and dx == 0:
        return Regiao.VESTIBULAR
    if ndy in (2, 3):  # linha da raiz e linha dos canais colapsam nas 3 regioes de raiz
        if dx == 0:
            return Regiao.CANAL_CENTRAL
        if dx in (-2, 2):
            return _proximal(dx, fdi, canal=True)
    return None


def decodificar(numdente: str, posdente: str) -> Alvo:
    """Traduz o par (NUMDENTE, POSDENTE) do Dentalis para escopo + dente + regiao."""
    dente_bruto = (numdente or "").strip()
    # NAO fazer strip no posdente: as duas metades sao alinhadas a direita e o
    # espaco a esquerda faz parte do alinhamento. " 947" e Y=9, X=47.
    pos = (posdente or "").ljust(4)[:4]
    pos_limpo = pos.strip()

    if pos_limpo == SENTINELA_BOCA:
        motivos = () if dente_bruto in _DENTE_ZERADO else ("boca_com_dente_preenchido",)
        return Alvo(Escopo.BOCA, None, None, motivos)

    if dente_bruto in _DENTE_ZERADO:
        return Alvo(Escopo.BOCA, None, None, ("dente_zerado_sem_sentinela",))

    try:
        indice = int(dente_bruto)
        fdi = fdi_de_indice_legado(indice)
    except ValueError:
        return Alvo(Escopo.BOCA, None, None, ("indice_de_dente_invalido",))

    if pos_limpo == SENTINELA_DENTE:
        return Alvo(Escopo.DENTE, fdi, None, ())

    try:
        y, x = int(pos[0:2]), int(pos[2:4])
    except ValueError:
        return Alvo(Escopo.DENTE, fdi, None, ("posdente_ilegivel",))
    if y < 0 or x < 0:
        return Alvo(Escopo.DENTE, fdi, None, ("posdente_ilegivel",))

    xc, yc = centro_da_celula(indice)
    dx = x - xc
    # normaliza para que + aponte sempre para a raiz: na fileira superior a raiz
    # fica em cima (y menor), na inferior fica embaixo (y maior)
    ndy = (yc - y) if indice <= 16 else (y - yc)

    regiao = _regiao_do_deslocamento(dx, ndy, fdi)
    if regiao is None:
        return Alvo(Escopo.DENTE, fdi, None, ("posdente_fora_da_grade",))
    return Alvo(Escopo.REGIOES, fdi, regiao, ())
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `pytest tests/migracao/test_posdente.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Rodar contra os dados reais**

Este passo confirma que o decodificador reproduz os números da conferência. Ele **depende do extrato**, que não está no repositório — pule se o arquivo não existir.

`tests/migracao/test_posdente_dados_reais.py`:

```python
"""Roda o decodificador contra os 44.812 lancamentos reais.

E o teste mais valioso do modulo: os numeros abaixo sao os mesmos da conferencia
bloqueante da spec. Se algum mudar, a migracao inteira esta errada.
"""

import os
import sqlite3
from collections import Counter

import pytest

from app.shared.tipos import Escopo, Regiao
from migracao.posdente import decodificar

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO),
    reason=f"extrato nao disponivel em {EXTRATO} (nunca e versionado — dado de paciente)",
)


@pytest.fixture(scope="module")
def contagens():
    conexao = sqlite3.connect(EXTRATO)
    escopos: Counter = Counter()
    regioes: Counter = Counter()
    motivos: Counter = Counter()
    for numdente, posdente in conexao.execute("SELECT NUMDENTE, POSDENTE FROM ARQDENTE"):
        alvo = decodificar(numdente, posdente)
        escopos[alvo.escopo] += 1
        if alvo.regiao is not None:
            regioes[alvo.regiao] += 1
        for motivo in alvo.motivos:
            motivos[motivo] += 1
    conexao.close()
    return escopos, regioes, motivos


def test_totais_por_escopo(contagens):
    escopos, _, _ = contagens
    assert sum(escopos.values()) == 44_812
    assert escopos[Escopo.REGIOES] == 29_350
    assert escopos[Escopo.BOCA] == 7_638
    assert escopos[Escopo.DENTE] == 7_824


def test_uma_regiao_por_lancamento_com_escopo_regioes(contagens):
    escopos, regioes, _ = contagens
    assert sum(regioes.values()) == escopos[Escopo.REGIOES] == 29_350


def test_apenas_um_registro_e_perdido(contagens):
    _, _, motivos = contagens
    assert motivos["posdente_ilegivel"] == 1
    assert motivos["posdente_fora_da_grade"] == 0
    assert motivos["boca_com_dente_preenchido"] == 39


def test_distribuicao_bate_com_a_anatomia(contagens):
    """A face de mastigacao e de longe a mais tratada; as duas proximais vem
    empatadas entre si, como esperado de restauracoes classe II e III."""
    _, regioes, _ = contagens
    total = sum(regioes.values())
    assert regioes[Regiao.OCLUSAL] / total == pytest.approx(0.303, abs=0.005)
    assert regioes[Regiao.MESIAL] / total == pytest.approx(0.164, abs=0.005)
    assert regioes[Regiao.DISTAL] / total == pytest.approx(0.160, abs=0.005)
    assert regioes[Regiao.VESTIBULAR] / total == pytest.approx(0.103, abs=0.005)
    assert regioes[Regiao.LINGUAL] / total == pytest.approx(0.060, abs=0.005)
    # as duas proximais sao praticamente simetricas — se uma disparar, o
    # espelhamento mesial/distal esta invertido em algum quadrante
    assert abs(regioes[Regiao.MESIAL] - regioes[Regiao.DISTAL]) < 300
```

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_posdente_dados_reais.py -v`
Expected: PASS (4 testes) — ou SKIP se o extrato não estiver na máquina

- [ ] **Step 6: Commitar**

```bash
git add migracao/__init__.py migracao/posdente.py tests/migracao
git commit -m "feat: decodificador do POSDENTE validado contra os 44.812 registros reais"
```

---

# Fase 1 — Banco

### Task 5: Schema e Alembic

**Files:**
- Create: `app/shared/db.py`, `app/shared/modelos.py`
- Create: `app/auth/__init__.py`, `app/auth/models.py`
- Create: `app/pacientes/__init__.py`, `app/pacientes/models.py`
- Create: `app/catalogo/__init__.py`, `app/catalogo/models.py`
- Create: `app/clinico/__init__.py`, `app/clinico/models.py`
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_schema_inicial.py`
- Test: `tests/conftest.py`, `tests/test_schema.py`

**Interfaces:**
- Consumes: `app.config.config`, `app.shared.tipos.*`, `app.shared.dentes.TODOS_FDI`.
- Produces:
  - `app.shared.db.Base` — base declarativa; `app.shared.db.Sessao` — `sessionmaker`; `app.shared.db.obter_sessao() -> Iterator[Session]` (dependência do FastAPI).
  - Modelos: `Clinica`, `Usuario`, `Auditoria`, `Paciente`, `PacienteTelefone`, `PacienteEndereco`, `Categoria`, `Convenio`, `Procedimento`, `Preco`, `Odontograma`, `Lancamento`, `LancamentoRegiao`, `Condicao`, `PerguntaAnamnese`, `RespostaAnamnese`, `ObservacaoClinica`.
  - Fixtures de teste: `engine_teste` (escopo sessão) e `sessao` (por teste, com rollback).

- [ ] **Step 1: Escrever o teste que falha**

`tests/conftest.py`:

```python
import os

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

URL_TESTE = os.environ.get(
    "DATABASE_URL_TESTE",
    "postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste",
)


@pytest.fixture(scope="session")
def engine_teste():
    """Sobe o schema do zero uma vez por sessao de teste, pelo proprio Alembic.

    Usar o Alembic (e nao Base.metadata.create_all) e proposital: garante que as
    migrations que vao rodar em producao sao as mesmas que os testes exercitam.
    """
    engine = create_engine(URL_TESTE)
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", URL_TESTE)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def sessao(engine_teste):
    """Uma sessao por teste, sempre revertida no fim. Testes nao se enxergam."""
    conexao = engine_teste.connect()
    transacao = conexao.begin()
    with Session(bind=conexao, expire_on_commit=False) as s:
        yield s
    transacao.rollback()
    conexao.close()
```

`tests/test_schema.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.auth.models import Clinica, Usuario
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.clinico.models import Lancamento, LancamentoRegiao, Odontograma
from app.pacientes.models import Paciente
from app.shared.tipos import Escopo, Regiao, StatusLancamento

TABELAS_ESPERADAS = {
    "clinica", "usuario", "auditoria",
    "paciente", "paciente_telefone", "paciente_endereco",
    "categoria", "convenio", "procedimento", "preco",
    "odontograma", "lancamento", "lancamento_regiao", "condicao",
    "pergunta_anamnese", "resposta_anamnese", "observacao_clinica",
}


def test_todas_as_tabelas_da_spec_existem(engine_teste):
    existentes = set(inspect(engine_teste).get_table_names())
    assert TABELAS_ESPERADAS <= existentes


def test_enums_nativos_do_postgres_existem_com_os_valores_certos(engine_teste):
    with engine_teste.connect() as conexao:
        for nome, membros in [
            ("escopo", Escopo),
            ("regiao", Regiao),
            ("status_lancamento", StatusLancamento),
        ]:
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
            assert valores == {m.value for m in membros}, nome


def test_grava_e_le_um_lancamento_completo(sessao):
    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()

    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([categoria, convenio])
    sessao.flush()

    procedimento = Procedimento(
        clinica_id=clinica.id,
        codigo="21",
        nome="Restauracao Classe II",
        categoria_id=categoria.id,
        escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.MESIAL, Regiao.OCLUSAL],
    )
    sessao.add(procedimento)
    sessao.flush()
    sessao.add(
        Preco(
            procedimento_id=procedimento.id,
            convenio_id=convenio.id,
            valor=Decimal("180.00"),
            vigente_desde=date(2026, 1, 1),
        )
    )

    paciente = Paciente(clinica_id=clinica.id, nome="Fulana de Tal")
    sessao.add(paciente)
    sessao.flush()
    odontograma = Odontograma(paciente_id=paciente.id, numero=1)
    sessao.add(odontograma)
    sessao.flush()

    lancamento = Lancamento(
        clinica_id=clinica.id,
        odontograma_id=odontograma.id,
        dente=16,
        escopo=Escopo.REGIOES,
        procedimento_id=procedimento.id,
        status=StatusLancamento.PLANEJADO,
        valor=Decimal("180.00"),
    )
    sessao.add(lancamento)
    sessao.flush()
    sessao.add_all(
        [
            LancamentoRegiao(lancamento_id=lancamento.id, regiao=Regiao.MESIAL),
            LancamentoRegiao(lancamento_id=lancamento.id, regiao=Regiao.OCLUSAL),
        ]
    )
    sessao.flush()

    lido = sessao.get(Lancamento, lancamento.id)
    assert lido is not None
    assert lido.dente == 16
    assert lido.escopo is Escopo.REGIOES
    assert {r.regiao for r in lido.regioes} == {Regiao.MESIAL, Regiao.OCLUSAL}
    assert lido.excluido_em is None


def test_array_de_enum_faz_ida_e_volta(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    categoria = Categoria(clinica_id=clinica.id, codigo="05", nome="Endodontia", ordem=5)
    sessao.add(categoria)
    sessao.flush()
    p = Procedimento(
        clinica_id=clinica.id,
        codigo="90",
        nome="Tratamento de canal",
        categoria_id=categoria.id,
        escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.CANAL_MESIAL, Regiao.CANAL_CENTRAL, Regiao.CANAL_DISTAL],
    )
    sessao.add(p)
    sessao.flush()
    sessao.expire(p)
    assert sessao.get(Procedimento, p.id).regioes_sugeridas == [
        Regiao.CANAL_MESIAL,
        Regiao.CANAL_CENTRAL,
        Regiao.CANAL_DISTAL,
    ]


def test_escopo_boca_exige_dente_nulo(sessao):
    """O banco recusa a contradicao 'boca toda, mas num dente especifico'."""
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    categoria = Categoria(clinica_id=clinica.id, codigo="01", nome="Diagnostico", ordem=1)
    sessao.add(categoria)
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="1", nome="Consulta",
        categoria_id=categoria.id, escopo_sugerido=Escopo.BOCA, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=clinica.id, nome="F")
    sessao.add_all([proc, paciente])
    sessao.flush()
    odo = Odontograma(paciente_id=paciente.id, numero=1)
    sessao.add(odo)
    sessao.flush()

    sessao.add(
        Lancamento(
            clinica_id=clinica.id, odontograma_id=odo.id, dente=16,
            escopo=Escopo.BOCA, procedimento_id=proc.id,
            status=StatusLancamento.REALIZADO, valor=Decimal("0"),
        )
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_usuario_tem_email_unico(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    for _ in range(2):
        sessao.add(
            Usuario(clinica_id=clinica.id, email="k@exemplo.com", senha_hash="x", nome="K")
        )
    with pytest.raises(IntegrityError):
        sessao.flush()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `docker compose up -d && pytest tests/test_schema.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.shared.db'`

- [ ] **Step 3: Criar `app/shared/db.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import config


class Base(DeclarativeBase):
    """Base declarativa unica. Um banco, um metadata — a fronteira entre modulos
    e de codigo, nao de schema."""


engine = create_engine(config.database_url, pool_pre_ping=True)
Sessao = sessionmaker(engine, expire_on_commit=False)


def obter_sessao() -> Iterator[Session]:
    """Dependencia do FastAPI. Commit fica a cargo de quem chama."""
    with Sessao() as sessao:
        yield sessao
```

- [ ] **Step 4: Criar os modelos de `auth`**

`app/auth/models.py` (crie também `app/auth/__init__.py` vazio):

```python
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class Clinica(Base):
    __tablename__ = "clinica"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    nome: Mapped[str] = mapped_column(String(120))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Auditoria(Base):
    """Toda escrita da aplicacao deixa uma linha aqui. Exigencia de LGPD e a unica
    forma de responder 'quem mudou este prontuario e quando'."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    acao: Mapped[str] = mapped_column(String(20))  # CRIAR | ATUALIZAR | EXCLUIR
    entidade: Mapped[str] = mapped_column(String(60))
    entidade_id: Mapped[int | None] = mapped_column()
    dados_antes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dados_depois: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
```

- [ ] **Step 5: Criar os modelos de `catalogo`**

`app/catalogo/models.py` (crie também `app/catalogo/__init__.py` vazio):

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.tipos import Escopo, Regiao

# Os tipos enum sao criados uma vez pela migration; as colunas apenas os referenciam.
ESCOPO_PG = Enum(Escopo, name="escopo", create_type=False, values_callable=lambda e: [m.value for m in e])
REGIAO_PG = Enum(Regiao, name="regiao", create_type=False, values_callable=lambda e: [m.value for m in e])


class Categoria(Base):
    __tablename__ = "categoria"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(4))
    nome: Mapped[str] = mapped_column(String(80))
    ordem: Mapped[int] = mapped_column(default=0)


class Convenio(Base):
    __tablename__ = "convenio"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(4))
    nome: Mapped[str] = mapped_column(String(80))


class Procedimento(Base):
    __tablename__ = "procedimento"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(8), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Calculados a partir do historico na migracao: o palpite inicial da tela e o
    # habito real da dentista, nao uma opiniao de quem programou.
    escopo_sugerido: Mapped[Escopo] = mapped_column(ESCOPO_PG, default=Escopo.DENTE)
    regioes_sugeridas: Mapped[list[Regiao]] = mapped_column(
        ARRAY(REGIAO_PG), default=list, server_default="{}"
    )
    duracao_min: Mapped[int | None] = mapped_column()


class Preco(Base):
    __tablename__ = "preco"

    id: Mapped[int] = mapped_column(primary_key=True)
    procedimento_id: Mapped[int] = mapped_column(ForeignKey("procedimento.id"), index=True)
    convenio_id: Mapped[int] = mapped_column(ForeignKey("convenio.id"), index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    vigente_desde: Mapped[date] = mapped_column(Date)
```

- [ ] **Step 6: Criar os modelos de `pacientes`**

`app/pacientes/models.py` (crie também `app/pacientes/__init__.py` vazio):

```python
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base


class Paciente(Base):
    __tablename__ = "paciente"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo_legado: Mapped[str | None] = mapped_column(String(10), index=True)

    nome: Mapped[str] = mapped_column(String(160), index=True)
    nascimento: Mapped[date | None] = mapped_column(Date)
    cpf: Mapped[str | None] = mapped_column(String(14))
    ci: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))
    profissao: Mapped[str | None] = mapped_column(String(60))
    estado_civil: Mapped[str | None] = mapped_column(String(30))
    indicacao: Mapped[str | None] = mapped_column(String(60))
    pai: Mapped[str | None] = mapped_column(String(120))
    mae: Mapped[str | None] = mapped_column(String(120))

    # FK declarada por nome: pacientes NAO importa o modelo Convenio. Para exibir o
    # nome do convenio, chame catalogo.service.convenio(id).
    convenio_id: Mapped[int | None] = mapped_column(ForeignKey("convenio.id"))

    cadastrado_em: Mapped[date | None] = mapped_column(Date)
    ultimo_atendimento: Mapped[date | None] = mapped_column(Date, index=True)

    # Dado suspeito e marcado, nunca corrigido no chute nem escondido.
    revisar_motivo: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    telefones: Mapped[list["PacienteTelefone"]] = relationship(
        back_populates="paciente", cascade="all"
    )
    enderecos: Mapped[list["PacienteEndereco"]] = relationship(
        back_populates="paciente", cascade="all"
    )


class PacienteTelefone(Base):
    __tablename__ = "paciente_telefone"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    numero: Mapped[str] = mapped_column(String(24))
    # O campo cru do Dentalis, guardado caso a separacao em varios numeros erre.
    numero_original: Mapped[str | None] = mapped_column(String(60))
    principal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    paciente: Mapped[Paciente] = relationship(back_populates="telefones")


class PacienteEndereco(Base):
    __tablename__ = "paciente_endereco"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(12))  # RESIDENCIAL | COMERCIAL
    logradouro: Mapped[str | None] = mapped_column(String(120))
    bairro: Mapped[str | None] = mapped_column(String(60))
    cidade: Mapped[str | None] = mapped_column(String(60))
    uf: Mapped[str | None] = mapped_column(String(2))
    cep: Mapped[str | None] = mapped_column(String(9))

    paciente: Mapped[Paciente] = relationship(back_populates="enderecos")
```

- [ ] **Step 7: Criar os modelos de `clinico`**

`app/clinico/models.py` (crie também `app/clinico/__init__.py` vazio):

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey,
    Numeric, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base
from app.shared.tipos import Escopo, Regiao, StatusLancamento, TipoCondicao

ESCOPO_PG = Enum(Escopo, name="escopo", create_type=False, values_callable=lambda e: [m.value for m in e])
REGIAO_PG = Enum(Regiao, name="regiao", create_type=False, values_callable=lambda e: [m.value for m in e])
STATUS_PG = Enum(
    StatusLancamento, name="status_lancamento", create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
TIPO_CONDICAO_PG = Enum(
    TipoCondicao, name="tipo_condicao", create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Odontograma(Base):
    """Um paciente pode ter mais de um odontograma ao longo dos anos (NUMODO no
    Dentalis: 43.887 lancamentos no numero 1, o resto espalhado ate o 5)."""

    __tablename__ = "odontograma"
    __table_args__ = (UniqueConstraint("paciente_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    numero: Mapped[int] = mapped_column(SmallInteger, default=1)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Lancamento(Base):
    """O que a dentista faz e cobra. Vermelho (planejado) ou verde (realizado)."""

    __tablename__ = "lancamento"
    __table_args__ = (
        CheckConstraint(
            "(escopo = 'BOCA') = (dente IS NULL)",
            name="ck_lancamento_dente_conforme_escopo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    odontograma_id: Mapped[int] = mapped_column(ForeignKey("odontograma.id"), index=True)

    dente: Mapped[int | None] = mapped_column(SmallInteger)  # FDI; NULL quando escopo=BOCA
    escopo: Mapped[Escopo] = mapped_column(ESCOPO_PG)
    procedimento_id: Mapped[int] = mapped_column(ForeignKey("procedimento.id"), index=True)
    status: Mapped[StatusLancamento] = mapped_column(STATUS_PG)

    data_planejada: Mapped[date | None] = mapped_column(Date, index=True)
    data_realizada: Mapped[date | None] = mapped_column(Date, index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    observacao: Mapped[str | None] = mapped_column(Text)

    codigo_legado: Mapped[str | None] = mapped_column(String(20), index=True)
    revisar_motivo: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    regioes: Mapped[list["LancamentoRegiao"]] = relationship(
        back_populates="lancamento", cascade="all"
    )


class LancamentoRegiao(Base):
    """N:N livre. Nao ha validacao de compatibilidade entre tratamento e regiao: o
    historico real mostra o mesmo tratamento em escopos diferentes, e travar
    rejeitaria dados verdadeiros."""

    __tablename__ = "lancamento_regiao"

    lancamento_id: Mapped[int] = mapped_column(
        ForeignKey("lancamento.id"), primary_key=True
    )
    regiao: Mapped[Regiao] = mapped_column(REGIAO_PG, primary_key=True)

    lancamento: Mapped[Lancamento] = relationship(back_populates="regioes")


class Condicao(Base):
    """A camada azul: estado pre-existente do dente. Sem preco, sem status."""

    __tablename__ = "condicao"

    id: Mapped[int] = mapped_column(primary_key=True)
    odontograma_id: Mapped[int] = mapped_column(ForeignKey("odontograma.id"), index=True)
    dente: Mapped[int] = mapped_column(SmallInteger)
    tipo: Mapped[TipoCondicao] = mapped_column(TIPO_CONDICAO_PG)
    regioes: Mapped[list[Regiao]] = mapped_column(
        ARRAY(REGIAO_PG), default=list, server_default="{}"
    )
    # Os 309 codigos de icone do Dentalis, preservados ate a Dra. Katia traduzi-los.
    icone_legado: Mapped[str | None] = mapped_column(String(20), index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PerguntaAnamnese(Base):
    __tablename__ = "pergunta_anamnese"
    __table_args__ = (UniqueConstraint("clinica_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(4))
    texto: Mapped[str] = mapped_column(Text)
    tipo_resposta: Mapped[int] = mapped_column(SmallInteger, default=1)
    ordem: Mapped[int] = mapped_column(default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class RespostaAnamnese(Base):
    __tablename__ = "resposta_anamnese"
    __table_args__ = (UniqueConstraint("paciente_id", "pergunta_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    pergunta_id: Mapped[int] = mapped_column(ForeignKey("pergunta_anamnese.id"))
    resposta: Mapped[str] = mapped_column(Text)
    respondido_em: Mapped[date | None] = mapped_column(Date)


class ObservacaoClinica(Base):
    __tablename__ = "observacao_clinica"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)
    texto: Mapped[str] = mapped_column(Text)
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 8: Criar `app/shared/modelos.py`**

```python
"""Reune todos os modelos num lugar so, para que o Alembic e o mapeador do
SQLAlchemy enxerguem o metadata completo.

Este e o UNICO arquivo do projeto onde modelos de modulos diferentes se encontram.
Importar `app.auth.models` de dentro de `app/clinico/` continua sendo violacao da
fronteira de modulo.
"""

from app.auth import models as auth_models
from app.catalogo import models as catalogo_models
from app.clinico import models as clinico_models
from app.pacientes import models as pacientes_models

__all__ = ["auth_models", "catalogo_models", "clinico_models", "pacientes_models"]
```

- [ ] **Step 9: Configurar o Alembic**

Run: `alembic init alembic`

Substitua a seção de URL em `alembic.ini` (deixe a linha vazia — a URL vem do `env.py`):

```ini
sqlalchemy.url =
```

Substitua o miolo de `alembic/env.py` por:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import config as config_app
from app.shared.db import Base
import app.shared.modelos  # noqa: F401  — registra todos os modelos no metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", config_app.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectavel = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectavel.connect() as conexao:
        context.configure(connection=conexao, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 10: Gerar a migration inicial e corrigir os dois pontos conhecidos**

Run:
```bash
docker compose up -d
alembic revision --autogenerate -m "schema inicial"
```

Renomeie o arquivo gerado para `alembic/versions/0001_schema_inicial.py` e ajuste `revision = "0001"`, `down_revision = None`.

**Duas correções obrigatórias no arquivo gerado.** O autogenerate erra nas duas e o teste de Step 1 pega ambas:

1. **Criar os tipos enum antes das tabelas.** Como os modelos declaram `create_type=False`, o Alembic não os cria sozinho. Adicione no início de `upgrade()`:

```python
def upgrade() -> None:
    bind = op.get_bind()
    for nome, valores in (
        ("escopo", ["BOCA", "DENTE", "REGIOES"]),
        (
            "regiao",
            ["MESIAL", "DISTAL", "VESTIBULAR", "LINGUAL", "OCLUSAL",
             "CANAL_MESIAL", "CANAL_CENTRAL", "CANAL_DISTAL"],
        ),
        ("status_lancamento", ["PLANEJADO", "REALIZADO"]),
        (
            "tipo_condicao",
            ["AUSENTE", "RESTAURACAO_ANTERIOR", "COROA", "IMPLANTE", "OUTRO"],
        ),
    ):
        postgresql.ENUM(*valores, name=nome).create(bind, checkfirst=True)

    # ... aqui segue o op.create_table(...) que o autogenerate produziu
```

e o espelho em `downgrade()`, **depois** dos `op.drop_table(...)`:

```python
    for nome in ("tipo_condicao", "status_lancamento", "regiao", "escopo"):
        postgresql.ENUM(name=nome).drop(bind, checkfirst=True)
```

Garanta o import no topo: `from sqlalchemy.dialects import postgresql`.

2. **Colunas de array de enum.** O autogenerate costuma emitir `postgresql.ARRAY(sa.Enum(...))` sem `create_type=False`, o que tenta recriar o tipo e falha com `DuplicateObject`. Troque, nas colunas `procedimento.regioes_sugeridas` e `condicao.regioes`, por:

```python
sa.Column(
    "regioes_sugeridas",
    postgresql.ARRAY(postgresql.ENUM(name="regiao", create_type=False)),
    server_default="{}",
    nullable=False,
),
```

- [ ] **Step 11: Rodar o teste e ver passar**

Run:
```bash
docker compose exec db psql -U bddente -c "CREATE DATABASE bddente_teste" || true
pytest tests/test_schema.py -v
```
Expected: PASS (6 testes)

- [ ] **Step 12: Verificar que a migration desce e sobe de novo**

Este passo é o que garante que a fixture `engine_teste` (que faz `downgrade base` antes de cada sessão) não vai quebrar daqui a três tasks.

Run:
```bash
alembic upgrade head && alembic downgrade base && alembic upgrade head
```
Expected: sem erro nas três

- [ ] **Step 13: Commitar**

```bash
git add app/shared/db.py app/shared/modelos.py app/auth app/pacientes app/catalogo app/clinico alembic alembic.ini tests/conftest.py tests/test_schema.py
git commit -m "feat: schema completo dos quatro modulos com Alembic"
```

---

# Fase 2 — Migração

As quatro tasks a seguir movem 30 anos de prontuário. **Princípios que valem para todas:**

1. **Nunca destruir.** Importa o dado como está; marca o suspeito em `revisar_motivo`.
2. **Rastreabilidade.** Todo registro guarda `codigo_legado`.
3. **Idempotente.** Reexecutável quantas vezes for preciso a partir do extrato.
4. **Falha alto.** Se a conferência final não bater, aborta sem gravar.

O extrato (`dados_extraidos/dentalis.sqlite`) **nunca entra no repositório**. Os testes destas tasks se marcam como skip quando ele não está na máquina.

### Task 6: Migração do catálogo

**Files:**
- Create: `migracao/extrato.py`, `migracao/texto.py`, `migracao/catalogo.py`
- Test: `tests/migracao/test_texto.py`, `tests/migracao/test_migracao_catalogo.py`

**Interfaces:**
- Consumes: modelos de `app.catalogo`, `app.auth.models.Clinica`; `migracao.posdente.decodificar`.
- Produces:
  - `migracao.extrato.Extrato` — abre o SQLite. Métodos: `linhas(tabela: str) -> Iterator[dict]`, `contar(tabela: str) -> int`, `fechar() -> None`. Context manager.
  - `migracao.texto.limpar(valor: str | None) -> str | None` — trim; string vazia vira `None`.
  - `migracao.texto.data_legada(valor: str | None) -> tuple[date | None, str | None]` — devolve `(data, motivo)`; `motivo` não-nulo quando a data é impossível.
  - `migracao.catalogo.migrar(sessao, extrato, clinica_id) -> ResultadoCatalogo` — dataclass com `categorias: int`, `convenios: int`, `procedimentos: int`, `precos: int`.
  - `migracao.catalogo.calcular_sugestoes(extrato) -> dict[str, tuple[Escopo, list[Regiao]]]` — chaveado por `CODSERV`.

- [ ] **Step 1: Escrever o teste de `texto` (falha)**

`tests/migracao/test_texto.py`:

```python
from datetime import date

import pytest

from migracao.texto import data_legada, limpar


@pytest.mark.parametrize(
    ("entrada", "saida"),
    [("  Fulana  ", "Fulana"), ("", None), ("   ", None), (None, None), ("X", "X")],
)
def test_limpar_tira_espaco_e_transforma_vazio_em_nulo(entrada, saida):
    assert limpar(entrada) == saida


def test_data_valida_passa_sem_motivo():
    assert data_legada("1962-04-12") == (date(1962, 4, 12), None)


def test_data_vazia_e_nula_sem_motivo():
    """Faltar data de nascimento nao e erro de digitacao: 1.574 pacientes nao tem."""
    assert data_legada("") == (None, None)
    assert data_legada(None) == (None, None)


@pytest.mark.parametrize("valor", ["1194-05-01", "2080-06-09", "9200-01-01"])
def test_data_impossivel_e_preservada_e_marcada(valor):
    """Erros de digitacao de 30 anos atras. O dado dela nao e apagado nem 'consertado'."""
    lida, motivo = data_legada(valor)
    assert lida is not None
    assert motivo == "data_suspeita"


def test_data_ilegivel_vira_nula_e_marcada():
    assert data_legada("nao-e-data") == (None, "data_ilegivel")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/migracao/test_texto.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'migracao.texto'`

- [ ] **Step 3: Implementar `migracao/texto.py`**

```python
"""Limpeza dos campos de texto e data vindos do Dentalis.

O extrato ja normalizou as datas para 'YYYY-MM-DD'; o que sobra aqui e decidir o
que fazer com as impossiveis. A regra e sempre a mesma: preserva e marca.
"""

from datetime import date

ANO_MINIMO = 1900
ANO_MAXIMO = 2035  # o Dentalis parou em 2024; nada legitimo passa disso


def limpar(valor: str | None) -> str | None:
    """Tira espacos das pontas. String vazia vira None."""
    if valor is None:
        return None
    limpo = valor.strip()
    return limpo or None


def data_legada(valor: str | None) -> tuple[date | None, str | None]:
    """Le uma data do extrato. Devolve (data, motivo_de_revisao).

    Data impossivel e devolvida assim mesmo, marcada — nunca apagada nem chutada.
    """
    bruto = limpar(valor)
    if bruto is None:
        return None, None
    try:
        lida = date.fromisoformat(bruto)
    except ValueError:
        return None, "data_ilegivel"
    if not ANO_MINIMO <= lida.year <= ANO_MAXIMO:
        return lida, "data_suspeita"
    return lida, None
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/migracao/test_texto.py -v`
Expected: PASS

- [ ] **Step 5: Escrever o teste da migração do catálogo (falha)**

`tests/migracao/test_migracao_catalogo.py`:

```python
import os

import pytest

from app.auth.models import Clinica
from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.shared.tipos import Escopo, Regiao
from migracao.catalogo import migrar
from migracao.extrato import Extrato

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO),
    reason=f"extrato nao disponivel em {EXTRATO} (nunca e versionado — dado de paciente)",
)


@pytest.fixture
def clinica(sessao):
    c = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(c)
    sessao.flush()
    return c


@pytest.fixture
def migrado(sessao, clinica):
    with Extrato(EXTRATO) as extrato:
        resultado = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return resultado


def test_traz_as_12_categorias_reais(sessao, migrado, clinica):
    """ARQESPE tem 13 linhas, mas a '00 Todas as Intervencoes' e um filtro de tela,
    nao uma categoria."""
    assert migrado.categorias == 12
    nomes = {c.nome for c in sessao.query(Categoria).filter_by(clinica_id=clinica.id)}
    assert "Dentistica" in nomes
    assert "Endodontia" in nomes
    assert not any(n.startswith("Todas") for n in nomes)


def test_traz_os_7_convenios(sessao, migrado):
    assert migrado.convenios == 7
    codigos = {c.codigo for c in sessao.query(Convenio)}
    assert codigos == {"001", "002", "003", "004", "005", "006", "051"}
    particular = sessao.query(Convenio).filter_by(codigo="001").one()
    assert particular.nome == "PARTICULAR"


def test_convenio_sem_nome_no_legado_ganha_rotulo_do_codigo(sessao, migrado):
    """003 a 006 nao tem nome em TABELAS. Inventar um nome seria mentir; usamos o
    codigo, visivelmente provisorio."""
    assert sessao.query(Convenio).filter_by(codigo="004").one().nome == "Convenio 004"


def test_traz_os_477_procedimentos_distintos_e_612_precos(sessao, migrado):
    assert migrado.procedimentos == 477
    assert migrado.precos == 612


def test_todo_procedimento_tem_categoria(sessao, migrado):
    assert sessao.query(Procedimento).filter_by(categoria_id=None).count() == 0


def test_todo_preco_aponta_para_procedimento_e_convenio_existentes(sessao, migrado):
    total = sessao.query(Preco).count()
    validos = (
        sessao.query(Preco)
        .join(Procedimento, Preco.procedimento_id == Procedimento.id)
        .join(Convenio, Preco.convenio_id == Convenio.id)
        .count()
    )
    assert validos == total == 612


def test_escopo_sugerido_vem_do_habito_real_dela(sessao, migrado):
    """Restauracao classe II e feita em parede; consulta e na boca toda. Nao e
    opiniao de quem programou: e a maioria das 44.812 ocorrencias."""
    por_nome = {
        p.nome.upper(): p for p in sessao.query(Procedimento).all()
    }
    classe_ii = next(p for n, p in por_nome.items() if "CLASSE II" in n and "III" not in n)
    assert classe_ii.escopo_sugerido is Escopo.REGIOES
    assert set(classe_ii.regioes_sugeridas) <= set(Regiao)
    assert classe_ii.regioes_sugeridas  # nao vazio

    consulta = next(p for n, p in por_nome.items() if n.startswith("CONSULTA"))
    assert consulta.escopo_sugerido is Escopo.BOCA
    assert consulta.regioes_sugeridas == []


def test_procedimento_sem_uso_no_historico_recebe_escopo_padrao(sessao, migrado):
    """477 procedimentos no catalogo, so 177 aparecem em lancamentos. Os outros nao
    tem habito para copiar — ficam em DENTE, o meio-termo."""
    sem_regioes = sessao.query(Procedimento).filter(
        Procedimento.escopo_sugerido == Escopo.DENTE
    ).count()
    assert sem_regioes > 0


def test_rodar_duas_vezes_nao_duplica(sessao, clinica, migrado):
    with Extrato(EXTRATO) as extrato:
        segundo = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert segundo.categorias == migrado.categorias
    assert sessao.query(Categoria).filter_by(clinica_id=clinica.id).count() == 12
    assert sessao.query(Procedimento).count() == 477
    assert sessao.query(Preco).count() == 612
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_catalogo.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'migracao.extrato'`

- [ ] **Step 7: Implementar `migracao/extrato.py`**

```python
"""Leitor do extrato imutavel do Dentalis.

A migracao le daqui, nunca dos .DBF originais. O extrato ja foi verificado: 100%
dos registros lidos, encoding CP1252 confirmado, zero registros deletados, zero
referencias orfas. Ver dados_extraidos/DICIONARIO.md.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType


class Extrato:
    """Acesso somente leitura ao SQLite do extrato."""

    def __init__(self, caminho: str | Path) -> None:
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f"extrato nao encontrado: {caminho}")
        self._conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        self._conexao.row_factory = sqlite3.Row

    def linhas(self, tabela: str, ordem: str | None = None) -> Iterator[dict]:
        sql = f'SELECT * FROM "{tabela}"'  # noqa: S608 — nome de tabela vem de constante
        if ordem:
            sql += f' ORDER BY "{ordem}"'
        for linha in self._conexao.execute(sql):
            yield dict(linha)

    def contar(self, tabela: str) -> int:
        return self._conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]  # noqa: S608

    def consultar(self, sql: str, parametros: tuple = ()) -> list[sqlite3.Row]:
        return list(self._conexao.execute(sql, parametros))

    def fechar(self) -> None:
        self._conexao.close()

    def __enter__(self) -> "Extrato":
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        traco: TracebackType | None,
    ) -> None:
        self.fechar()
```

- [ ] **Step 8: Implementar `migracao/catalogo.py`**

```python
"""Migra categorias, convenios, procedimentos e precos.

O ponto nao obvio: `escopo_sugerido` e `regioes_sugeridas` nao sao configuracao —
sao calculados a partir das 44.812 ocorrencias reais. O palpite inicial da tela e
literalmente o habito da Dra. Katia nos ultimos 30 anos.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Categoria, Convenio, Preco, Procedimento
from app.shared.tipos import Escopo, Regiao
from migracao.extrato import Extrato
from migracao.posdente import decodificar
from migracao.texto import limpar

# ARQESPE tem 13 linhas; '00 Todas as Intervencoes' e um filtro de tela.
CODIGO_CATEGORIA_FILTRO = "00"
CATEGORIA_PADRAO = "11"  # "Outros Servicos"
VIGENCIA_INICIAL = date(2024, 6, 26)  # ultimo dia de uso do Dentalis
# Uma regiao entra na sugestao se aparece em pelo menos 15% das ocorrencias do
# procedimento; no maximo 3, da mais frequente para a menos.
LIMIAR_SUGESTAO = 0.15
MAXIMO_REGIOES_SUGERIDAS = 3


@dataclass
class ResultadoCatalogo:
    categorias: int = 0
    convenios: int = 0
    procedimentos: int = 0
    precos: int = 0


def calcular_sugestoes(extrato: Extrato) -> dict[str, tuple[Escopo, list[Regiao]]]:
    """Para cada CODSERV, o escopo dominante e as regioes mais usadas no historico."""
    escopos: defaultdict[str, Counter] = defaultdict(Counter)
    regioes: defaultdict[str, Counter] = defaultdict(Counter)

    for linha in extrato.linhas("ARQDENTE"):
        codigo = (linha["CODSERV"] or "").strip()
        if not codigo:
            continue
        alvo = decodificar(linha["NUMDENTE"], linha["POSDENTE"])
        escopos[codigo][alvo.escopo] += 1
        if alvo.regiao is not None:
            regioes[codigo][alvo.regiao] += 1

    sugestoes: dict[str, tuple[Escopo, list[Regiao]]] = {}
    for codigo, contagem in escopos.items():
        escopo = contagem.most_common(1)[0][0]
        if escopo is not Escopo.REGIOES:
            sugestoes[codigo] = (escopo, [])
            continue
        total = sum(regioes[codigo].values())
        escolhidas = [
            regiao
            for regiao, n in regioes[codigo].most_common(MAXIMO_REGIOES_SUGERIDAS)
            if total and n / total >= LIMIAR_SUGESTAO
        ]
        # Um procedimento com escopo REGIOES sem nenhuma regiao acima do limiar
        # ainda precisa de um palpite: fica com a mais frequente.
        if not escolhidas and regioes[codigo]:
            escolhidas = [regioes[codigo].most_common(1)[0][0]]
        sugestoes[codigo] = (Escopo.REGIOES, escolhidas)
    return sugestoes


def _migrar_categorias(sessao: Session, extrato: Extrato, clinica_id: int) -> int:
    existentes = {
        c.codigo: c
        for c in sessao.scalars(select(Categoria).where(Categoria.clinica_id == clinica_id))
    }
    n = 0
    for linha in extrato.linhas("ARQESPE"):
        codigo = (limpar(linha["CODIGO"]) or "").zfill(2)
        if codigo == CODIGO_CATEGORIA_FILTRO:
            continue
        nome = limpar(linha["NOME"]) or f"Categoria {codigo}"
        if codigo in existentes:
            existentes[codigo].nome = nome
        else:
            sessao.add(
                Categoria(
                    clinica_id=clinica_id, codigo=codigo, nome=nome, ordem=int(codigo)
                )
            )
        n += 1
    sessao.flush()
    return n


def _migrar_convenios(sessao: Session, extrato: Extrato, clinica_id: int) -> int:
    existentes = {
        c.codigo: c
        for c in sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
    }
    n = 0
    for linha in extrato.linhas("TABELAS"):
        codigo = (limpar(linha["CODCONV"]) or "").zfill(3)
        # 003 a 006 nao tem nome no legado. Rotulo provisorio, visivelmente provisorio.
        nome = limpar(linha["NOMCONV"]) or f"Convenio {codigo}"
        if codigo in existentes:
            existentes[codigo].nome = nome
        else:
            sessao.add(Convenio(clinica_id=clinica_id, codigo=codigo, nome=nome))
        n += 1
    sessao.flush()
    return n


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoCatalogo:
    resultado = ResultadoCatalogo()
    resultado.categorias = _migrar_categorias(sessao, extrato, clinica_id)
    resultado.convenios = _migrar_convenios(sessao, extrato, clinica_id)

    categorias = {
        c.codigo: c.id
        for c in sessao.scalars(select(Categoria).where(Categoria.clinica_id == clinica_id))
    }
    convenios = {
        c.codigo: c.id
        for c in sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
    }
    sugestoes = calcular_sugestoes(extrato)

    procedimentos = {
        p.codigo: p
        for p in sessao.scalars(
            select(Procedimento).where(Procedimento.clinica_id == clinica_id)
        )
    }
    # V_PROCEDIMENTO consolida os 51 arquivos ARQSE### em 612 pares convenio x
    # procedimento, com 477 CODSERV distintos.
    pares = extrato.consultar(
        "SELECT CODCONV, CODSERV, DESCRICAO FROM V_PROCEDIMENTO ORDER BY CODSERV, CODCONV"
    )

    precos_existentes = {
        (p.procedimento_id, p.convenio_id) for p in sessao.scalars(select(Preco))
    }

    for par in pares:
        codigo = (limpar(par["CODSERV"]) or "").strip()
        descricao = limpar(par["DESCRICAO"]) or f"Procedimento {codigo}"
        cod_conv = (limpar(par["CODCONV"]) or "").zfill(3)

        procedimento = procedimentos.get(codigo)
        if procedimento is None:
            escopo, regioes = sugestoes.get(codigo, (Escopo.DENTE, []))
            especialidade = _especialidade_de(extrato, codigo)
            procedimento = Procedimento(
                clinica_id=clinica_id,
                codigo=codigo,
                nome=descricao,
                categoria_id=categorias.get(especialidade, categorias[CATEGORIA_PADRAO]),
                escopo_sugerido=escopo,
                regioes_sugeridas=regioes,
                duracao_min=_duracao_de(extrato, codigo),
            )
            sessao.add(procedimento)
            sessao.flush()
            procedimentos[codigo] = procedimento
            resultado.procedimentos += 1

        convenio_id = convenios.get(cod_conv)
        if convenio_id is None:
            continue
        if (procedimento.id, convenio_id) in precos_existentes:
            resultado.precos += 1
            continue
        sessao.add(
            Preco(
                procedimento_id=procedimento.id,
                convenio_id=convenio_id,
                valor=Decimal(str(_valor_de(extrato, cod_conv, codigo))),
                vigente_desde=VIGENCIA_INICIAL,
            )
        )
        precos_existentes.add((procedimento.id, convenio_id))
        resultado.precos += 1

    sessao.flush()
    if resultado.procedimentos == 0:
        # segunda execucao: nada novo criado, mas o total tem de continuar batendo
        resultado.procedimentos = sessao.query(Procedimento).count()
    return resultado


_CACHE_DETALHE: dict[tuple[str, str], dict] = {}


def _detalhe(extrato: Extrato, cod_conv: str, cod_serv: str) -> dict:
    """Le a linha crua do ARQSE### daquele convenio. Cacheia: sao 612 consultas."""
    chave = (cod_conv, cod_serv)
    if chave not in _CACHE_DETALHE:
        tabela = f"ARQSE{cod_conv}"
        linhas = extrato.consultar(
            f'SELECT * FROM "{tabela}" WHERE TRIM(CODSERV) = ?', (cod_serv,)  # noqa: S608
        )
        _CACHE_DETALHE[chave] = dict(linhas[0]) if linhas else {}
    return _CACHE_DETALHE[chave]


def _especialidade_de(extrato: Extrato, cod_serv: str) -> str:
    """A categoria vem do catalogo PARTICULAR (001), o mais completo."""
    valor = _detalhe(extrato, "001", cod_serv).get("ESPECIA")
    codigo = (limpar(str(valor)) if valor is not None else None) or CATEGORIA_PADRAO
    return codigo.zfill(2)


def _duracao_de(extrato: Extrato, cod_serv: str) -> int | None:
    valor = _detalhe(extrato, "001", cod_serv).get("TEMPO")
    try:
        minutos = int(float(valor))
    except (TypeError, ValueError):
        return None
    return minutos or None


def _valor_de(extrato: Extrato, cod_conv: str, cod_serv: str) -> float:
    valor = _detalhe(extrato, cod_conv, cod_serv).get("VALOCZ")
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0
```

- [ ] **Step 9: Rodar e ver passar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_catalogo.py -v`
Expected: PASS (9 testes)

Se `test_escopo_sugerido_vem_do_habito_real_dela` falhar por não achar um procedimento pelo nome, **não relaxe o teste**: rode
`sqlite3 dados_extraidos/dentalis.sqlite "SELECT DISTINCT DESCRICAO FROM V_PROCEDIMENTO WHERE DESCRICAO LIKE '%CLASSE%'"`
e ajuste o nome procurado para o que existe de fato.

- [ ] **Step 10: Commitar**

```bash
git add migracao/extrato.py migracao/texto.py migracao/catalogo.py tests/migracao/test_texto.py tests/migracao/test_migracao_catalogo.py
git commit -m "feat: migracao do catalogo com escopo sugerido derivado do historico"
```

---

### Task 7: Migração de pacientes

**Files:**
- Create: `migracao/telefone.py` → na verdade `app/pacientes/telefone.py` (é regra de domínio, usada também pela tela)
- Create: `migracao/pacientes.py`
- Test: `tests/pacientes/__init__.py`, `tests/pacientes/test_telefone.py`, `tests/migracao/test_migracao_pacientes.py`

**Interfaces:**
- Consumes: `migracao.extrato.Extrato`, `migracao.texto.limpar`, `migracao.texto.data_legada`; modelos de `app.pacientes`, `app.catalogo.models.Convenio`.
- Produces:
  - `app.pacientes.telefone.separar(bruto: str | None) -> list[str]` — quebra o campo único do Dentalis em números individuais.
  - `app.pacientes.telefone.formatar(numero: str) -> str` — `(51) 99999-0001`; devolve o número cru quando não reconhece o formato.
  - `app.pacientes.telefone.parecer_incompleto(numero: str) -> bool`
  - `migracao.pacientes.migrar(sessao, extrato, clinica_id) -> ResultadoPacientes` — dataclass com `pacientes: int`, `telefones: int`, `enderecos: int`, `marcados: int`.

- [ ] **Step 1: Escrever o teste do parser de telefone (falha)**

`tests/pacientes/test_telefone.py`:

```python
import pytest

from app.pacientes.telefone import formatar, parecer_incompleto, separar


def test_campo_com_varios_numeros_e_quebrado():
    """No Dentalis vem tudo num campo so, separado por barra."""
    assert separar("32671690/99684152 /84257133") == ["32671690", "99684152", "84257133"]


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("51999990001", ["51999990001"]),
        ("  9999-0002  ", ["32693124"]),
        ("", []),
        (None, []),
        ("/", []),
        ("3248-5030 / 9968-4152", ["32485030", "99684152"]),
    ],
)
def test_separar_normaliza_e_descarta_vazio(bruto, esperado):
    assert separar(bruto) == esperado


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [
        ("51999990001", "(51) 99999-0001"),
        ("51999990002", "(51) 9999-0002"),
        ("992370295", "99999-0001"),
        ("32693124", "9999-0002"),
        ("2490143", "2490143"),  # 7 digitos: nao reconhece, devolve cru
    ],
)
def test_formatar(numero, esperado):
    assert formatar(numero) == esperado


@pytest.mark.parametrize(
    ("numero", "incompleto"),
    [("2490143", True), ("32693124", False), ("51999990001", False), ("123", True)],
)
def test_parecer_incompleto(numero, incompleto):
    """Numero real do banco dela: '2490-143', com um digito a menos."""
    assert parecer_incompleto(numero) is incompleto
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/pacientes/test_telefone.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.pacientes.telefone'`

- [ ] **Step 3: Implementar `app/pacientes/telefone.py`**

```python
"""Telefones do Dentalis vinham todos num campo unico de texto livre, por exemplo
'32671690/99684152 /84257133'. Aqui separamos e formatamos — sempre guardando o
campo cru em PacienteTelefone.numero_original, caso a separacao erre."""

import re

_SEPARADORES = re.compile(r"[/;,]")
_NAO_DIGITO = re.compile(r"\D")

TAMANHO_MINIMO = 8  # fixo local sem DDD


def separar(bruto: str | None) -> list[str]:
    """Quebra o campo unico em numeros individuais, so com digitos."""
    if not bruto:
        return []
    numeros = []
    for pedaco in _SEPARADORES.split(bruto):
        digitos = _NAO_DIGITO.sub("", pedaco)
        if digitos:
            numeros.append(digitos)
    return numeros


def formatar(numero: str) -> str:
    """Formata para leitura. Devolve o numero cru quando nao reconhece o formato —
    nunca inventa digito para fazer caber."""
    match len(numero):
        case 11:
            return f"({numero[:2]}) {numero[2:7]}-{numero[7:]}"
        case 10:
            return f"({numero[:2]}) {numero[2:6]}-{numero[6:]}"
        case 9:
            return f"{numero[:5]}-{numero[5:]}"
        case 8:
            return f"{numero[:4]}-{numero[4:]}"
        case _:
            return numero


def parecer_incompleto(numero: str) -> bool:
    """Curto demais para ser um telefone valido. A tela marca; nao corrige."""
    return len(numero) < TAMANHO_MINIMO
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/pacientes/test_telefone.py -v`
Expected: PASS

- [ ] **Step 5: Escrever o teste da migração de pacientes (falha)**

`tests/migracao/test_migracao_pacientes.py`:

```python
import os

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.catalogo.models import Convenio
from app.pacientes.models import Paciente, PacienteEndereco, PacienteTelefone
from migracao.extrato import Extrato
from migracao.pacientes import migrar

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture
def migrado(sessao):
    from migracao.catalogo import migrar as migrar_catalogo

    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        migrar_catalogo(sessao, extrato, clinica.id)
        resultado = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica, resultado


def test_traz_os_5561_pacientes(sessao, migrado):
    _, resultado = migrado
    assert resultado.pacientes == 5_561
    assert sessao.query(Paciente).count() == 5_561


def test_nenhum_paciente_perde_o_codigo_legado(sessao, migrado):
    assert sessao.query(Paciente).filter(Paciente.codigo_legado.is_(None)).count() == 0
    codigos = sessao.query(func.count(func.distinct(Paciente.codigo_legado))).scalar()
    assert codigos == 5_561


def test_nenhum_paciente_fica_sem_nome(sessao, migrado):
    assert sessao.query(Paciente).filter(Paciente.nome == "").count() == 0
    assert sessao.query(Paciente).filter(Paciente.nome.is_(None)).count() == 0


def test_telefone_multiplo_vira_varias_linhas_com_o_original_guardado(sessao, migrado):
    com_varios = (
        sessao.query(PacienteTelefone.paciente_id)
        .group_by(PacienteTelefone.paciente_id)
        .having(func.count() > 1)
        .first()
    )
    assert com_varios is not None
    linhas = sessao.query(PacienteTelefone).filter_by(paciente_id=com_varios[0]).all()
    assert len({t.numero for t in linhas}) == len(linhas)
    assert all(t.numero_original for t in linhas)
    assert sum(1 for t in linhas if t.principal) == 1


def test_1574_pacientes_sem_nascimento_entram_assim_mesmo(sessao, migrado):
    """Faltar data nao e motivo para recusar o cadastro."""
    assert sessao.query(Paciente).filter(Paciente.nascimento.is_(None)).count() == 1_574


def test_data_impossivel_e_preservada_e_marcada(sessao, migrado):
    marcados = sessao.scalars(
        select(Paciente).where(Paciente.revisar_motivo.any("data_suspeita"))
    ).all()
    assert marcados, "as datas impossiveis conhecidas (1194, 2080, 9200) sumiram"
    for p in marcados:
        assert p.nascimento is not None or p.ultimo_atendimento is not None


def test_telefone_curto_e_marcado_mas_gravado(sessao, migrado):
    marcados = sessao.scalars(
        select(Paciente).where(Paciente.revisar_motivo.any("telefone_incompleto"))
    ).all()
    assert marcados
    for p in marcados:
        assert p.telefones


def test_os_dois_duplicados_conhecidos_entram_marcados(sessao, migrado):
    for codigo in ("1659/PT", "4783/PT"):
        p = sessao.scalars(
            select(Paciente).where(Paciente.codigo_legado == codigo)
        ).one()
        assert "possivel_duplicata" in p.revisar_motivo


def test_convenio_e_ligado_pelo_codigo(sessao, migrado):
    com_convenio = sessao.query(Paciente).filter(Paciente.convenio_id.isnot(None)).count()
    assert com_convenio > 0
    validos = (
        sessao.query(Paciente)
        .join(Convenio, Paciente.convenio_id == Convenio.id)
        .count()
    )
    assert validos == com_convenio


def test_endereco_residencial_e_comercial_viram_linhas_separadas(sessao, migrado):
    tipos = {t for (t,) in sessao.query(PacienteEndereco.tipo).distinct()}
    assert tipos <= {"RESIDENCIAL", "COMERCIAL"}
    assert "RESIDENCIAL" in tipos


def test_rodar_duas_vezes_nao_duplica(sessao, migrado):
    clinica, _ = migrado
    with Extrato(EXTRATO) as extrato:
        migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert sessao.query(Paciente).count() == 5_561
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_pacientes.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'migracao.pacientes'`

- [ ] **Step 7: Implementar `migracao/pacientes.py`**

```python
"""Migra os 5.561 pacientes com telefones, enderecos e marcacoes de revisao.

Regra que atravessa o arquivo inteiro: dado ruim entra marcado, nunca corrigido no
chute nem descartado. A Dra. Katia decide o que fazer com cada marcacao.
"""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Convenio
from app.pacientes.models import Paciente, PacienteEndereco, PacienteTelefone
from app.pacientes.telefone import parecer_incompleto, separar
from migracao.extrato import Extrato
from migracao.texto import data_legada, limpar


@dataclass
class ResultadoPacientes:
    pacientes: int = 0
    telefones: int = 0
    enderecos: int = 0
    marcados: int = 0


def _duplicados_por_nome(extrato: Extrato) -> set[str]:
    """Nomes que aparecem em mais de um cadastro. Sao 2 no banco real."""
    contagem: Counter = Counter()
    for linha in extrato.linhas("ARQCLIEN"):
        nome = (limpar(linha["NOME"]) or "").upper()
        if nome:
            contagem[nome] += 1
    return {nome for nome, n in contagem.items() if n > 1}


def _endereco(
    paciente_id: int, tipo: str, linha: dict, campos: tuple[str, str, str, str, str]
) -> PacienteEndereco | None:
    logradouro, bairro, cidade, uf, cep = (limpar(linha.get(c)) for c in campos)
    if not any((logradouro, bairro, cidade, uf, cep)):
        return None
    return PacienteEndereco(
        paciente_id=paciente_id,
        tipo=tipo,
        logradouro=logradouro,
        bairro=bairro,
        cidade=cidade,
        uf=(uf or "")[:2] or None,
        cep=cep,
    )


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoPacientes:
    resultado = ResultadoPacientes()

    convenios = {
        c.codigo: c.id
        for c in sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
    }
    existentes = {
        p.codigo_legado: p
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    nomes_repetidos = _duplicados_por_nome(extrato)

    for linha in extrato.linhas("ARQCLIEN", ordem="CODICLIE"):
        codigo = limpar(linha["CODICLIE"])
        if codigo in existentes:
            resultado.pacientes += 1
            continue

        motivos: list[str] = []
        nascimento, motivo_nasc = data_legada(linha["NASCIDO"])
        if motivo_nasc:
            motivos.append(motivo_nasc if motivo_nasc == "data_ilegivel" else "data_suspeita")
        ultimo, motivo_ultimo = data_legada(linha["DTSERV"])
        if motivo_ultimo == "data_suspeita" and "data_suspeita" not in motivos:
            motivos.append("data_suspeita")
        cadastrado, _ = data_legada(linha["DAT_CAD"])

        nome = limpar(linha["NOME"]) or f"(sem nome) {codigo}"
        if nome.upper() in nomes_repetidos:
            motivos.append("possivel_duplicata")

        cod_conv = (limpar(linha["CODCONV"]) or "").zfill(3)

        paciente = Paciente(
            clinica_id=clinica_id,
            codigo_legado=codigo,
            nome=nome,
            nascimento=nascimento,
            cpf=limpar(linha["CPF"]),
            ci=limpar(linha["CI"]),
            email=limpar(linha["EMAIL"]),
            profissao=limpar(linha["PROFISSAO"]),
            estado_civil=limpar(linha["ESTADOCIV"]),
            indicacao=limpar(linha["INDICACAO"]),
            pai=limpar(linha["PAI"]),
            mae=limpar(linha["MAE"]),
            convenio_id=convenios.get(cod_conv),
            cadastrado_em=cadastrado,
            ultimo_atendimento=ultimo,
        )
        sessao.add(paciente)
        sessao.flush()
        existentes[codigo] = paciente
        resultado.pacientes += 1

        bruto_residencial = linha["TELEFONE"]
        bruto_comercial = linha["TELECOM"]
        primeiro = True
        for bruto in (bruto_residencial, bruto_comercial):
            for numero in separar(bruto):
                if parecer_incompleto(numero) and "telefone_incompleto" not in motivos:
                    motivos.append("telefone_incompleto")
                sessao.add(
                    PacienteTelefone(
                        paciente_id=paciente.id,
                        numero=numero,
                        numero_original=limpar(bruto),
                        principal=primeiro,
                    )
                )
                resultado.telefones += 1
                primeiro = False

        for tipo, campos in (
            ("RESIDENCIAL", ("ENDERECO", "BAIRRO", "CIDADE", "UF", "CEP")),
            ("COMERCIAL", ("ENDCOM", "BAICOM", "CIDCOM", "UFCOM", "CEPCOM")),
        ):
            endereco = _endereco(paciente.id, tipo, linha, campos)
            if endereco is not None:
                sessao.add(endereco)
                resultado.enderecos += 1

        if motivos:
            paciente.revisar_motivo = motivos
            resultado.marcados += 1

    sessao.flush()
    return resultado
```

- [ ] **Step 8: Rodar e ver passar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_pacientes.py -v`
Expected: PASS (11 testes)

- [ ] **Step 9: Commitar**

```bash
git add app/pacientes/telefone.py migracao/pacientes.py tests/pacientes tests/migracao/test_migracao_pacientes.py
git commit -m "feat: migracao dos 5.561 pacientes com marcacao de dado suspeito"
```

---

### Task 8: Migração dos lançamentos

A task de maior volume: 44.812 lançamentos e 29.350 regiões.

**Files:**
- Create: `migracao/lancamentos.py`
- Test: `tests/migracao/test_migracao_lancamentos.py`

**Interfaces:**
- Consumes: `migracao.posdente.decodificar`, `migracao.texto.data_legada`; modelos de `app.clinico` e `app.catalogo`.
- Produces:
  - `migracao.lancamentos.migrar(sessao, extrato, clinica_id) -> ResultadoLancamentos` — dataclass com `odontogramas: int`, `lancamentos: int`, `regioes: int`, `marcados: int`, `soma_valores: Decimal`.
  - `migracao.lancamentos.STATUS_LEGADO: dict[str, StatusLancamento]` — `R` → `REALIZADO`, `E` e `J` → `PLANEJADO`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/migracao/test_migracao_lancamentos.py`:

```python
import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.clinico.models import Lancamento, LancamentoRegiao, Odontograma
from app.pacientes.models import Paciente
from app.shared.dentes import TODOS_FDI
from app.shared.tipos import Escopo, Regiao, StatusLancamento
from migracao.extrato import Extrato
from migracao.lancamentos import migrar

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture(scope="module")
def _aviso():
    """Esta migracao le 44.812 linhas: leva alguns segundos. E proposital que rode
    contra o volume real — e o unico jeito de saber que aguenta."""


@pytest.fixture
def migrado(sessao):
    from migracao.catalogo import migrar as migrar_catalogo
    from migracao.pacientes import migrar as migrar_pacientes

    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        migrar_catalogo(sessao, extrato, clinica.id)
        migrar_pacientes(sessao, extrato, clinica.id)
        resultado = migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica, resultado


def test_traz_os_44812_lancamentos(sessao, migrado):
    _, resultado = migrado
    assert resultado.lancamentos == 44_812
    assert sessao.query(Lancamento).count() == 44_812


def test_traz_exatamente_29350_regioes(sessao, migrado):
    """Cada POSDENTE e uma unica celula da grade, entao e exatamente uma regiao por
    lancamento migrado com escopo REGIOES."""
    _, resultado = migrado
    assert resultado.regioes == 29_350
    assert sessao.query(LancamentoRegiao).count() == 29_350


def test_a_soma_dos_valores_bate_ao_centavo(sessao, migrado):
    total = sessao.query(func.coalesce(func.sum(Lancamento.valor), 0)).scalar()
    assert Decimal(total) == Decimal("3461389.07")


def test_distribuicao_por_escopo(sessao, migrado):
    contagem = dict(
        sessao.query(Lancamento.escopo, func.count()).group_by(Lancamento.escopo).all()
    )
    assert contagem[Escopo.REGIOES] == 29_350
    assert contagem[Escopo.BOCA] == 7_638
    assert contagem[Escopo.DENTE] == 7_824


def test_distribuicao_por_status(sessao, migrado):
    contagem = dict(
        sessao.query(Lancamento.status, func.count()).group_by(Lancamento.status).all()
    )
    assert contagem[StatusLancamento.REALIZADO] == 37_034
    assert contagem[StatusLancamento.PLANEJADO] == 7_764 + 14  # 'E' + os 14 'J'


def test_todo_dente_gravado_e_fdi_valido(sessao, migrado):
    dentes = {
        d for (d,) in sessao.query(Lancamento.dente).distinct() if d is not None
    }
    assert dentes <= set(TODOS_FDI)


def test_boca_nao_tem_dente_e_o_resto_tem(sessao, migrado):
    assert (
        sessao.query(Lancamento)
        .filter(Lancamento.escopo == Escopo.BOCA, Lancamento.dente.isnot(None))
        .count()
        == 0
    )
    assert (
        sessao.query(Lancamento)
        .filter(Lancamento.escopo != Escopo.BOCA, Lancamento.dente.is_(None))
        .count()
        == 0
    )


def test_regiao_so_existe_quando_o_escopo_e_regioes(sessao, migrado):
    fora = (
        sessao.query(LancamentoRegiao)
        .join(Lancamento, LancamentoRegiao.lancamento_id == Lancamento.id)
        .filter(Lancamento.escopo != Escopo.REGIOES)
        .count()
    )
    assert fora == 0


def test_nenhum_lancamento_orfao(sessao, migrado):
    total = sessao.query(Lancamento).count()
    ligados = (
        sessao.query(Lancamento)
        .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
        .join(Paciente, Odontograma.paciente_id == Paciente.id)
        .count()
    )
    assert ligados == total


def test_os_39_registros_contraditorios_entram_marcados(sessao, migrado):
    """POSDENTE dizia 'boca toda' mas o dente estava preenchido."""
    marcados = sessao.scalars(
        select(Lancamento).where(
            Lancamento.revisar_motivo.any("boca_com_dente_preenchido")
        )
    ).all()
    assert len(marcados) == 39
    assert all(m.escopo is Escopo.BOCA and m.dente is None for m in marcados)


def test_o_unico_posdente_corrompido_entra_como_dente_inteiro_marcado(sessao, migrado):
    marcados = sessao.scalars(
        select(Lancamento).where(Lancamento.revisar_motivo.any("posdente_ilegivel"))
    ).all()
    assert len(marcados) == 1
    assert marcados[0].escopo is Escopo.DENTE
    assert marcados[0].dente is not None


def test_os_dois_codserv_desconhecidos_viram_procedimento_marcado(sessao, migrado):
    """CODSERV 'P1' e 'P4' nao existem em nenhuma tabela de preco. Criamos um
    procedimento visivelmente provisorio em vez de descartar o lancamento."""
    from app.catalogo.models import Procedimento

    desconhecidos = sessao.scalars(
        select(Procedimento).where(Procedimento.nome.like("DESCONHECIDO%"))
    ).all()
    assert {p.codigo for p in desconhecidos} == {"P1", "P4"}


def test_multiplos_odontogramas_por_paciente_sao_preservados(sessao, migrado):
    """NUMODO no Dentalis vai de 1 a 5."""
    numeros = {n for (n,) in sessao.query(Odontograma.numero).distinct()}
    assert numeros >= {1, 2}
    com_varios = (
        sessao.query(Odontograma.paciente_id)
        .group_by(Odontograma.paciente_id)
        .having(func.count() > 1)
        .count()
    )
    assert com_varios > 0


def test_rodar_duas_vezes_nao_duplica(sessao, migrado):
    clinica, _ = migrado
    with Extrato(EXTRATO) as extrato:
        migrar(sessao, extrato, clinica.id)
    sessao.flush()
    assert sessao.query(Lancamento).count() == 44_812
    assert sessao.query(LancamentoRegiao).count() == 29_350
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_lancamentos.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'migracao.lancamentos'`

- [ ] **Step 3: Implementar `migracao/lancamentos.py`**

```python
"""Migra os 44.812 lancamentos e as 29.350 regioes.

O ARQDENTE nao tem chave primaria propria. A identidade de um lancamento aqui e
(CODICLIE, NUMODO, NUMDENTE, CODSERV, DTSERV, ordem-na-leitura), gravada em
codigo_legado — e o que torna a migracao idempotente.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Lancamento, LancamentoRegiao, Odontograma
from app.pacientes.models import Paciente
from app.shared.tipos import Escopo, Regiao, StatusLancamento
from migracao.extrato import Extrato
from migracao.posdente import decodificar
from migracao.texto import data_legada, limpar

# 'J' aparece em 14 registros, todos com valor zero e sem data de realizacao.
# Significado perdido junto com a interface do Dentalis: entra como planejado e marcado.
STATUS_LEGADO: dict[str, StatusLancamento] = {
    "R": StatusLancamento.REALIZADO,
    "E": StatusLancamento.PLANEJADO,
    "J": StatusLancamento.PLANEJADO,
}
CATEGORIA_PADRAO = "11"  # "Outros Servicos"


@dataclass
class ResultadoLancamentos:
    odontogramas: int = 0
    lancamentos: int = 0
    regioes: int = 0
    marcados: int = 0
    soma_valores: Decimal = field(default_factory=lambda: Decimal("0"))


def _valor(bruto) -> Decimal:
    try:
        return Decimal(str(bruto or 0)).quantize(Decimal("0.01"))
    except (TypeError, ArithmeticError):
        return Decimal("0.00")


def _procedimento_desconhecido(
    sessao: Session, clinica_id: int, codigo: str, categoria_id: int
) -> Procedimento:
    """CODSERV que nao existe em nenhuma tabela de preco. Sao 2 registros reais.
    Criar um procedimento provisorio preserva o lancamento; descartar perderia dado."""
    proc = Procedimento(
        clinica_id=clinica_id,
        codigo=codigo,
        nome=f"DESCONHECIDO (cod. {codigo})",
        categoria_id=categoria_id,
        ativo=False,
        escopo_sugerido=Escopo.DENTE,
        regioes_sugeridas=[],
    )
    sessao.add(proc)
    sessao.flush()
    return proc


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoLancamentos:
    resultado = ResultadoLancamentos()

    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    procedimentos = {
        p.codigo: p.id
        for p in sessao.scalars(
            select(Procedimento).where(Procedimento.clinica_id == clinica_id)
        )
    }
    categoria_padrao = sessao.scalars(
        select(Categoria).where(
            Categoria.clinica_id == clinica_id, Categoria.codigo == CATEGORIA_PADRAO
        )
    ).one().id

    odontogramas: dict[tuple[int, int], int] = {
        (o.paciente_id, o.numero): o.id for o in sessao.scalars(select(Odontograma))
    }
    ja_migrados = {
        codigo
        for (codigo,) in sessao.query(Lancamento.codigo_legado).filter(
            Lancamento.clinica_id == clinica_id, Lancamento.codigo_legado.isnot(None)
        )
    }

    for ordem, linha in enumerate(extrato.linhas("ARQDENTE")):
        codigo_paciente = limpar(linha["CODICLIE"])
        paciente_id = pacientes.get(codigo_paciente)
        if paciente_id is None:
            # O extrato ja provou ter zero referencias orfas; se aparecer uma, e
            # bug de codigo, nao dado ruim. Falha alto.
            raise ValueError(f"lancamento aponta para paciente inexistente: {codigo_paciente!r}")

        codigo_legado = f"{codigo_paciente}#{ordem}"
        if codigo_legado in ja_migrados:
            resultado.lancamentos += 1
            continue

        numero_odo = int(float(linha["NUMODO"] or 1)) or 1
        chave = (paciente_id, numero_odo)
        if chave not in odontogramas:
            odontograma = Odontograma(paciente_id=paciente_id, numero=numero_odo)
            sessao.add(odontograma)
            sessao.flush()
            odontogramas[chave] = odontograma.id
            resultado.odontogramas += 1

        alvo = decodificar(linha["NUMDENTE"], linha["POSDENTE"])
        motivos = list(alvo.motivos)

        cod_serv = (limpar(linha["CODSERV"]) or "").strip()
        procedimento_id = procedimentos.get(cod_serv)
        if procedimento_id is None:
            proc = _procedimento_desconhecido(
                sessao, clinica_id, cod_serv or "?", categoria_padrao
            )
            procedimentos[cod_serv] = proc.id
            procedimento_id = proc.id
            motivos.append("procedimento_desconhecido")

        situacao = (limpar(linha["SITUACAO"]) or "").upper()
        status = STATUS_LEGADO.get(situacao, StatusLancamento.PLANEJADO)
        if situacao not in ("R", "E"):
            motivos.append("situacao_desconhecida")

        planejada, motivo_p = data_legada(linha["DTSERV"])
        realizada, motivo_r = data_legada(linha["DTREAL"])
        for motivo in (motivo_p, motivo_r):
            if motivo and motivo not in motivos:
                motivos.append(motivo)

        valor = _valor(linha["CZSERV"])
        lancamento = Lancamento(
            clinica_id=clinica_id,
            odontograma_id=odontogramas[chave],
            dente=alvo.fdi,
            escopo=alvo.escopo,
            procedimento_id=procedimento_id,
            status=status,
            data_planejada=planejada,
            data_realizada=realizada,
            valor=valor,
            observacao=limpar(linha["OBSERV"]),
            codigo_legado=codigo_legado,
            revisar_motivo=motivos,
        )
        sessao.add(lancamento)
        sessao.flush()

        if alvo.regiao is not None:
            sessao.add(
                LancamentoRegiao(lancamento_id=lancamento.id, regiao=alvo.regiao)
            )
            resultado.regioes += 1

        resultado.lancamentos += 1
        resultado.soma_valores += valor
        if motivos:
            resultado.marcados += 1

        if resultado.lancamentos % 5_000 == 0:
            sessao.flush()

    sessao.flush()
    return resultado
```

> **Nota de desempenho.** Este laço faz um `flush()` por lançamento para obter o `id`
> antes de gravar a região. São 44.812 idas ao banco: leva algo entre 1 e 3 minutos
> localmente. É aceitável para uma migração que roda uma vez. **Não troque por
> `bulk_insert_mappings` para acelerar** sem primeiro ter o teste desta task passando:
> o custo de errar aqui é um prontuário de 30 anos gravado torto.

- [ ] **Step 4: Rodar e ver passar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_lancamentos.py -v`
Expected: PASS (14 testes). Leva alguns minutos.

- [ ] **Step 5: Commitar**

```bash
git add migracao/lancamentos.py tests/migracao/test_migracao_lancamentos.py
git commit -m "feat: migracao dos 44.812 lancamentos e 29.350 regioes"
```

---

### Task 9: Condições, anamnese e conferência bloqueante

**Files:**
- Create: `migracao/condicoes.py`, `migracao/anamnese.py`, `migracao/conferencia.py`, `migracao/__main__.py`
- Test: `tests/migracao/test_migracao_completa.py`

**Interfaces:**
- Consumes: tudo das Tasks 6–8.
- Produces:
  - `migracao.condicoes.migrar(sessao, extrato, clinica_id) -> int`
  - `migracao.anamnese.migrar(sessao, extrato, clinica_id) -> ResultadoAnamnese` — `perguntas: int`, `respostas: int`, `observacoes: int`.
  - `migracao.conferencia.conferir(sessao, clinica_id) -> list[str]` — devolve a lista de divergências; vazia significa aprovado.
  - `migracao.conferencia.ConferenciaFalhou` — exceção.
  - `migracao.__main__` — `python -m migracao` roda tudo numa transação e só faz commit se a conferência passar.

- [ ] **Step 1: Escrever o teste que falha**

`tests/migracao/test_migracao_completa.py`:

```python
import os

import pytest
from sqlalchemy import func, select

from app.auth.models import Clinica
from app.clinico.models import (
    Condicao, Lancamento, LancamentoRegiao, ObservacaoClinica,
    Odontograma, PerguntaAnamnese, RespostaAnamnese,
)
from app.pacientes.models import Paciente
from app.shared.dentes import TODOS_FDI
from app.shared.tipos import TipoCondicao
from migracao.conferencia import ConferenciaFalhou, conferir
from migracao.extrato import Extrato

EXTRATO = os.environ.get("EXTRATO_SQLITE", "dados_extraidos/dentalis.sqlite")

pytestmark = pytest.mark.skipif(
    not os.path.exists(EXTRATO), reason=f"extrato nao disponivel em {EXTRATO}"
)


@pytest.fixture
def tudo_migrado(sessao):
    from migracao import anamnese, catalogo, condicoes, lancamentos, pacientes

    clinica = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(clinica)
    sessao.flush()
    with Extrato(EXTRATO) as extrato:
        catalogo.migrar(sessao, extrato, clinica.id)
        pacientes.migrar(sessao, extrato, clinica.id)
        lancamentos.migrar(sessao, extrato, clinica.id)
        condicoes.migrar(sessao, extrato, clinica.id)
        anamnese.migrar(sessao, extrato, clinica.id)
    sessao.flush()
    return clinica


def test_traz_as_9629_condicoes(sessao, tudo_migrado):
    assert sessao.query(Condicao).count() == 9_629


def test_condicao_guarda_o_codigo_de_icone_original(sessao, tudo_migrado):
    """Os 309 codigos nao foram traduzidos ainda — precisam da Dra. Katia. Ate la,
    entram como OUTRO com o codigo preservado."""
    sem_icone = sessao.query(Condicao).filter(Condicao.icone_legado.is_(None)).count()
    assert sem_icone == 0
    assert sessao.query(Condicao).filter_by(tipo=TipoCondicao.OUTRO).count() == 9_629
    top = (
        sessao.query(Condicao.icone_legado, func.count())
        .group_by(Condicao.icone_legado)
        .order_by(func.count().desc())
        .first()
    )
    assert top[0] == "OICO14"
    assert top[1] == 2_859


def test_condicao_com_dente_sentinela_nao_vira_dente_invalido(sessao, tudo_migrado):
    """ARQICONE tem NUMDENTE ate '88'. So entram as que apontam para dente real."""
    dentes = {d for (d,) in sessao.query(Condicao.dente).distinct()}
    assert dentes <= set(TODOS_FDI)


def test_traz_as_37_perguntas_e_2046_respostas(sessao, tudo_migrado):
    assert sessao.query(PerguntaAnamnese).count() == 37
    assert sessao.query(RespostaAnamnese).count() == 2_046


def test_traz_as_80_observacoes_com_texto(sessao, tudo_migrado):
    assert sessao.query(ObservacaoClinica).count() == 80


def test_a_conferencia_aprova_a_migracao_completa(sessao, tudo_migrado):
    assert conferir(sessao, tudo_migrado.id) == []


def test_a_conferencia_reprova_quando_falta_registro(sessao, tudo_migrado):
    """Este teste e o motivo de a conferencia existir: ela tem de gritar."""
    algum = sessao.scalars(select(Paciente).limit(1)).one()
    sessao.query(LancamentoRegiao).filter(
        LancamentoRegiao.lancamento_id.in_(
            select(Lancamento.id)
            .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
            .where(Odontograma.paciente_id == algum.id)
        )
    ).delete(synchronize_session=False)
    sessao.flush()

    divergencias = conferir(sessao, tudo_migrado.id)
    assert divergencias
    assert any("lancamento_regiao" in d for d in divergencias)


def test_conferencia_falhou_e_uma_excecao_com_a_lista_dentro():
    erro = ConferenciaFalhou(["paciente: esperado 5561, encontrado 5560"])
    assert erro.divergencias == ["paciente: esperado 5561, encontrado 5560"]
    assert "5560" in str(erro)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_completa.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'migracao.conferencia'`

- [ ] **Step 3: Implementar `migracao/condicoes.py`**

```python
"""Migra a camada azul do odontograma: o que ja existia no dente antes.

Os 309 codigos de icone do Dentalis (OICO14, d01RX, d08i2...) nao foram traduzidos:
sabemos o dente e a frequencia, nao o significado. Ate a Dra. Katia interpretar —
cerca de 10 codigos cobrem quase tudo — entram como OUTRO com o codigo preservado.
Traduzir no chute seria inventar diagnostico.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinico.models import Condicao, Odontograma
from app.pacientes.models import Paciente
from app.shared.dentes import fdi_de_indice_legado
from app.shared.tipos import TipoCondicao
from migracao.extrato import Extrato
from migracao.texto import limpar


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> int:
    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    odontogramas = {
        (o.paciente_id, o.numero): o.id for o in sessao.scalars(select(Odontograma))
    }
    ja_existem = sessao.query(Condicao).count()
    if ja_existem:
        return ja_existem

    total = 0
    for linha in extrato.linhas("ARQICONE"):
        paciente_id = pacientes.get(limpar(linha["CODICLIE"]))
        if paciente_id is None:
            continue

        bruto = limpar(linha["NUMDENTE"]) or ""
        try:
            fdi = fdi_de_indice_legado(int(bruto))
        except ValueError:
            # ARQICONE tem NUMDENTE ate '88' (sentinela de tela). Sem dente real,
            # a condicao nao tem onde ser desenhada.
            continue

        numero_odo = int(float(linha["NUMODO"] or 1)) or 1
        chave = (paciente_id, numero_odo)
        if chave not in odontogramas:
            odontograma = Odontograma(paciente_id=paciente_id, numero=numero_odo)
            sessao.add(odontograma)
            sessao.flush()
            odontogramas[chave] = odontograma.id

        sessao.add(
            Condicao(
                odontograma_id=odontogramas[chave],
                dente=fdi,
                tipo=TipoCondicao.OUTRO,
                regioes=[],
                icone_legado=limpar(linha["ICONE"]),
            )
        )
        total += 1
        if total % 2_000 == 0:
            sessao.flush()

    sessao.flush()
    return total
```

- [ ] **Step 4: Implementar `migracao/anamnese.py`**

```python
"""Migra o questionario de saude: 37 perguntas, 2.046 respostas, 80 observacoes.

As respostas vivem em duas tabelas no legado — ARQSINAO ('S'/'N') e ARQSIQUA
(texto). Aqui viram uma so; o tipo da pergunta continua em tipo_resposta.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinico.models import ObservacaoClinica, PerguntaAnamnese, RespostaAnamnese
from app.pacientes.models import Paciente
from migracao.extrato import Extrato
from migracao.texto import limpar


@dataclass
class ResultadoAnamnese:
    perguntas: int = 0
    respostas: int = 0
    observacoes: int = 0


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoAnamnese:
    resultado = ResultadoAnamnese()

    perguntas = {
        p.codigo: p
        for p in sessao.scalars(
            select(PerguntaAnamnese).where(PerguntaAnamnese.clinica_id == clinica_id)
        )
    }
    for ordem, linha in enumerate(extrato.linhas("ARQUEST", ordem="NUMQUEST")):
        codigo = (limpar(linha["NUMQUEST"]) or "").zfill(2)
        texto = " ".join(
            parte
            for parte in (
                limpar(linha["DESCRICAO"]), limpar(linha["DESCRI2"]), limpar(linha["DESCRI3"])
            )
            if parte
        )
        if codigo in perguntas:
            perguntas[codigo].texto = texto or perguntas[codigo].texto
        else:
            pergunta = PerguntaAnamnese(
                clinica_id=clinica_id,
                codigo=codigo,
                texto=texto or f"Pergunta {codigo}",
                tipo_resposta=int(float(linha["TIPORESP"] or 1)),
                ordem=ordem,
            )
            sessao.add(pergunta)
            perguntas[codigo] = pergunta
        resultado.perguntas += 1
    sessao.flush()

    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    ja_respondidas = {
        (r.paciente_id, r.pergunta_id) for r in sessao.scalars(select(RespostaAnamnese))
    }

    for tabela in ("ARQSINAO", "ARQSIQUA"):
        for linha in extrato.linhas(tabela):
            paciente_id = pacientes.get(limpar(linha["CODICLIE"]))
            pergunta = perguntas.get((limpar(linha["NUMQUEST"]) or "").zfill(2))
            if paciente_id is None or pergunta is None:
                continue
            chave = (paciente_id, pergunta.id)
            if chave in ja_respondidas:
                resultado.respostas += 1
                continue
            sessao.add(
                RespostaAnamnese(
                    paciente_id=paciente_id,
                    pergunta_id=pergunta.id,
                    resposta=limpar(linha["RESP"]) or "",
                )
            )
            ja_respondidas.add(chave)
            resultado.respostas += 1
    sessao.flush()

    if sessao.query(ObservacaoClinica).count() == 0:
        for linha in extrato.linhas("OBSERCLI"):
            paciente_id = pacientes.get(limpar(linha["CODICLIE"]))
            texto = limpar(linha["OBS"])
            # ALERTA e um flag 'S'/'N' da tela antiga, com 1 unico 'S' em 1.481
            # linhas: sem significado recuperavel. Nao migra.
            if paciente_id is None or not texto:
                continue
            sessao.add(ObservacaoClinica(paciente_id=paciente_id, texto=texto))
            resultado.observacoes += 1
    else:
        resultado.observacoes = sessao.query(ObservacaoClinica).count()
    sessao.flush()

    return resultado
```

- [ ] **Step 5: Implementar `migracao/conferencia.py`**

```python
"""Conferencia bloqueante da migracao.

Todos os numeros abaixo vieram do extrato verificado e estao documentados na spec
(secao 6) e em dados_extraidos/DICIONARIO.md. Se algum nao bater, a migracao aborta
sem gravar: melhor nao migrar do que migrar torto um prontuario de 30 anos.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clinico.models import (
    Condicao, Lancamento, LancamentoRegiao, Odontograma, RespostaAnamnese,
)
from app.pacientes.models import Paciente
from app.shared.dentes import TODOS_FDI
from app.shared.tipos import Escopo

ESPERADO_PACIENTES = 5_561
ESPERADO_LANCAMENTOS = 44_812
ESPERADO_REGIOES = 29_350
ESPERADO_CONDICOES = 9_629
ESPERADO_RESPOSTAS = 2_046
ESPERADO_SOMA = Decimal("3461389.07")


class ConferenciaFalhou(RuntimeError):
    def __init__(self, divergencias: list[str]) -> None:
        self.divergencias = divergencias
        super().__init__(
            "a conferencia da migracao reprovou:\n  - " + "\n  - ".join(divergencias)
        )


def conferir(sessao: Session, clinica_id: int) -> list[str]:
    """Devolve a lista de divergencias. Lista vazia significa aprovado."""
    divergencias: list[str] = []

    def comparar(rotulo: str, encontrado, esperado) -> None:
        if encontrado != esperado:
            divergencias.append(f"{rotulo}: esperado {esperado}, encontrado {encontrado}")

    comparar(
        "paciente",
        sessao.query(Paciente).filter_by(clinica_id=clinica_id).count(),
        ESPERADO_PACIENTES,
    )
    comparar(
        "lancamento",
        sessao.query(Lancamento).filter_by(clinica_id=clinica_id).count(),
        ESPERADO_LANCAMENTOS,
    )
    comparar(
        "lancamento_regiao",
        sessao.query(LancamentoRegiao)
        .join(Lancamento, LancamentoRegiao.lancamento_id == Lancamento.id)
        .filter(Lancamento.clinica_id == clinica_id)
        .count(),
        ESPERADO_REGIOES,
    )
    comparar("condicao", sessao.query(Condicao).count(), ESPERADO_CONDICOES)
    comparar("resposta_anamnese", sessao.query(RespostaAnamnese).count(), ESPERADO_RESPOSTAS)

    soma = sessao.query(
        func.coalesce(func.sum(Lancamento.valor), 0)
    ).filter_by(clinica_id=clinica_id).scalar()
    comparar("soma dos valores", Decimal(soma).quantize(Decimal("0.01")), ESPERADO_SOMA)

    orfaos = (
        sessao.query(Lancamento)
        .outerjoin(Odontograma, Lancamento.odontograma_id == Odontograma.id)
        .filter(Odontograma.id.is_(None))
        .count()
    )
    comparar("lancamento orfao", orfaos, 0)

    dentes_invalidos = sessao.scalars(
        select(func.count())
        .select_from(Lancamento)
        .where(
            Lancamento.dente.isnot(None),
            Lancamento.dente.notin_(list(TODOS_FDI)),
        )
    ).one()
    comparar("dente fora da notacao FDI", dentes_invalidos, 0)

    boca_com_dente = (
        sessao.query(Lancamento)
        .filter(Lancamento.escopo == Escopo.BOCA, Lancamento.dente.isnot(None))
        .count()
    )
    comparar("lancamento de boca com dente preenchido", boca_com_dente, 0)

    regiao_fora_de_escopo = (
        sessao.query(LancamentoRegiao)
        .join(Lancamento, LancamentoRegiao.lancamento_id == Lancamento.id)
        .filter(Lancamento.escopo != Escopo.REGIOES)
        .count()
    )
    comparar("regiao em lancamento sem escopo REGIOES", regiao_fora_de_escopo, 0)

    return divergencias
```

- [ ] **Step 6: Implementar `migracao/__main__.py`**

```python
"""Roda a migracao inteira numa transacao so.

    python -m migracao

Nada e gravado se a conferencia final reprovar. Rodar de novo e seguro: cada etapa
e idempotente.
"""

import sys

from sqlalchemy import select

from app.auth.models import Clinica
from app.config import config
from app.shared.db import Sessao
from migracao import anamnese, catalogo, condicoes, lancamentos, pacientes
from migracao.conferencia import ConferenciaFalhou, conferir
from migracao.extrato import Extrato


def main() -> int:
    with Sessao() as sessao, Extrato(config.extrato_sqlite) as extrato:
        clinica = sessao.scalars(select(Clinica).limit(1)).first()
        if clinica is None:
            clinica = Clinica(nome="Consultorio Dra. Katia")
            sessao.add(clinica)
            sessao.flush()

        print("catalogo...", flush=True)
        print(" ", catalogo.migrar(sessao, extrato, clinica.id))
        print("pacientes...", flush=True)
        print(" ", pacientes.migrar(sessao, extrato, clinica.id))
        print("lancamentos... (44.812 registros, leva alguns minutos)", flush=True)
        print(" ", lancamentos.migrar(sessao, extrato, clinica.id))
        print("condicoes...", flush=True)
        print(" ", condicoes.migrar(sessao, extrato, clinica.id))
        print("anamnese...", flush=True)
        print(" ", anamnese.migrar(sessao, extrato, clinica.id))

        print("conferindo...", flush=True)
        divergencias = conferir(sessao, clinica.id)
        if divergencias:
            sessao.rollback()
            raise ConferenciaFalhou(divergencias)

        sessao.commit()
        print("conferencia aprovada. migracao gravada.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConferenciaFalhou as erro:
        print(erro, file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 7: Rodar e ver passar**

Run: `EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite pytest tests/migracao/test_migracao_completa.py -v`
Expected: PASS (8 testes)

- [ ] **Step 8: Rodar a migração de verdade, ponta a ponta**

Run:
```bash
alembic upgrade head
EXTRATO_SQLITE=../dados_extraidos/dentalis.sqlite python -m migracao
```
Expected: termina com `conferencia aprovada. migracao gravada.`

Confira à mão que os 30 anos estão lá:

```bash
docker compose exec db psql -U bddente -c \
  "SELECT (SELECT count(*) FROM paciente) pacientes,
          (SELECT count(*) FROM lancamento) lancamentos,
          (SELECT count(*) FROM lancamento_regiao) regioes,
          (SELECT sum(valor) FROM lancamento) total"
```
Expected: `5561 | 44812 | 29350 | 3461389.07`

- [ ] **Step 9: Commitar**

```bash
git add migracao/condicoes.py migracao/anamnese.py migracao/conferencia.py migracao/__main__.py tests/migracao/test_migracao_completa.py
git commit -m "feat: migracao de condicoes e anamnese com conferencia bloqueante"
```

---

# Fase 3 — Aplicação

### Task 10: Autenticação e auditoria

**Files:**
- Create: `app/auth/senha.py`, `app/auth/sessao.py`, `app/auth/auditoria.py`, `app/auth/service.py`, `app/auth/rotas.py`
- Create: `app/templates/login.html`
- Modify: `app/main.py`
- Test: `tests/auth/__init__.py`, `tests/auth/test_senha.py`, `tests/auth/test_login.py`

**Interfaces:**
- Consumes: `app.auth.models.Usuario`, `app.auth.models.Auditoria`, `app.shared.db.obter_sessao`, `app.config.config`.
- Produces:
  - `app.auth.senha.gerar_hash(senha: str) -> str` e `app.auth.senha.conferir(senha: str, hash_guardado: str) -> bool`
  - `app.auth.sessao.assinar(usuario_id: int) -> str` e `app.auth.sessao.ler(token: str) -> int | None`
  - `app.auth.sessao.usuario_atual(request, sessao) -> Usuario` — dependência do FastAPI; redireciona para `/login` se não houver sessão válida.
  - `app.auth.auditoria.registrar(sessao, *, clinica_id, usuario_id, acao, entidade, entidade_id, antes=None, depois=None, ip=None) -> None`
  - `app.auth.service.autenticar(sessao, email: str, senha: str) -> Usuario | None`
  - `app.auth.service.criar_usuario(sessao, *, clinica_id, email, senha, nome) -> Usuario`
  - `app.auth.rotas.router` — `GET /login`, `POST /login`, `POST /logout`
  - Nome do cookie: `bddente_sessao`.

- [ ] **Step 1: Escrever o teste de senha e sessão (falha)**

`tests/auth/test_senha.py`:

```python
import pytest

from app.auth.senha import conferir, gerar_hash
from app.auth.sessao import assinar, ler


def test_hash_nao_guarda_a_senha_em_claro():
    h = gerar_hash("segredo-da-katia")
    assert "segredo-da-katia" not in h
    assert h.startswith("$argon2")


def test_senha_certa_confere_e_errada_nao():
    h = gerar_hash("segredo-da-katia")
    assert conferir("segredo-da-katia", h) is True
    assert conferir("outra-coisa", h) is False


def test_duas_chamadas_geram_hashes_diferentes():
    """Sal aleatorio: dois usuarios com a mesma senha nao ficam iguais no banco."""
    assert gerar_hash("igual") != gerar_hash("igual")


def test_hash_corrompido_nao_derruba_o_login():
    assert conferir("qualquer", "isto-nao-e-um-hash") is False


def test_token_de_sessao_faz_ida_e_volta():
    assert ler(assinar(42)) == 42


@pytest.mark.parametrize("token", ["", "lixo", "eyJ1IjoxfQ.assinatura-falsa"])
def test_token_adulterado_e_recusado(token):
    assert ler(token) is None


def test_token_expirado_e_recusado(monkeypatch):
    import app.auth.sessao as modulo

    token = assinar(42)
    monkeypatch.setattr(modulo, "MAX_IDADE_SEGUNDOS", -1)
    assert ler(token) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/auth/test_senha.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.auth.senha'`

- [ ] **Step 3: Implementar `app/auth/senha.py` e `app/auth/sessao.py`**

`app/auth/senha.py`:

```python
"""Hash de senha com argon2 — o padrao recomendado hoje. Dado de saude e dado
pessoal sensivel pela LGPD; a senha que da acesso a ele nao pode ser reversivel."""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def conferir(senha: str, hash_guardado: str) -> bool:
    """Nunca levanta excecao: um hash corrompido no banco vira 'senha errada',
    nao erro 500 na tela de login."""
    try:
        return _hasher.verify(hash_guardado, senha)
    except (Argon2Error, ValueError, TypeError):
        return False
```

`app/auth/sessao.py`:

```python
"""Sessao em cookie assinado. Sem tabela de sessao: um usuario so, uma clinica."""

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.config import config
from app.shared.db import obter_sessao

NOME_COOKIE = "bddente_sessao"
SALT = "bddente-sessao-v1"
MAX_IDADE_SEGUNDOS = config.sessao_horas * 3600

_serializador = URLSafeTimedSerializer(config.secret_key, salt=SALT)


def assinar(usuario_id: int) -> str:
    return _serializador.dumps({"u": usuario_id})


def ler(token: str) -> int | None:
    try:
        dados = _serializador.loads(token, max_age=MAX_IDADE_SEGUNDOS)
    except (BadSignature, SignatureExpired, TypeError):
        return None
    identificador = dados.get("u") if isinstance(dados, dict) else None
    return identificador if isinstance(identificador, int) else None


class PrecisaLogar(HTTPException):
    """Levantada quando nao ha sessao valida. O handler em main.py devolve um
    redirect para /login."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail="sessao ausente ou expirada")


def usuario_atual(
    request: Request, sessao: Session = Depends(obter_sessao)
) -> Usuario:
    token = request.cookies.get(NOME_COOKIE, "")
    usuario_id = ler(token)
    if usuario_id is None:
        raise PrecisaLogar()
    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise PrecisaLogar()
    return usuario


def redirecionar_para_login(request: Request, exc: Exception) -> RedirectResponse:
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(NOME_COOKIE)
    return resposta
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/auth/test_senha.py -v`
Expected: PASS (7 testes)

- [ ] **Step 5: Escrever o teste de login e auditoria (falha)**

`tests/auth/test_login.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica, Usuario
from app.auth.sessao import NOME_COOKIE
from app.auth.service import autenticar, criar_usuario
from app.main import criar_app
from app.shared.db import obter_sessao


@pytest.fixture
def cliente(sessao):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def katia(sessao):
    clinica = Clinica(nome="Consultorio")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao,
        clinica_id=clinica.id,
        email="katia@exemplo.com",
        senha="senha-forte-de-verdade",
        nome="Katia",
    )
    sessao.flush()
    return usuario


def test_autenticar_aceita_a_senha_certa(sessao, katia):
    assert autenticar(sessao, "katia@exemplo.com", "senha-forte-de-verdade") is not None


@pytest.mark.parametrize(
    ("email", "senha"),
    [
        ("katia@exemplo.com", "errada"),
        ("naoexiste@exemplo.com", "senha-forte-de-verdade"),
        ("", ""),
    ],
)
def test_autenticar_recusa_o_resto(sessao, katia, email, senha):
    assert autenticar(sessao, email, senha) is None


def test_usuario_inativo_nao_entra(sessao, katia):
    katia.ativo = False
    sessao.flush()
    assert autenticar(sessao, "katia@exemplo.com", "senha-forte-de-verdade") is None


def test_login_bem_sucedido_seta_cookie_e_redireciona(cliente, katia):
    resposta = cliente.post(
        "/login", data={"email": "katia@exemplo.com", "senha": "senha-forte-de-verdade"}
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes"
    assert NOME_COOKIE in resposta.cookies


def test_login_errado_volta_para_a_tela_sem_cookie(cliente, katia):
    resposta = cliente.post("/login", data={"email": "katia@exemplo.com", "senha": "x"})
    assert resposta.status_code == 200
    assert NOME_COOKIE not in resposta.cookies
    assert "senha" in resposta.text.lower()


def test_pagina_protegida_sem_sessao_manda_para_o_login(cliente):
    resposta = cliente.get("/pacientes")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_logout_apaga_o_cookie(cliente, katia):
    cliente.post(
        "/login", data={"email": "katia@exemplo.com", "senha": "senha-forte-de-verdade"}
    )
    resposta = cliente.post("/logout")
    assert resposta.status_code == 303
    assert cliente.cookies.get(NOME_COOKIE) in (None, "")


def test_criar_usuario_deixa_rastro_na_auditoria(sessao, katia):
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "usuario")
    ).all()
    assert len(linhas) == 1
    assert linhas[0].acao == "CRIAR"
    assert linhas[0].entidade_id == katia.id
    assert "senha" not in str(linhas[0].dados_depois).lower()


def test_auditoria_nunca_guarda_hash_de_senha(sessao, katia):
    for linha in sessao.scalars(select(Auditoria)):
        assert "argon2" not in str(linha.dados_depois or "")
```

Crie `tests/auth/__init__.py` vazio.

- [ ] **Step 6: Rodar e ver falhar**

Run: `pytest tests/auth/test_login.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.auth.service'`

- [ ] **Step 7: Implementar auditoria e service**

`app/auth/auditoria.py`:

```python
"""Registro de toda escrita da aplicacao.

Exigencia de LGPD e a unica forma de responder 'quem mudou este prontuario, quando,
e o que estava la antes'. Chamado por todos os service.py — nao ha escrita sem linha
aqui.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.auth.models import Auditoria

CAMPOS_PROIBIDOS = frozenset({"senha", "senha_hash", "token"})


def _sem_segredo(dados: dict[str, Any] | None) -> dict[str, Any] | None:
    """Auditoria nunca guarda credencial — nem em hash."""
    if dados is None:
        return None
    return {k: v for k, v in dados.items() if k.lower() not in CAMPOS_PROIBIDOS}


def registrar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int | None,
    acao: str,
    entidade: str,
    entidade_id: int | None,
    antes: dict[str, Any] | None = None,
    depois: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    sessao.add(
        Auditoria(
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            dados_antes=_sem_segredo(antes),
            dados_depois=_sem_segredo(depois),
            ip=ip,
        )
    )
```

`app/auth/service.py`:

```python
"""Fronteira publica do modulo auth. Nenhum outro modulo importa auth.models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.models import Usuario
from app.auth.senha import conferir, gerar_hash


def autenticar(sessao: Session, email: str, senha: str) -> Usuario | None:
    """Devolve o usuario ou None. Nao distingue 'email nao existe' de 'senha errada':
    a tela nao deve confirmar quais emails existem."""
    if not email or not senha:
        return None
    usuario = sessao.scalars(
        select(Usuario).where(Usuario.email == email.strip().lower())
    ).first()
    if usuario is None or not usuario.ativo:
        return None
    if not conferir(senha, usuario.senha_hash):
        return None
    return usuario


def criar_usuario(
    sessao: Session, *, clinica_id: int, email: str, senha: str, nome: str
) -> Usuario:
    usuario = Usuario(
        clinica_id=clinica_id,
        email=email.strip().lower(),
        senha_hash=gerar_hash(senha),
        nome=nome.strip(),
    )
    sessao.add(usuario)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario.id,
        acao="CRIAR",
        entidade="usuario",
        entidade_id=usuario.id,
        depois={"email": usuario.email, "nome": usuario.nome},
    )
    return usuario
```

- [ ] **Step 8: Implementar as rotas e a tela de login**

`app/auth/rotas.py`:

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import autenticar
from app.config import config
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def tela_de_login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@router.post("/login")
def entrar(
    request: Request,
    email: str = Form(""),
    senha: str = Form(""),
    sessao: Session = Depends(obter_sessao),
):
    usuario = autenticar(sessao, email, senha)
    if usuario is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "Email ou senha nao conferem."},
            status_code=200,
        )
    registrar(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        acao="ENTRAR",
        entidade="sessao",
        entidade_id=usuario.id,
        ip=request.client.host if request.client else None,
    )
    sessao.commit()
    resposta = RedirectResponse("/pacientes", status_code=303)
    resposta.set_cookie(
        NOME_COOKIE,
        assinar(usuario.id),
        httponly=True,
        samesite="lax",
        secure=config.cookie_seguro,
        max_age=config.sessao_horas * 3600,
    )
    return resposta


@router.post("/logout")
def sair():
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(NOME_COOKIE)
    return resposta
```

`app/templates/__init__.py`:

```python
from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent))
```

`app/templates/login.html`:

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Entrar — BDDente</title>
  <link rel="stylesheet" href="/static/bddente.css">
</head>
<body class="tela-login">
  <main class="cartao-login">
    <div class="marca-login">BD<span>Dente</span></div>
    <p class="sub-login">Prontuario odontologico</p>
    <form method="post" action="/login">
      <label for="email">Email</label>
      <input id="email" name="email" type="email" autocomplete="username" required autofocus>
      <label for="senha">Senha</label>
      <input id="senha" name="senha" type="password" autocomplete="current-password" required>
      {% if erro %}<p class="erro-login">{{ erro }}</p>{% endif %}
      <button type="submit">Entrar</button>
    </form>
  </main>
</body>
</html>
```

- [ ] **Step 9: Montar tudo em `app/main.py`**

Substitua `app/main.py` por:

```python
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
```

Crie `app/static/bddente.css` vazio por enquanto (a Task 11 preenche) e `app/static/.gitkeep`.

> `test_pagina_protegida_sem_sessao_manda_para_o_login` só passa depois da Task 12,
> que cria a rota `/pacientes`. **Marque-o com `@pytest.mark.xfail(reason="rota /pacientes chega na Task 12")` agora e remova a marca na Task 12** — não apague o teste.

- [ ] **Step 10: Rodar e ver passar**

Run: `pytest tests/auth -v`
Expected: PASS (com 1 xfail)

- [ ] **Step 11: Criar o primeiro usuário**

Sem isto ninguém consegue entrar: `criar_usuario` existe no service, mas não há
cadastro público (de propósito) nem tela de administração no MVP.

`scripts/criar_usuario.py`:

```python
"""Cria (ou troca a senha de) o usuario da clinica.

    python -m scripts.criar_usuario katia@exemplo.com "Katia"

A senha e pedida no terminal, sem eco, e nunca fica no historico do shell.
"""

import getpass
import sys

from sqlalchemy import select

from app.auth.models import Clinica, Usuario
from app.auth.senha import gerar_hash
from app.auth.service import criar_usuario
from app.shared.db import Sessao

TAMANHO_MINIMO_SENHA = 12


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 64
    email, nome = sys.argv[1].strip().lower(), sys.argv[2].strip()

    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        print("as senhas nao conferem", file=sys.stderr)
        return 1
    if len(senha) < TAMANHO_MINIMO_SENHA:
        print(
            f"senha curta demais: use ao menos {TAMANHO_MINIMO_SENHA} caracteres. "
            "Esta senha abre 30 anos de prontuario.",
            file=sys.stderr,
        )
        return 1

    with Sessao() as sessao:
        clinica = sessao.scalars(select(Clinica).limit(1)).first()
        if clinica is None:
            clinica = Clinica(nome="Consultorio")
            sessao.add(clinica)
            sessao.flush()

        existente = sessao.scalars(select(Usuario).where(Usuario.email == email)).first()
        if existente is not None:
            existente.senha_hash = gerar_hash(senha)
            existente.ativo = True
            acao = "senha trocada"
        else:
            criar_usuario(
                sessao, clinica_id=clinica.id, email=email, senha=senha, nome=nome
            )
            acao = "usuario criado"
        sessao.commit()
    print(f"{acao}: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Crie `scripts/__init__.py` vazio.

`tests/auth/test_criar_usuario_cli.py`:

```python
import subprocess
import sys


def test_o_script_explica_o_uso_quando_chamado_errado():
    resultado = subprocess.run(
        [sys.executable, "-m", "scripts.criar_usuario"],
        capture_output=True, text=True,
    )
    assert resultado.returncode == 64
    assert "criar_usuario" in resultado.stderr
```

Run:
```bash
alembic upgrade head
python -m scripts.criar_usuario katia@exemplo.com "Katia"
```
Expected: `usuario criado: katia@exemplo.com`

- [ ] **Step 12: Commitar**

```bash
git add app/auth app/templates app/static app/main.py scripts tests/auth
git commit -m "feat: login com argon2, sessao assinada e auditoria"
```

---

### Task 11: Layout base e identidade visual

Interface **branca com roxo nos detalhes** — não uma interface roxa. O nome "BDDente" aparece em branco sobre a lateral roxa.

**Files:**
- Create: `app/templates/base.html`
- Modify: `app/static/bddente.css` (preencher)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `app.templates.templates`.
- Produces:
  - `app/templates/base.html` com os blocos Jinja `{% block titulo %}`, `{% block conteudo %}` e `{% block scripts %}`, e a variável de contexto `aba` (`"pacientes"` · `"odontograma"` · `"tratamentos"`) que marca o item ativo da navegação.

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_layout.py`:

```python
import re
from pathlib import Path

CSS = Path("app/static/bddente.css")
BASE = Path("app/templates/base.html")

TOKENS = {
    "--roxo": "#7C3AED",
    "--roxo-esc": "#5B21B6",
    "--roxo-cl": "#EDE9FE",
    "--roxo-brd": "#C4B5FD",
    "--borda": "#E2E8F0",
    "--texto": "#0F172A",
    "--texto-fraco": "#64748B",
    "--planejado": "#DC2626",
    "--realizado": "#16A34A",
    "--existente": "#2563EB",
}


def test_todos_os_tokens_da_spec_estao_definidos():
    css = CSS.read_text(encoding="utf-8")
    for nome, valor in TOKENS.items():
        assert re.search(rf"{re.escape(nome)}\s*:\s*{valor}", css, re.I), nome


def test_o_fundo_da_pagina_e_branco_nao_roxo():
    """A spec e explicita: interface branca com roxo nos detalhes."""
    css = CSS.read_text(encoding="utf-8")
    corpo = re.search(r"\bbody\s*\{([^}]*)\}", css, re.S)
    assert corpo, "regra para body nao encontrada"
    assert re.search(r"background\s*:\s*#fff", corpo.group(1), re.I)


def test_o_nome_aparece_em_branco_sobre_a_lateral_roxa():
    css = CSS.read_text(encoding="utf-8")
    marca = re.search(r"\.marca\s*\{([^}]*)\}", css, re.S)
    assert marca and re.search(r"color\s*:\s*#fff", marca.group(1), re.I)
    lateral = re.search(r"\.lateral\s*\{([^}]*)\}", css, re.S)
    assert lateral and "roxo" in lateral.group(1)


def test_a_navegacao_tem_as_tres_abas_mais_o_financeiro_em_breve():
    html = BASE.read_text(encoding="utf-8")
    for rotulo in ("Pacientes", "Odontograma", "Tratamentos", "Financeiro"):
        assert rotulo in html
    assert "em breve" in html


def test_o_layout_expoe_os_blocos_que_as_telas_usam():
    html = BASE.read_text(encoding="utf-8")
    for bloco in ("titulo", "conteudo", "scripts"):
        assert f"block {bloco}" in html


def test_a_pagina_declara_idioma_e_viewport():
    html = BASE.read_text(encoding="utf-8")
    assert 'lang="pt-BR"' in html
    assert "viewport" in html
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_layout.py -v`
Expected: FAIL — `base.html` não existe e o CSS está vazio

- [ ] **Step 3: Escrever `app/templates/base.html`**

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}BDDente{% endblock %}</title>
  <link rel="stylesheet" href="/static/bddente.css">
</head>
<body>
  <div class="app">
    <nav class="lateral">
      <div class="marca">BD<span>Dente</span></div>
      <ul class="navegacao">
        <li><a href="/pacientes" class="{{ 'ativo' if aba == 'pacientes' }}">Pacientes</a></li>
        <li><a href="/odontograma" class="{{ 'ativo' if aba == 'odontograma' }}">Odontograma</a></li>
        <li><a href="/tratamentos" class="{{ 'ativo' if aba == 'tratamentos' }}">Tratamentos</a></li>
        <li><span class="desativado">Financeiro <b>em breve</b></span></li>
      </ul>
      <form method="post" action="/logout" class="sair">
        <button type="submit">Sair</button>
      </form>
    </nav>
    <main class="principal">
      {% block conteudo %}{% endblock %}
    </main>
  </div>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 4: Escrever `app/static/bddente.css`**

```css
/* BDDente — interface branca com roxo nos detalhes. */

:root {
  --roxo: #7C3AED;
  --roxo-esc: #5B21B6;
  --roxo-cl: #EDE9FE;
  --roxo-brd: #C4B5FD;
  --borda: #E2E8F0;
  --texto: #0F172A;
  --texto-fraco: #64748B;
  --planejado: #DC2626;
  --realizado: #16A34A;
  --existente: #2563EB;
  --raio: 10px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: #fff;
  color: var(--texto);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px;
}

.app { display: flex; min-height: 100vh; }

/* --- lateral: a unica superficie roxa da interface --- */
.lateral {
  width: 200px;
  flex: none;
  background: linear-gradient(170deg, var(--roxo-esc), #4C1D95);
  padding: 20px 0;
  display: flex;
  flex-direction: column;
}

.marca {
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  padding: 0 18px 22px;
}
.marca span { color: var(--roxo-brd); font-weight: 400; }

.navegacao { list-style: none; margin: 0; padding: 0; flex: 1; }
.navegacao a,
.navegacao .desativado {
  display: block;
  color: #DDD6FE;
  font-size: 14px;
  padding: 11px 18px;
  text-decoration: none;
}
.navegacao a:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
.navegacao a.ativo {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  font-weight: 600;
  box-shadow: inset 3px 0 0 #fff;
}
.navegacao .desativado { color: #A78BFA; cursor: default; }
.navegacao .desativado b {
  font-size: 9.5px;
  background: rgba(255, 255, 255, 0.14);
  padding: 2px 6px;
  border-radius: 10px;
  margin-left: 6px;
  font-weight: 600;
}

.sair { padding: 0 18px; }
.sair button {
  width: 100%;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #DDD6FE;
  border-radius: var(--raio);
  padding: 8px;
  cursor: pointer;
  font-size: 13px;
}
.sair button:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }

/* --- area principal: branca --- */
.principal { flex: 1; min-width: 0; padding: 22px 26px; }

h1 { font-size: 20px; margin: 0 0 4px; }
.legenda-topo { color: var(--texto-fraco); font-size: 13px; margin: 0 0 16px; }

/* --- componentes --- */
.busca {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1.5px solid var(--roxo-brd);
  border-radius: var(--raio);
  padding: 10px 14px;
  max-width: 620px;
}
.busca input {
  border: 0;
  outline: 0;
  flex: 1;
  font-size: 14px;
  color: var(--texto);
  background: transparent;
}

.filtros { display: flex; gap: 7px; flex-wrap: wrap; margin: 12px 0 16px; }
.filtro {
  font-size: 12px;
  padding: 5px 13px;
  border-radius: 20px;
  border: 1px solid var(--borda);
  color: #475569;
  text-decoration: none;
}
.filtro.ativo {
  background: var(--roxo);
  border-color: var(--roxo);
  color: #fff;
  font-weight: 600;
}

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94A3B8;
  font-weight: 700;
  padding: 10px 12px;
  border-bottom: 1px solid var(--borda);
}
td { padding: 10px 12px; border-bottom: 1px solid #F1F5F9; color: #334155; }
tbody tr:hover td { background: #FAF7FF; }
.nome { font-weight: 620; color: var(--texto); }
.codigo { font-size: 11px; color: #94A3B8; font-family: ui-monospace, monospace; }
.numero { font-variant-numeric: tabular-nums; }

/* dado suspeito e marcado, nunca escondido nem corrigido no chute */
.aviso {
  color: #B45309;
  background: #FEF3C7;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 11px;
}

.selo { font-size: 11px; font-weight: 650; padding: 2.5px 8px; border-radius: 20px; }
.selo.pendente { background: #FEE2E2; color: #B91C1C; }
.selo.zero { background: #F1F5F9; color: #94A3B8; }

button.primario {
  background: var(--roxo);
  color: #fff;
  border: 0;
  border-radius: var(--raio);
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
button.primario:hover { background: var(--roxo-esc); }
button.primario:disabled { background: var(--roxo-brd); cursor: not-allowed; }

/* --- login --- */
.tela-login {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(160deg, #F5F3FF, #fff 60%);
}
.cartao-login {
  width: 340px;
  background: #fff;
  border: 1px solid var(--borda);
  border-radius: 16px;
  padding: 30px 28px;
  box-shadow: 0 8px 30px rgba(15, 23, 42, 0.07);
}
.marca-login {
  font-size: 24px;
  font-weight: 700;
  color: var(--roxo-esc);
  letter-spacing: -0.02em;
}
.marca-login span { color: var(--roxo); font-weight: 400; }
.sub-login { color: var(--texto-fraco); font-size: 13px; margin: 2px 0 22px; }
.cartao-login label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 5px;
}
.cartao-login input {
  width: 100%;
  border: 1px solid var(--borda);
  border-radius: var(--raio);
  padding: 10px 12px;
  font-size: 14px;
  margin-bottom: 15px;
}
.cartao-login input:focus {
  outline: 0;
  border-color: var(--roxo);
  box-shadow: 0 0 0 3px var(--roxo-cl);
}
.cartao-login button {
  width: 100%;
  background: var(--roxo);
  color: #fff;
  border: 0;
  border-radius: var(--raio);
  padding: 11px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}
.cartao-login button:hover { background: var(--roxo-esc); }
.erro-login {
  color: #B91C1C;
  background: #FEE2E2;
  border-radius: var(--raio);
  padding: 8px 10px;
  font-size: 13px;
  margin: 0 0 12px;
}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/test_layout.py -v`
Expected: PASS (6 testes)

- [ ] **Step 6: Commitar**

```bash
git add app/templates/base.html app/static/bddente.css tests/test_layout.py
git commit -m "feat: layout base com lateral roxa e identidade visual"
```

---

### Task 12: Tela de pacientes

A busca é o centro da tela porque é o que a Dra. Kátia faz o dia inteiro: acha o paciente e abre o odontograma. Digitar e apertar Enter leva direto pro dente.

**Files:**
- Create: `app/pacientes/service.py`, `app/pacientes/rotas.py`, `app/templates/pacientes.html`
- Modify: `app/main.py` (incluir o router), `tests/auth/test_login.py` (remover o `xfail`)
- Test: `tests/pacientes/test_service.py`, `tests/pacientes/test_tela_pacientes.py`

**Interfaces:**
- Consumes: modelos de `app.pacientes`, `app.auth.sessao.usuario_atual`.
- **Não** deixe os contadores de pendência zerados esperando uma task futura: a
  Task 12 implementa `clinico.service.resumo_por_paciente` e
  `catalogo.service.nomes_de_convenio` como parte da própria entrega (Steps 3 e 5).
- Produces:
  - `app.pacientes.service.Filtro` — `StrEnum` com `ATIVOS`, `COM_PENDENCIA`, `EM_ABERTO`, `TODOS`.
  - `app.pacientes.service.LinhaPaciente` — dataclass: `id`, `nome`, `codigo_legado`, `idade: int | None`, `telefone: str | None`, `telefone_suspeito: bool`, `ultimo_atendimento: date | None`, `data_suspeita: bool`, `convenio: str | None`, `pendentes: int`, `em_aberto: Decimal`, `revisar_motivo: list[str]`.
  - `app.pacientes.service.buscar(sessao, *, clinica_id, termo="", filtro=Filtro.ATIVOS, limite=100) -> list[LinhaPaciente]`
  - `app.pacientes.service.obter(sessao, *, clinica_id, paciente_id) -> Paciente | None`
  - `app.pacientes.service.contagens(sessao, *, clinica_id) -> dict[str, int]` — chaves `total`, `ativos`, `com_pendencia`.
  - `app.clinico.service.resumo_por_paciente(sessao, *, clinica_id, paciente_ids) -> dict[int, tuple[int, Decimal]]` — para cada paciente, `(pendentes, valor_em_aberto)`.
  - `app.catalogo.service.nomes_de_convenio(sessao, *, clinica_id, convenio_ids) -> dict[int, str]`
  - Rota `GET /pacientes` com query `q` e `filtro`.

**Direção da dependência entre módulos.** `clinico` depende de `pacientes` (um
lançamento pertence a um paciente) — pode importar `pacientes.service` no topo do
arquivo. A volta existe só para os contadores da lista, e por isso
`pacientes.service` importa `clinico.service` **dentro da função**, não no topo:
importar nos dois sentidos no topo trava o Python com import circular.

- [ ] **Step 1: Escrever o teste do service (falha)**

`tests/pacientes/test_service.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

from app.auth.models import Clinica
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.clinico.models import Lancamento, Odontograma
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.service import Filtro, buscar, contagens, obter
from app.shared.tipos import Escopo, StatusLancamento


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="002", nome="UNIODONTO")
    sessao.add_all([categoria, convenio])
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao",
        categoria_id=categoria.id, escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.add(proc)
    sessao.flush()

    amanda = Paciente(
        clinica_id=clinica.id, codigo_legado="6612/PT", nome="Amanda Ribeiro Nogueira",
        nascimento=date(1990, 3, 2), ultimo_atendimento=date(2024, 6, 25),
    )
    itagiba = Paciente(
        clinica_id=clinica.id, codigo_legado="3799/PT", nome="Itagiba Pereira Bastos",
        nascimento=date(1937, 1, 5), ultimo_atendimento=date(2024, 6, 26),
        convenio_id=convenio.id,
    )
    antigo = Paciente(
        clinica_id=clinica.id, codigo_legado="0001/PT", nome="Paciente Antigo",
        ultimo_atendimento=date(2001, 5, 1),
    )
    excluido = Paciente(
        clinica_id=clinica.id, codigo_legado="0002/PT", nome="Ja Excluido",
        excluido_em=date(2020, 1, 1),
    )
    sessao.add_all([amanda, itagiba, antigo, excluido])
    sessao.flush()

    sessao.add(
        PacienteTelefone(
            paciente_id=amanda.id, numero="51999990001",
            numero_original="51999990001", principal=True,
        )
    )
    sessao.add(
        PacienteTelefone(
            paciente_id=itagiba.id, numero="2490143",
            numero_original="2490-143", principal=True,
        )
    )
    odo = Odontograma(paciente_id=itagiba.id, numero=1)
    sessao.add(odo)
    sessao.flush()
    for _ in range(3):
        sessao.add(
            Lancamento(
                clinica_id=clinica.id, odontograma_id=odo.id, dente=16,
                escopo=Escopo.DENTE, procedimento_id=proc.id,
                status=StatusLancamento.PLANEJADO, valor=Decimal("100.00"),
            )
        )
    sessao.add(
        Lancamento(
            clinica_id=clinica.id, odontograma_id=odo.id, dente=17,
            escopo=Escopo.DENTE, procedimento_id=proc.id,
            status=StatusLancamento.REALIZADO, valor=Decimal("50.00"),
        )
    )
    sessao.flush()
    return clinica, amanda, itagiba, antigo, excluido


def test_busca_vazia_traz_os_ativos_em_ordem_alfabetica(sessao, cenario):
    clinica, amanda, itagiba, antigo, _ = cenario
    linhas = buscar(sessao, clinica_id=clinica.id, filtro=Filtro.ATIVOS)
    nomes = [linha.nome for linha in linhas]
    assert nomes == ["Amanda Ribeiro Nogueira", "Itagiba Pereira Bastos"]


def test_excluido_nunca_aparece_em_nenhum_filtro(sessao, cenario):
    clinica, *_ = cenario
    for filtro in Filtro:
        nomes = [linha.nome for linha in buscar(sessao, clinica_id=clinica.id, filtro=filtro)]
        assert "Ja Excluido" not in nomes


def test_filtro_todos_inclui_quem_nao_vem_ha_anos(sessao, cenario):
    clinica, *_ = cenario
    nomes = [linha.nome for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)]
    assert "Paciente Antigo" in nomes


@pytest.mark.parametrize(
    "termo", ["amanda", "AMANDA", "haubert", "Rosana Haubert", "6612", "51999990001"]
)
def test_busca_por_nome_parcial_telefone_e_codigo(sessao, cenario, termo):
    clinica, *_ = cenario
    linhas = buscar(sessao, clinica_id=clinica.id, termo=termo, filtro=Filtro.TODOS)
    assert [linha.nome for linha in linhas] == ["Amanda Ribeiro Nogueira"]


def test_busca_sem_resultado_devolve_lista_vazia(sessao, cenario):
    clinica, *_ = cenario
    assert buscar(sessao, clinica_id=clinica.id, termo="zzzzz", filtro=Filtro.TODOS) == []


def test_conta_pendentes_e_valor_em_aberto(sessao, cenario):
    clinica, _, itagiba, *_ = cenario
    linha = next(
        linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
        if linha.id == itagiba.id
    )
    assert linha.pendentes == 3
    assert linha.em_aberto == Decimal("300.00")


def test_filtro_com_pendencia_so_traz_quem_tem(sessao, cenario):
    clinica, _, itagiba, *_ = cenario
    linhas = buscar(sessao, clinica_id=clinica.id, filtro=Filtro.COM_PENDENCIA)
    assert [linha.id for linha in linhas] == [itagiba.id]


def test_idade_e_calculada_e_ausente_quando_nao_ha_nascimento(sessao, cenario):
    clinica, *_ = cenario
    por_nome = {
        linha.nome: linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
    }
    assert por_nome["Amanda Ribeiro Nogueira"].idade == date.today().year - 1990 - (
        (date.today().month, date.today().day) < (3, 2)
    )
    assert por_nome["Paciente Antigo"].idade is None


def test_telefone_vem_formatado_e_o_curto_vem_marcado(sessao, cenario):
    clinica, *_ = cenario
    por_nome = {
        linha.nome: linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
    }
    assert por_nome["Amanda Ribeiro Nogueira"].telefone == "(51) 99999-0001"
    assert por_nome["Amanda Ribeiro Nogueira"].telefone_suspeito is False
    assert por_nome["Itagiba Pereira Bastos"].telefone_suspeito is True


def test_convenio_vem_pelo_service_do_catalogo(sessao, cenario):
    clinica, _, itagiba, *_ = cenario
    linha = next(
        linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
        if linha.id == itagiba.id
    )
    assert linha.convenio == "UNIODONTO"


def test_paciente_sem_convenio_aparece_como_particular(sessao, cenario):
    clinica, amanda, *_ = cenario
    linha = next(
        linha
        for linha in buscar(sessao, clinica_id=clinica.id, filtro=Filtro.TODOS)
        if linha.id == amanda.id
    )
    assert linha.convenio is None


def test_obter_respeita_a_clinica_e_a_exclusao(sessao, cenario):
    clinica, amanda, _, _, excluido = cenario
    assert obter(sessao, clinica_id=clinica.id, paciente_id=amanda.id) is not None
    assert obter(sessao, clinica_id=clinica.id, paciente_id=excluido.id) is None
    assert obter(sessao, clinica_id=clinica.id + 999, paciente_id=amanda.id) is None


def test_contagens_do_cabecalho(sessao, cenario):
    clinica, *_ = cenario
    numeros = contagens(sessao, clinica_id=clinica.id)
    assert numeros["total"] == 3  # o excluido nao conta
    assert numeros["com_pendencia"] == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/pacientes/test_service.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.pacientes.service'`

- [ ] **Step 3: Implementar `app/clinico/service.py` (só o resumo, por ora)**

```python
"""Fronteira publica do modulo clinico.

Quando o modulo financeiro chegar, ele chama funcoes daqui — nunca consulta a
tabela lancamento direto.
"""

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clinico.models import Lancamento, Odontograma
from app.shared.tipos import StatusLancamento


def contar_pacientes_com_pendencia(sessao: Session, *, clinica_id: int) -> int:
    """Quantos pacientes tem ao menos um tratamento planejado. Uma agregacao so."""
    return sessao.scalars(
        select(func.count(func.distinct(Odontograma.paciente_id)))
        .select_from(Odontograma)
        .join(Lancamento, Lancamento.odontograma_id == Odontograma.id)
        .where(
            Lancamento.clinica_id == clinica_id,
            Lancamento.status == StatusLancamento.PLANEJADO,
            Lancamento.excluido_em.is_(None),
        )
    ).one()


def resumo_por_paciente(
    sessao: Session, *, clinica_id: int, paciente_ids: Iterable[int]
) -> dict[int, tuple[int, Decimal]]:
    """Para cada paciente, quantos tratamentos estao pendentes e quanto somam.

    Uma consulta agregada para a lista inteira — nunca uma por linha da tabela.
    """
    ids = list(paciente_ids)
    if not ids:
        return {}
    linhas = sessao.execute(
        select(
            Odontograma.paciente_id,
            func.count(Lancamento.id),
            func.coalesce(func.sum(Lancamento.valor), 0),
        )
        .join(Lancamento, Lancamento.odontograma_id == Odontograma.id)
        .where(
            Odontograma.paciente_id.in_(ids),
            Lancamento.clinica_id == clinica_id,
            Lancamento.status == StatusLancamento.PLANEJADO,
            Lancamento.excluido_em.is_(None),
        )
        .group_by(Odontograma.paciente_id)
    ).all()
    resumo: defaultdict[int, tuple[int, Decimal]] = defaultdict(
        lambda: (0, Decimal("0.00"))
    )
    for paciente_id, pendentes, soma in linhas:
        resumo[paciente_id] = (pendentes, Decimal(soma).quantize(Decimal("0.01")))
    return dict(resumo)
```

- [ ] **Step 4: Implementar `app/pacientes/service.py`**

```python
"""Fronteira publica do modulo pacientes."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalogo.service import nomes_de_convenio
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.telefone import formatar, parecer_incompleto

# "Ativo" = veio nos ultimos 4 anos. Sao 494 dos 5.561 no banco real.
ANOS_PARA_SER_ATIVO = 4
LIMITE_PADRAO = 100


class Filtro(StrEnum):
    ATIVOS = "ativos"
    COM_PENDENCIA = "com_pendencia"
    EM_ABERTO = "em_aberto"
    TODOS = "todos"


@dataclass
class LinhaPaciente:
    id: int
    nome: str
    codigo_legado: str | None
    idade: int | None
    telefone: str | None
    telefone_suspeito: bool
    ultimo_atendimento: date | None
    data_suspeita: bool
    convenio: str | None
    pendentes: int
    em_aberto: Decimal
    revisar_motivo: list[str] = field(default_factory=list)


def _idade(nascimento: date | None) -> int | None:
    if nascimento is None:
        return None
    hoje = date.today()
    return (
        hoje.year
        - nascimento.year
        - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
    )


def _corte_de_atividade() -> date:
    hoje = date.today()
    try:
        return hoje.replace(year=hoje.year - ANOS_PARA_SER_ATIVO)
    except ValueError:
        # 29 de fevereiro: o ano de 4 anos atras pode nao ter o dia 29.
        return hoje.replace(year=hoje.year - ANOS_PARA_SER_ATIVO, day=28)


def obter(sessao: Session, *, clinica_id: int, paciente_id: int) -> Paciente | None:
    return sessao.scalars(
        select(Paciente).where(
            Paciente.id == paciente_id,
            Paciente.clinica_id == clinica_id,
            Paciente.excluido_em.is_(None),
        )
    ).first()


def contagens(sessao: Session, *, clinica_id: int) -> dict[str, int]:
    """Numeros do cabecalho. Tres agregacoes no banco — nunca carregando a base.

    A versao ingenua chamaria buscar() e contaria em Python: com 5.561 pacientes
    isso seria uma varredura completa a cada abertura da tela.
    """
    from app.clinico.service import contar_pacientes_com_pendencia

    base = select(func.count()).select_from(Paciente).where(
        Paciente.clinica_id == clinica_id, Paciente.excluido_em.is_(None)
    )
    return {
        "total": sessao.scalars(base).one(),
        "ativos": sessao.scalars(
            base.where(Paciente.ultimo_atendimento >= _corte_de_atividade())
        ).one(),
        "com_pendencia": contar_pacientes_com_pendencia(sessao, clinica_id=clinica_id),
    }


def buscar(
    sessao: Session,
    *,
    clinica_id: int,
    termo: str = "",
    filtro: Filtro = Filtro.ATIVOS,
    limite: int | None = LIMITE_PADRAO,
) -> list[LinhaPaciente]:
    consulta = (
        select(Paciente)
        .options(selectinload(Paciente.telefones))
        .where(Paciente.clinica_id == clinica_id, Paciente.excluido_em.is_(None))
        .order_by(Paciente.nome)
    )

    termo = (termo or "").strip()
    if termo:
        padrao = f"%{termo}%"
        so_digitos = "".join(c for c in termo if c.isdigit())
        condicoes = [Paciente.nome.ilike(padrao), Paciente.codigo_legado.ilike(padrao)]
        if so_digitos:
            condicoes.append(
                Paciente.id.in_(
                    select(PacienteTelefone.paciente_id).where(
                        PacienteTelefone.numero.like(f"%{so_digitos}%")
                    )
                )
            )
        consulta = consulta.where(or_(*condicoes))
    elif filtro is Filtro.ATIVOS:
        consulta = consulta.where(Paciente.ultimo_atendimento >= _corte_de_atividade())

    # COM_PENDENCIA e EM_ABERTO sao peneirados em Python depois da consulta, entao
    # trazemos uma folga do banco para o limite final ainda poder ser preenchido.
    if limite is not None:
        folga = limite * 10 if filtro in (Filtro.COM_PENDENCIA, Filtro.EM_ABERTO) else limite
        consulta = consulta.limit(folga)

    # Import aqui dentro, nao no topo: clinico.service importa pacientes.service,
    # e importar nos dois sentidos no topo trava o Python com import circular.
    from app.clinico.service import resumo_por_paciente

    pacientes = list(sessao.scalars(consulta))
    resumo = resumo_por_paciente(
        sessao, clinica_id=clinica_id, paciente_ids=[p.id for p in pacientes]
    )
    convenios = nomes_de_convenio(
        sessao,
        clinica_id=clinica_id,
        convenio_ids={p.convenio_id for p in pacientes if p.convenio_id},
    )

    linhas: list[LinhaPaciente] = []
    for paciente in pacientes:
        pendentes, em_aberto = resumo.get(paciente.id, (0, Decimal("0.00")))
        if filtro is Filtro.COM_PENDENCIA and not pendentes:
            continue
        if filtro is Filtro.EM_ABERTO and em_aberto <= 0:
            continue

        principal = next(
            (t for t in paciente.telefones if t.principal), None
        ) or next(iter(paciente.telefones), None)

        linhas.append(
            LinhaPaciente(
                id=paciente.id,
                nome=paciente.nome,
                codigo_legado=paciente.codigo_legado,
                idade=_idade(paciente.nascimento),
                telefone=formatar(principal.numero) if principal else None,
                telefone_suspeito=bool(principal)
                and parecer_incompleto(principal.numero),
                ultimo_atendimento=paciente.ultimo_atendimento,
                data_suspeita="data_suspeita" in (paciente.revisar_motivo or []),
                convenio=convenios.get(paciente.convenio_id),
                pendentes=pendentes,
                em_aberto=em_aberto,
                revisar_motivo=list(paciente.revisar_motivo or []),
            )
        )
    if limite is not None:
        return linhas[:limite]
    return linhas
```

- [ ] **Step 5: Implementar `app/catalogo/service.py` (só o que a Task 12 usa)**

```python
"""Fronteira publica do modulo catalogo."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Convenio


def nomes_de_convenio(
    sessao: Session, *, clinica_id: int, convenio_ids: Iterable[int]
) -> dict[int, str]:
    """Uma consulta para a lista inteira. Outros modulos guardam convenio_id e
    perguntam o nome aqui — nunca fazem JOIN na tabela convenio."""
    ids = list(convenio_ids)
    if not ids:
        return {}
    return {
        c.id: c.nome
        for c in sessao.scalars(
            select(Convenio).where(
                Convenio.clinica_id == clinica_id, Convenio.id.in_(ids)
            )
        )
    }
```

- [ ] **Step 6: Rodar e ver passar**

Run: `pytest tests/pacientes/test_service.py -v`
Expected: PASS (13 testes)

- [ ] **Step 7: Escrever o teste da tela (falha)**

`tests/pacientes/test_tela_pacientes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def cliente_logado(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    sessao.add(
        Paciente(
            clinica_id=clinica.id, codigo_legado="0001/PT",
            nome="Claudia Moreira Sant'Ana",
            revisar_motivo=["data_suspeita", "telefone_incompleto"],
        )
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


def test_a_tela_lista_o_paciente(cliente_logado):
    resposta = cliente_logado.get("/pacientes?filtro=todos")
    assert resposta.status_code == 200
    assert "Claudia Moreira Sant'Ana" in resposta.text


def test_a_busca_e_o_primeiro_campo_da_tela(cliente_logado):
    """E o que ela faz o dia inteiro; nao pode estar escondido atras de um menu."""
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert html.index('class="busca"') < html.index("<table")


def test_dado_suspeito_aparece_marcado_nao_escondido(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'class="aviso"' in html


def test_a_tela_marca_a_aba_pacientes_como_ativa(cliente_logado):
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert 'href="/pacientes" class="ativo"' in html


def test_os_quatro_filtros_aparecem(cliente_logado):
    html = cliente_logado.get("/pacientes").text
    for rotulo in ("Ativos", "Com pendência", "Em aberto", "Todos"):
        assert rotulo in html


def test_cada_linha_leva_para_o_odontograma(cliente_logado, sessao):
    paciente = sessao.query(Paciente).one()
    html = cliente_logado.get("/pacientes?filtro=todos").text
    assert f'/odontograma/{paciente.id}' in html


def test_filtro_invalido_cai_no_padrao_em_vez_de_dar_erro(cliente_logado):
    assert cliente_logado.get("/pacientes?filtro=inventado").status_code == 200
```

Remova agora o `@pytest.mark.xfail` de `test_pagina_protegida_sem_sessao_manda_para_o_login` em `tests/auth/test_login.py`.

- [ ] **Step 8: Implementar rotas e template**

`app/pacientes/rotas.py`:

```python
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.pacientes.service import Filtro, buscar, contagens
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/pacientes", response_class=HTMLResponse)
def listar(
    request: Request,
    q: str = Query(""),
    filtro: str = Query(Filtro.ATIVOS.value),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        escolhido = Filtro(filtro)
    except ValueError:
        escolhido = Filtro.ATIVOS  # filtro inventado na URL nao derruba a tela

    return templates.TemplateResponse(
        request,
        "pacientes.html",
        {
            "aba": "pacientes",
            "termo": q,
            "filtro": escolhido,
            "filtros": list(Filtro),
            "linhas": buscar(
                sessao, clinica_id=usuario.clinica_id, termo=q, filtro=escolhido
            ),
            "numeros": contagens(sessao, clinica_id=usuario.clinica_id),
        },
    )
```

`app/templates/pacientes.html`:

```html
{% extends "base.html" %}
{% set rotulos = {
  'ativos': 'Ativos', 'com_pendencia': 'Com pendência',
  'em_aberto': 'Em aberto no financeiro', 'todos': 'Todos'
} %}
{% block titulo %}Pacientes — BDDente{% endblock %}
{% block conteudo %}
<h1>Pacientes</h1>
<p class="legenda-topo">
  {{ "{:,}".format(numeros.total).replace(",", ".") }} cadastrados ·
  {{ numeros.ativos }} atendidos nos últimos 4 anos ·
  {{ numeros.com_pendencia }} com tratamento pendente
</p>

<form class="busca" method="get" action="/pacientes">
  <span aria-hidden="true">⌕</span>
  <input name="q" value="{{ termo }}" autofocus
         placeholder="Buscar por nome, telefone ou código…">
  <input type="hidden" name="filtro" value="{{ filtro.value }}">
</form>

<div class="filtros">
  {% for f in filtros %}
    <a class="filtro {{ 'ativo' if f == filtro }}"
       href="/pacientes?filtro={{ f.value }}{% if termo %}&q={{ termo }}{% endif %}">
      {{ rotulos[f.value] }}
    </a>
  {% endfor %}
</div>

<table>
  <thead>
    <tr>
      <th>Paciente</th><th>Idade</th><th>Telefone</th><th>Último atendimento</th>
      <th>Convênio</th><th style="text-align:center">Pendentes</th>
      <th style="text-align:right">Em aberto</th>
    </tr>
  </thead>
  <tbody>
  {% for linha in linhas %}
    <tr onclick="location.href='/odontograma/{{ linha.id }}'" style="cursor:pointer">
      <td>
        <a class="nome" href="/odontograma/{{ linha.id }}">{{ linha.nome }}</a>
        <div class="codigo">{{ linha.codigo_legado or '—' }}</div>
      </td>
      <td>{% if linha.idade is not none %}{{ linha.idade }}
          {% else %}<span class="aviso">sem data</span>{% endif %}</td>
      <td>{% if linha.telefone %}{{ linha.telefone }}
            {% if linha.telefone_suspeito %}<span class="aviso">curto</span>{% endif %}
          {% else %}—{% endif %}</td>
      <td>{% if linha.ultimo_atendimento %}
            {{ linha.ultimo_atendimento.strftime('%d/%m/%Y') }}
            {% if linha.data_suspeita %}<span class="aviso">data inválida</span>{% endif %}
          {% else %}—{% endif %}</td>
      <td>{{ linha.convenio or 'Particular' }}</td>
      <td style="text-align:center">
        <span class="selo {{ 'pendente' if linha.pendentes else 'zero' }}">{{ linha.pendentes }}</span>
      </td>
      <td style="text-align:right" class="numero">
        {% if linha.em_aberto > 0 %}R$ {{ "%.2f"|format(linha.em_aberto) }}{% else %}—{% endif %}
      </td>
    </tr>
  {% else %}
    <tr><td colspan="7" style="color:var(--texto-fraco)">Nenhum paciente encontrado.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Em `app/main.py`, adicione `from app.pacientes import rotas as pacientes_rotas` e
`app.include_router(pacientes_rotas.router)`.

- [ ] **Step 9: Rodar e ver passar**

Run: `pytest tests/pacientes tests/auth -v`
Expected: PASS, sem xfail

- [ ] **Step 10: Commitar**

```bash
git add app/pacientes/service.py app/pacientes/rotas.py app/catalogo/service.py app/clinico/service.py app/templates/pacientes.html app/main.py tests/pacientes tests/auth/test_login.py
git commit -m "feat: tela de pacientes com busca, filtros e marcacao de dado suspeito"
```

---

### Task 13: API JSON do odontograma

O odontograma é a única ilha interativa do sistema. Esta task entrega os dados que ela consome; a Task 14 desenha.

**Files:**
- Modify: `app/clinico/service.py` (acrescentar)
- Create: `app/clinico/api.py`
- Modify: `app/main.py`
- Test: `tests/clinico/__init__.py`, `tests/clinico/test_api_odontograma.py`

**Interfaces:**
- Consumes: `app.clinico.models.*`, `app.catalogo.service`, `app.pacientes.service.obter`, `app.auth.auditoria.registrar`, `app.shared.dentes.*`.
- Produces:
  - `app.clinico.service.estado_do_odontograma(sessao, *, clinica_id, paciente_id, numero=1) -> dict`
  - `app.clinico.service.lancar(sessao, *, clinica_id, usuario_id, paciente_id, procedimento_id, escopo, dente=None, regioes=(), status, data=None, valor=None, observacao=None, numero_odontograma=1) -> Lancamento`
  - `app.clinico.service.historico(sessao, *, clinica_id, paciente_id, limite=200) -> list[dict]`
  - `app.clinico.service.excluir_lancamento(sessao, *, clinica_id, usuario_id, lancamento_id) -> bool` — exclusão **lógica**.
  - `app.clinico.service.EscopoInvalido` — exceção para combinações que o domínio recusa.
  - Endpoints: `GET /api/odontograma/{paciente_id}`, `POST /api/lancamento`, `DELETE /api/lancamento/{id}`.

**Formato de `estado_do_odontograma`** (contrato que a Task 14 consome):

```json
{
  "paciente": {"id": 12, "nome": "Amanda Ribeiro Nogueira", "codigo_legado": "6612/PT"},
  "odontograma": {"id": 3, "numero": 1},
  "dentes": {
    "16": {
      "raizes": 3,
      "canais": ["CANAL_MESIAL", "CANAL_CENTRAL", "CANAL_DISTAL"],
      "anterior": false,
      "regioes": {"OCLUSAL": "REALIZADO", "MESIAL": "PLANEJADO"},
      "dente_inteiro": "PLANEJADO",
      "condicoes": ["OICO14"]
    }
  },
  "boca": [{"lancamento_id": 91, "procedimento": "Consulta", "status": "REALIZADO"}]
}
```

`regioes` guarda, por região, o estado **mais forte** presente: `PLANEJADO` (vermelho)
vence `REALIZADO` (verde), que vence `EXISTENTE` (azul) — o que está por fazer nunca
some atrás do que já foi feito.

- [ ] **Step 1: Escrever o teste que falha**

`tests/clinico/test_api_odontograma.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Condicao, Lancamento, Odontograma
from app.clinico.service import (
    EscopoInvalido, estado_do_odontograma, excluir_lancamento, historico, lancar,
)
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento, TipoCondicao


@pytest.fixture
def cenario(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    sessao.add(categoria)
    sessao.flush()
    restauracao = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.MESIAL, Regiao.OCLUSAL],
    )
    consulta = Procedimento(
        clinica_id=clinica.id, codigo="1", nome="Consulta",
        categoria_id=categoria.id, escopo_sugerido=Escopo.BOCA, regioes_sugeridas=[],
    )
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([restauracao, consulta, paciente])
    sessao.flush()
    return clinica, usuario, paciente, restauracao, consulta


@pytest.fixture
def cliente(sessao, cenario):
    _, usuario, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c


# --- estado --------------------------------------------------------------------

def test_odontograma_vazio_traz_os_32_dentes(sessao, cenario):
    clinica, _, paciente, *_ = cenario
    estado = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )
    assert len(estado["dentes"]) == 32
    assert estado["dentes"]["16"]["regioes"] == {}
    assert estado["boca"] == []
    assert estado["paciente"]["nome"] == "Amanda"


def test_cada_dente_traz_sua_anatomia(sessao, cenario):
    clinica, _, paciente, *_ = cenario
    dentes = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]
    assert dentes["16"]["raizes"] == 3
    assert dentes["36"]["raizes"] == 2
    assert dentes["11"]["raizes"] == 1
    assert dentes["11"]["anterior"] is True
    assert dentes["16"]["anterior"] is False
    assert dentes["11"]["canais"] == ["CANAL_CENTRAL"]


def test_lancamento_em_regiao_aparece_no_estado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL, Regiao.OCLUSAL], status=StatusLancamento.PLANEJADO,
        valor=Decimal("180.00"),
    )
    sessao.flush()
    dente = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]["16"]
    assert dente["regioes"] == {"MESIAL": "PLANEJADO", "OCLUSAL": "PLANEJADO"}


def test_planejado_vence_realizado_na_mesma_regiao(sessao, cenario):
    """O que esta por fazer nunca some atras do que ja foi feito."""
    clinica, usuario, paciente, restauracao, _ = cenario
    for status in (StatusLancamento.REALIZADO, StatusLancamento.PLANEJADO):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.REGIOES, dente=16, regioes=[Regiao.OCLUSAL], status=status,
        )
    sessao.flush()
    dente = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]["16"]
    assert dente["regioes"]["OCLUSAL"] == "PLANEJADO"


def test_escopo_boca_vai_para_a_lista_boca_nao_para_um_dente(sessao, cenario):
    clinica, usuario, paciente, _, consulta = cenario
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=consulta.id, escopo=Escopo.BOCA,
        status=StatusLancamento.REALIZADO,
    )
    sessao.flush()
    estado = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )
    assert len(estado["boca"]) == 1
    assert estado["boca"][0]["procedimento"] == "Consulta"
    assert all(not d["regioes"] for d in estado["dentes"].values())


def test_condicao_existente_aparece_no_dente(sessao, cenario):
    clinica, _, paciente, *_ = cenario
    odo = Odontograma(paciente_id=paciente.id, numero=1)
    sessao.add(odo)
    sessao.flush()
    sessao.add(
        Condicao(odontograma_id=odo.id, dente=26, tipo=TipoCondicao.OUTRO,
                 regioes=[], icone_legado="OICO14")
    )
    sessao.flush()
    dentes = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]
    assert dentes["26"]["condicoes"] == ["OICO14"]


def test_lancamento_excluido_some_do_estado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.OCLUSAL], status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    assert excluir_lancamento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, lancamento_id=lancamento.id
    )
    sessao.flush()
    dentes = estado_do_odontograma(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id
    )["dentes"]
    assert dentes["16"]["regioes"] == {}


def test_exclusao_e_logica_o_registro_continua_no_banco(sessao, cenario):
    """Prontuario tem guarda minima de 10 anos. Nada e apagado de verdade."""
    clinica, usuario, paciente, restauracao, _ = cenario
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.DENTE, dente=16,
        status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    excluir_lancamento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, lancamento_id=lancamento.id
    )
    sessao.flush()
    guardado = sessao.get(Lancamento, lancamento.id)
    assert guardado is not None
    assert guardado.excluido_em is not None


# --- regras de escopo ----------------------------------------------------------

def test_escopo_boca_com_dente_e_recusado(sessao, cenario):
    clinica, usuario, paciente, _, consulta = cenario
    with pytest.raises(EscopoInvalido):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=consulta.id,
            escopo=Escopo.BOCA, dente=16, status=StatusLancamento.REALIZADO,
        )


def test_escopo_regioes_sem_regiao_e_recusado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    with pytest.raises(EscopoInvalido):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.REGIOES, dente=16, regioes=[],
            status=StatusLancamento.PLANEJADO,
        )


def test_dente_fora_da_notacao_fdi_e_recusado(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    with pytest.raises(EscopoInvalido):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.DENTE, dente=19, status=StatusLancamento.PLANEJADO,
        )


def test_qualquer_tratamento_pode_ir_em_qualquer_regiao(sessao, cenario):
    """Nao ha validacao de compatibilidade: o historico real mostra o mesmo
    tratamento em escopos diferentes, e travar rejeitaria dados verdadeiros."""
    clinica, usuario, paciente, _, consulta = cenario
    lancamento = lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=consulta.id, escopo=Escopo.REGIOES, dente=11,
        regioes=[Regiao.CANAL_CENTRAL], status=StatusLancamento.PLANEJADO,
    )
    assert lancamento.id is not None


# --- auditoria e API -----------------------------------------------------------

def test_todo_lancamento_deixa_rastro_na_auditoria(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=restauracao.id, escopo=Escopo.DENTE, dente=16,
        status=StatusLancamento.PLANEJADO,
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "lancamento")
    ).all()
    assert len(linhas) == 1
    assert linhas[0].acao == "CRIAR"
    assert linhas[0].usuario_id == usuario.id


def test_get_do_estado_devolve_json(cliente, cenario):
    _, _, paciente, *_ = cenario
    resposta = cliente.get(f"/api/odontograma/{paciente.id}")
    assert resposta.status_code == 200
    assert len(resposta.json()["dentes"]) == 32


def test_post_de_lancamento_grava_e_devolve_o_estado_novo(cliente, cenario):
    _, _, paciente, restauracao, _ = cenario
    resposta = cliente.post(
        "/api/lancamento",
        json={
            "paciente_id": paciente.id,
            "procedimento_id": restauracao.id,
            "escopo": "REGIOES",
            "dente": 16,
            "regioes": ["MESIAL", "OCLUSAL"],
            "status": "PLANEJADO",
            "valor": "180.00",
        },
    )
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["estado"]["dentes"]["16"]["regioes"]["MESIAL"] == "PLANEJADO"
    assert corpo["lancamento_id"] > 0


def test_post_invalido_devolve_422_com_explicacao(cliente, cenario):
    _, _, paciente, _, consulta = cenario
    resposta = cliente.post(
        "/api/lancamento",
        json={
            "paciente_id": paciente.id, "procedimento_id": consulta.id,
            "escopo": "BOCA", "dente": 16, "regioes": [], "status": "REALIZADO",
        },
    )
    assert resposta.status_code == 422
    assert "dente" in resposta.json()["detail"].lower()


def test_api_sem_sessao_e_recusada(sessao, cenario):
    _, _, paciente, *_ = cenario
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get(f"/api/odontograma/{paciente.id}").status_code == 303


def test_paciente_de_outra_clinica_da_404(cliente, sessao, cenario):
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="De outra clinica")
    sessao.add(alheio)
    sessao.flush()
    assert cliente.get(f"/api/odontograma/{alheio.id}").status_code == 404


def test_historico_vem_ordenado_do_mais_recente_para_o_mais_antigo(sessao, cenario):
    clinica, usuario, paciente, restauracao, _ = cenario
    for dia in (10, 20, 15):
        lancar(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, procedimento_id=restauracao.id,
            escopo=Escopo.DENTE, dente=16, status=StatusLancamento.REALIZADO,
            data=date(2026, 5, dia),
        )
    sessao.flush()
    datas = [
        item["data"] for item in historico(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    ]
    assert datas == sorted(datas, reverse=True)
```

Crie `tests/clinico/__init__.py` vazio.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/clinico/test_api_odontograma.py -v`
Expected: FAIL com `ImportError: cannot import name 'estado_do_odontograma'`

- [ ] **Step 3: Acrescentar a lógica em `app/clinico/service.py`**

Acrescente ao arquivo criado na Task 12:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

from app.auth.auditoria import registrar
from app.catalogo.models import Procedimento
from app.clinico.models import Condicao, LancamentoRegiao
from app.pacientes.service import obter as obter_paciente
from app.shared.dentes import TODOS_FDI, canais_do_dente, e_anterior, e_fdi_valido, numero_de_raizes
from app.shared.tipos import Escopo, Regiao

# Ordem de forca: o que esta por fazer nunca some atras do que ja foi feito.
FORCA = {"EXISTENTE": 0, "REALIZADO": 1, "PLANEJADO": 2}


class EscopoInvalido(ValueError):
    """Combinacao de escopo, dente e regioes que o dominio recusa."""


def _validar(escopo: Escopo, dente: int | None, regioes) -> None:
    if escopo is Escopo.BOCA:
        if dente is not None:
            raise EscopoInvalido("lancamento de boca toda nao pode ter dente")
        if regioes:
            raise EscopoInvalido("lancamento de boca toda nao pode ter regioes")
        return
    if dente is None:
        raise EscopoInvalido("lancamento em dente exige o numero do dente")
    if not e_fdi_valido(dente):
        raise EscopoInvalido(f"dente {dente} nao existe na notacao FDI permanente")
    if escopo is Escopo.REGIOES and not regioes:
        raise EscopoInvalido("escopo REGIOES exige ao menos uma regiao")
    if escopo is Escopo.DENTE and regioes:
        raise EscopoInvalido("escopo DENTE nao aceita regioes; use REGIOES")


def _odontograma_de(sessao: Session, paciente_id: int, numero: int) -> Odontograma:
    odontograma = sessao.scalars(
        select(Odontograma).where(
            Odontograma.paciente_id == paciente_id, Odontograma.numero == numero
        )
    ).first()
    if odontograma is None:
        odontograma = Odontograma(paciente_id=paciente_id, numero=numero)
        sessao.add(odontograma)
        sessao.flush()
    return odontograma


def lancar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    procedimento_id: int,
    escopo: Escopo,
    dente: int | None = None,
    regioes: "list[Regiao] | tuple[Regiao, ...]" = (),
    status: StatusLancamento,
    data: date | None = None,
    valor: Decimal | None = None,
    observacao: str | None = None,
    numero_odontograma: int = 1,
) -> Lancamento:
    regioes = list(regioes)
    _validar(escopo, dente, regioes)

    odontograma = _odontograma_de(sessao, paciente_id, numero_odontograma)
    realizado = status is StatusLancamento.REALIZADO
    lancamento = Lancamento(
        clinica_id=clinica_id,
        odontograma_id=odontograma.id,
        dente=dente,
        escopo=escopo,
        procedimento_id=procedimento_id,
        status=status,
        data_planejada=data if not realizado else None,
        data_realizada=data if realizado else None,
        valor=valor if valor is not None else Decimal("0.00"),
        observacao=observacao,
        criado_por=usuario_id,
    )
    sessao.add(lancamento)
    sessao.flush()
    for regiao in regioes:
        sessao.add(LancamentoRegiao(lancamento_id=lancamento.id, regiao=regiao))
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="CRIAR",
        entidade="lancamento",
        entidade_id=lancamento.id,
        depois={
            "dente": dente,
            "escopo": escopo.value,
            "regioes": [r.value for r in regioes],
            "status": status.value,
            "valor": str(lancamento.valor),
            "procedimento_id": procedimento_id,
        },
    )
    return lancamento


def excluir_lancamento(
    sessao: Session, *, clinica_id: int, usuario_id: int, lancamento_id: int
) -> bool:
    """Exclusao LOGICA. Nunca ha DELETE: prontuario tem guarda minima de 10 anos."""
    lancamento = sessao.scalars(
        select(Lancamento).where(
            Lancamento.id == lancamento_id,
            Lancamento.clinica_id == clinica_id,
            Lancamento.excluido_em.is_(None),
        )
    ).first()
    if lancamento is None:
        return False
    lancamento.excluido_em = datetime.now(timezone.utc)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="EXCLUIR",
        entidade="lancamento",
        entidade_id=lancamento.id,
        antes={"dente": lancamento.dente, "escopo": lancamento.escopo.value},
    )
    return True


def estado_do_odontograma(
    sessao: Session, *, clinica_id: int, paciente_id: int, numero: int = 1
) -> dict:
    # Fronteira de modulo: clinico nao consulta a tabela paciente, pergunta ao
    # service de pacientes.
    paciente = obter_paciente(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if paciente is None:
        raise LookupError("paciente nao encontrado nesta clinica")

    odontograma = _odontograma_de(sessao, paciente_id, numero)

    dentes: dict[str, dict] = {
        str(fdi): {
            "raizes": numero_de_raizes(fdi),
            "canais": [r.value for r in canais_do_dente(fdi)],
            "anterior": e_anterior(fdi),
            "regioes": {},
            "dente_inteiro": None,
            "condicoes": [],
        }
        for fdi in TODOS_FDI
    }
    boca: list[dict] = []

    linhas = sessao.execute(
        select(Lancamento, Procedimento.nome)
        .join(Procedimento, Lancamento.procedimento_id == Procedimento.id)
        .where(
            Lancamento.odontograma_id == odontograma.id,
            Lancamento.excluido_em.is_(None),
        )
    ).all()
    ids = [lancamento.id for lancamento, _ in linhas]
    regioes_por_lancamento: dict[int, list[str]] = {}
    if ids:
        for ligacao in sessao.scalars(
            select(LancamentoRegiao).where(LancamentoRegiao.lancamento_id.in_(ids))
        ):
            regioes_por_lancamento.setdefault(ligacao.lancamento_id, []).append(
                ligacao.regiao.value
            )

    def mais_forte(atual: str | None, novo: str) -> str:
        return novo if atual is None or FORCA[novo] > FORCA[atual] else atual

    for lancamento, nome_procedimento in linhas:
        estado = lancamento.status.value
        if lancamento.escopo is Escopo.BOCA:
            boca.append(
                {
                    "lancamento_id": lancamento.id,
                    "procedimento": nome_procedimento,
                    "status": estado,
                }
            )
            continue
        chave = str(lancamento.dente)
        if chave not in dentes:
            continue
        if lancamento.escopo is Escopo.DENTE:
            dentes[chave]["dente_inteiro"] = mais_forte(
                dentes[chave]["dente_inteiro"], estado
            )
            continue
        for regiao in regioes_por_lancamento.get(lancamento.id, []):
            dentes[chave]["regioes"][regiao] = mais_forte(
                dentes[chave]["regioes"].get(regiao), estado
            )

    for condicao in sessao.scalars(
        select(Condicao).where(
            Condicao.odontograma_id == odontograma.id, Condicao.excluido_em.is_(None)
        )
    ):
        chave = str(condicao.dente)
        if chave not in dentes:
            continue
        if condicao.icone_legado:
            dentes[chave]["condicoes"].append(condicao.icone_legado)
        for regiao in condicao.regioes or []:
            dentes[chave]["regioes"][regiao.value] = mais_forte(
                dentes[chave]["regioes"].get(regiao.value), "EXISTENTE"
            )

    return {
        "paciente": {
            "id": paciente.id,
            "nome": paciente.nome,
            "codigo_legado": paciente.codigo_legado,
        },
        "odontograma": {"id": odontograma.id, "numero": odontograma.numero},
        "dentes": dentes,
        "boca": boca,
    }


def historico(
    sessao: Session, *, clinica_id: int, paciente_id: int, limite: int = 200
) -> list[dict]:
    linhas = sessao.execute(
        select(Lancamento, Procedimento.nome)
        .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
        .join(Procedimento, Lancamento.procedimento_id == Procedimento.id)
        .where(
            Odontograma.paciente_id == paciente_id,
            Lancamento.clinica_id == clinica_id,
            Lancamento.excluido_em.is_(None),
        )
        .limit(limite)
    ).all()

    itens = [
        {
            "lancamento_id": lancamento.id,
            "data": lancamento.data_realizada or lancamento.data_planejada,
            "dente": lancamento.dente,
            "escopo": lancamento.escopo.value,
            "procedimento": nome,
            "status": lancamento.status.value,
            "valor": str(lancamento.valor),
            "observacao": lancamento.observacao,
        }
        for lancamento, nome in linhas
    ]
    # Lancamento sem data nenhuma vai para o fim, nao para o topo. O date.min no
    # lugar do None e obrigatorio: com dois lancamentos sem data, comparar
    # None com None levanta TypeError e derruba a tela.
    return sorted(
        itens, key=lambda i: (i["data"] is not None, i["data"] or date.min), reverse=True
    )


def lancamentos_do_paciente(
    sessao: Session, *, clinica_id: int, paciente_id: int
) -> list[dict]:
    """Fronteira que o futuro modulo financeiro vai consumir."""
    return historico(sessao, clinica_id=clinica_id, paciente_id=paciente_id, limite=10_000)
```

- [ ] **Step 4: Implementar `app/clinico/api.py`**

```python
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.clinico.service import (
    EscopoInvalido, estado_do_odontograma, excluir_lancamento, lancar,
)
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

router = APIRouter(prefix="/api")


class NovoLancamento(BaseModel):
    paciente_id: int
    procedimento_id: int
    escopo: Escopo
    dente: int | None = None
    regioes: list[Regiao] = Field(default_factory=list)
    status: StatusLancamento
    data: str | None = None
    valor: str | None = None
    observacao: str | None = None
    numero_odontograma: int = 1


@router.get("/odontograma/{paciente_id}")
def obter_estado(
    paciente_id: int,
    numero: int = 1,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        return estado_do_odontograma(
            sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id, numero=numero
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


@router.post("/lancamento", status_code=201)
def criar_lancamento(
    corpo: NovoLancamento,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    from datetime import date as _date

    try:
        valor = Decimal(corpo.valor) if corpo.valor else None
    except InvalidOperation as erro:
        raise HTTPException(status_code=422, detail="valor invalido") from erro
    try:
        quando = _date.fromisoformat(corpo.data) if corpo.data else None
    except ValueError as erro:
        raise HTTPException(status_code=422, detail="data invalida") from erro

    try:
        lancamento = lancar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            paciente_id=corpo.paciente_id,
            procedimento_id=corpo.procedimento_id,
            escopo=corpo.escopo,
            dente=corpo.dente,
            regioes=corpo.regioes,
            status=corpo.status,
            data=quando,
            valor=valor,
            observacao=corpo.observacao,
            numero_odontograma=corpo.numero_odontograma,
        )
    except EscopoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    sessao.commit()
    return {
        "lancamento_id": lancamento.id,
        "estado": estado_do_odontograma(
            sessao,
            clinica_id=usuario.clinica_id,
            paciente_id=corpo.paciente_id,
            numero=corpo.numero_odontograma,
        ),
    }


@router.delete("/lancamento/{lancamento_id}")
def apagar_lancamento(
    lancamento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    if not excluir_lancamento(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        lancamento_id=lancamento_id,
    ):
        raise HTTPException(status_code=404, detail="lancamento nao encontrado")
    sessao.commit()
    return {"ok": True}
```

Em `app/main.py`, adicione `from app.clinico import api as clinico_api` e
`app.include_router(clinico_api.router)`.

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/clinico/test_api_odontograma.py -v`
Expected: PASS (19 testes)

- [ ] **Step 6: Commitar**

```bash
git add app/clinico/service.py app/clinico/api.py app/main.py tests/clinico
git commit -m "feat: API JSON do odontograma com lancamento e exclusao logica"
```

---

### Task 14: Odontograma — o desenho

Layout **linear espaçoso** (opção B, aprovada): duas fileiras de 16 dentes, separação visível entre quadrantes, dentes grandes o bastante para acertar a região no clique. Numeração FDI entre as fileiras.

Cada dente é um **quadrado com miolo** — o miolo é onde mastiga (oclusal/incisal), as 4 bordas são as paredes — mais **1 a 3 hastes** que representam os canais da raiz. As 8 regiões são clicáveis.

**Decisão de projeto importante:** qual parede do desenho corresponde a qual região **depende do quadrante** (a tela é espelhada na linha média) e da arcada. Essa regra **não fica no JavaScript** — fica em `app/shared/dentes.py`, testada com o mesmo rigor da Task 3, e viaja no JSON. O JavaScript é um desenhista burro: pinta o que o servidor mandou. Errar espelhamento aqui pinta 30 anos de prontuário no lugar errado.

**Files:**
- Modify: `app/shared/dentes.py` (acrescentar), `app/clinico/service.py` (acrescentar geometria ao estado)
- Create: `app/clinico/rotas.py`, `app/templates/odontograma.html`, `app/static/odontograma.js`
- Modify: `app/main.py`, `app/static/bddente.css` (acrescentar)
- Test: `tests/shared/test_geometria_dente.py`, `tests/clinico/test_tela_odontograma.py`

**Interfaces:**
- Consumes: `app.clinico.service.estado_do_odontograma`, `app.clinico.service.historico`.
- Produces:
  - `app.catalogo.service.arvore(sessao, *, clinica_id) -> list[dict]` — catálogo agrupado por categoria (Step 9); a Task 16 também a consome.
  - `app.shared.dentes.Parede` — `StrEnum` com `CIMA`, `BAIXO`, `ESQUERDA`, `DIREITA`.
  - `app.shared.dentes.paredes_do_dente(fdi: int) -> dict[Parede, Regiao]`
  - `app.shared.dentes.canais_em_ordem_de_tela(fdi: int) -> tuple[Regiao, ...]` — da esquerda para a direita na tela.
  - `app.shared.dentes.arcada_superior(fdi: int) -> bool`
  - Cada dente no JSON ganha as chaves `paredes` e `canais_tela`.
  - Rota `GET /odontograma/{paciente_id}` (e `GET /odontograma` que redireciona para `/pacientes`).

- [ ] **Step 1: Escrever o teste da geometria (falha)**

`tests/shared/test_geometria_dente.py`:

```python
import pytest

from app.shared.dentes import (
    TODOS_FDI, Parede, arcada_superior, canais_em_ordem_de_tela,
    canais_do_dente, numero_de_raizes, paredes_do_dente,
)
from app.shared.tipos import REGIOES_COROA, Regiao


def test_toda_parede_de_todo_dente_e_uma_regiao_de_coroa_distinta():
    for fdi in TODOS_FDI:
        paredes = paredes_do_dente(fdi)
        assert set(paredes) == set(Parede)
        assert set(paredes.values()) == REGIOES_COROA - {Regiao.OCLUSAL}
```

```python
@pytest.mark.parametrize("fdi", [18, 11, 21, 28])
def test_na_arcada_de_cima_a_bochecha_fica_em_cima(fdi):
    """A raiz aponta para cima nos dentes superiores, e a face da bochecha
    (vestibular) acompanha — e como a tela do Dentalis sempre desenhou."""
    assert arcada_superior(fdi) is True
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.CIMA] is Regiao.VESTIBULAR
    assert paredes[Parede.BAIXO] is Regiao.LINGUAL


@pytest.mark.parametrize("fdi", [48, 41, 31, 38])
def test_na_arcada_de_baixo_tudo_inverte(fdi):
    assert arcada_superior(fdi) is False
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.CIMA] is Regiao.LINGUAL
    assert paredes[Parede.BAIXO] is Regiao.VESTIBULAR


@pytest.mark.parametrize("fdi", [18, 16, 11, 48, 46, 41])
def test_nos_quadrantes_1_e_4_a_linha_media_fica_a_direita(fdi):
    """Sao os dentes desenhados na METADE ESQUERDA da tela; andar para a direita
    aproxima da linha media, e aproximar da linha media e mesial."""
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.DIREITA] is Regiao.MESIAL
    assert paredes[Parede.ESQUERDA] is Regiao.DISTAL


@pytest.mark.parametrize("fdi", [21, 26, 28, 31, 36, 38])
def test_nos_quadrantes_2_e_3_o_espelho_inverte(fdi):
    paredes = paredes_do_dente(fdi)
    assert paredes[Parede.ESQUERDA] is Regiao.MESIAL
    assert paredes[Parede.DIREITA] is Regiao.DISTAL


def test_canais_na_ordem_da_tela_tem_o_mesmo_conjunto_da_anatomia():
    for fdi in TODOS_FDI:
        tela = canais_em_ordem_de_tela(fdi)
        assert len(tela) == numero_de_raizes(fdi)
        assert set(tela) == set(canais_do_dente(fdi))


def test_o_canal_mais_perto_da_linha_media_e_o_mesial():
    # dente 16 (quadrante 1, metade esquerda da tela): mesial e o da direita
    assert canais_em_ordem_de_tela(16)[-1] is Regiao.CANAL_MESIAL
    assert canais_em_ordem_de_tela(16)[0] is Regiao.CANAL_DISTAL
    # dente 26 (quadrante 2, metade direita): espelhado
    assert canais_em_ordem_de_tela(26)[0] is Regiao.CANAL_MESIAL
    assert canais_em_ordem_de_tela(26)[-1] is Regiao.CANAL_DISTAL


def test_dente_de_uma_raiz_so_tem_o_canal_central():
    assert canais_em_ordem_de_tela(11) == (Regiao.CANAL_CENTRAL,)
    assert canais_em_ordem_de_tela(44) == (Regiao.CANAL_CENTRAL,)


def test_dente_de_duas_raizes_nao_tem_canal_central():
    assert Regiao.CANAL_CENTRAL not in canais_em_ordem_de_tela(46)
    assert len(canais_em_ordem_de_tela(46)) == 2


def test_a_geometria_concorda_com_o_decodificador_do_legado():
    """Prova cruzada: a parede que o desenho chama de mesial e a mesma que o
    POSDENTE do Dentalis apontava como mesial. Se estas duas fontes divergirem,
    a tela vai pintar o historico no lugar errado."""
    from migracao.posdente import centro_da_celula, decodificar
    from app.shared.dentes import indice_legado_de_fdi

    for fdi in TODOS_FDI:
        indice = indice_legado_de_fdi(fdi)
        xc, yc = centro_da_celula(indice)
        paredes = paredes_do_dente(fdi)
        # dx +1 na grade legada = parede da direita no desenho
        assert decodificar(str(indice), f"{yc:>2}{xc + 1:>2}").regiao is paredes[Parede.DIREITA]
        assert decodificar(str(indice), f"{yc:>2}{xc - 1:>2}").regiao is paredes[Parede.ESQUERDA]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/shared/test_geometria_dente.py -v`
Expected: FAIL com `ImportError: cannot import name 'Parede'`

- [ ] **Step 3: Acrescentar a geometria em `app/shared/dentes.py`**

```python
from enum import StrEnum


class Parede(StrEnum):
    """Os quatro lados do quadrado que desenha um dente na tela."""

    CIMA = "CIMA"
    BAIXO = "BAIXO"
    ESQUERDA = "ESQUERDA"
    DIREITA = "DIREITA"


def arcada_superior(fdi: int) -> bool:
    return quadrante(fdi) in (1, 2)


def _mesial_a_direita_na_tela(fdi: int) -> bool:
    """A tela e espelhada na linha media (entre 11 e 21, e entre 41 e 31).

    Quadrantes 1 e 4 sao desenhados na metade ESQUERDA; para eles a linha media
    fica a direita, entao a parede da direita e a mesial. Quadrantes 2 e 3, o
    contrario.
    """
    return quadrante(fdi) in (1, 4)


def paredes_do_dente(fdi: int) -> dict[Parede, Regiao]:
    """Qual regiao cada lado do desenho representa.

    Esta funcao existe para que a regra de espelhamento NAO fique no JavaScript:
    ela e testada aqui e viaja pronta no JSON.
    """
    vestibular_em_cima = arcada_superior(fdi)
    mesial_a_direita = _mesial_a_direita_na_tela(fdi)
    return {
        Parede.CIMA: Regiao.VESTIBULAR if vestibular_em_cima else Regiao.LINGUAL,
        Parede.BAIXO: Regiao.LINGUAL if vestibular_em_cima else Regiao.VESTIBULAR,
        Parede.DIREITA: Regiao.MESIAL if mesial_a_direita else Regiao.DISTAL,
        Parede.ESQUERDA: Regiao.DISTAL if mesial_a_direita else Regiao.MESIAL,
    }


def canais_em_ordem_de_tela(fdi: int) -> tuple[Regiao, ...]:
    """Os canais da esquerda para a direita no desenho.

    canais_do_dente() devolve em ordem anatomica (mesial -> distal); aqui a ordem
    e a da tela, que inverte nos quadrantes 2 e 3.
    """
    canais = canais_do_dente(fdi)
    return canais if not _mesial_a_direita_na_tela(fdi) else tuple(reversed(canais))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/shared/test_geometria_dente.py -v`
Expected: PASS (10 testes) — inclusive a prova cruzada com o decodificador do legado

- [ ] **Step 5: Levar a geometria para o JSON**

Em `app/clinico/service.py`, na construção do dicionário `dentes` dentro de
`estado_do_odontograma`, acrescente duas chaves:

```python
from app.shared.dentes import canais_em_ordem_de_tela, paredes_do_dente

    dentes: dict[str, dict] = {
        str(fdi): {
            "raizes": numero_de_raizes(fdi),
            "canais": [r.value for r in canais_do_dente(fdi)],
            "canais_tela": [r.value for r in canais_em_ordem_de_tela(fdi)],
            "paredes": {p.value: r.value for p, r in paredes_do_dente(fdi).items()},
            "anterior": e_anterior(fdi),
            "regioes": {},
            "dente_inteiro": None,
            "condicoes": [],
        }
        for fdi in TODOS_FDI
    }
```

Acrescente ao teste `test_cada_dente_traz_sua_anatomia` em
`tests/clinico/test_api_odontograma.py`:

```python
    assert dentes["16"]["paredes"]["DIREITA"] == "MESIAL"
    assert dentes["26"]["paredes"]["DIREITA"] == "DISTAL"
    assert dentes["16"]["paredes"]["CIMA"] == "VESTIBULAR"
    assert dentes["46"]["paredes"]["CIMA"] == "LINGUAL"
    assert len(dentes["16"]["canais_tela"]) == 3
```

- [ ] **Step 6: Escrever o teste da tela (falha)**

`tests/clinico/test_tela_odontograma.py`:

```python
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.catalogo.models import Categoria, Procedimento
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo

JS = Path("app/static/odontograma.js")


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    paciente = Paciente(clinica_id=clinica.id, codigo_legado="0001/PT", nome="Amanda")
    sessao.add_all([categoria, paciente])
    sessao.flush()
    sessao.add(
        Procedimento(
            clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
            categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES,
            regioes_sugeridas=[],
        )
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c, paciente


def test_a_tela_abre_e_mostra_o_nome_do_paciente(cliente):
    c, paciente = cliente
    resposta = c.get(f"/odontograma/{paciente.id}")
    assert resposta.status_code == 200
    assert "Amanda" in resposta.text


def test_o_estado_inteiro_vem_embutido_na_pagina(cliente):
    """Sem segunda ida ao servidor so para desenhar: a tela ja nasce pronta."""
    c, paciente = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    bruto = re.search(
        r'id="estado-inicial"[^>]*>(.*?)</script>', html, re.S
    )
    assert bruto, "o JSON de estado nao esta embutido na pagina"
    estado = json.loads(bruto.group(1))
    assert len(estado["dentes"]) == 32
    assert estado["dentes"]["16"]["paredes"]["DIREITA"] == "MESIAL"


def test_a_tela_marca_a_aba_odontograma(cliente):
    c, paciente = cliente
    assert 'href="/odontograma" class="ativo"' in c.get(f"/odontograma/{paciente.id}").text


def test_a_legenda_das_tres_cores_aparece(cliente):
    c, paciente = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    for rotulo in ("Planejado", "Realizado", "Já existente"):
        assert rotulo in html


def test_paciente_inexistente_da_404(cliente):
    c, _ = cliente
    assert c.get("/odontograma/999999").status_code == 404


def test_odontograma_sem_paciente_volta_para_a_lista(cliente):
    c, _ = cliente
    resposta = c.get("/odontograma")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/pacientes"


# --- contrato do desenhista ----------------------------------------------------

def test_o_javascript_le_a_geometria_do_servidor_e_nao_a_recalcula():
    """Se o JS voltar a decidir sozinho qual parede e mesial, a regra de
    espelhamento passa a existir em dois lugares — e um deles nao tem teste."""
    fonte = JS.read_text(encoding="utf-8")
    assert "paredes" in fonte
    assert "canais_tela" in fonte
    for proibido in ("quadrante", "% 10", "fdi < 30"):
        assert proibido not in fonte, f"logica de anatomia vazou para o JS: {proibido}"


def test_toda_regiao_desenhada_carrega_dente_e_regiao_no_elemento():
    fonte = JS.read_text(encoding="utf-8")
    assert "data-dente" in fonte
    assert "data-regiao" in fonte
```

- [ ] **Step 7: Escrever `app/static/odontograma.js`**

```javascript
/* BDDente — odontograma.
 *
 * Este arquivo NAO sabe anatomia. Qual parede e mesial, quantos canais o dente
 * tem e em que ordem eles aparecem vem prontos do servidor, em `paredes` e
 * `canais_tela`. A regra de espelhamento mesial/distal vive em
 * app/shared/dentes.py, onde ha teste. Nao a reimplemente aqui.
 */
(function () {
  "use strict";

  var COR = {
    PLANEJADO: "#DC2626",
    REALIZADO: "#16A34A",
    EXISTENTE: "#2563EB"
  };
  var VAZIO = "#FFFFFF";
  var TRACO = "#94A3B8";

  var LADO = 42;      // aresta do quadrado do dente
  var VAO = 8;        // espaco entre dentes vizinhos
  var VAO_QUADRANTE = 22;
  var RAIZ = LADO * 0.42;
  var MIOLO = LADO * 0.30;   // espessura das paredes
  var FAIXA_NUMEROS = 26;

  var estado = null;
  var aoClicar = null;

  function pintar(dente, regiao) {
    var valor = dente.regioes[regiao];
    return valor ? COR[valor] : VAZIO;
  }

  function caminho(pontos, preenchimento, fdi, regiao) {
    return (
      '<path d="' + pontos + '" fill="' + preenchimento + '" stroke="' + TRACO +
      '" stroke-width="1" class="regiao" data-dente="' + fdi +
      '" data-regiao="' + regiao + '"><title>' + regiao + "</title></path>"
    );
  }

  function desenharDente(fdi, dente, raizParaCima) {
    var a = 0, b = LADO, i = MIOLO, j = LADO - MIOLO;
    var partes = "";

    // --- raizes: uma haste por canal, na ordem que o servidor mandou ---
    var canais = dente.canais_tela;
    var passo = LADO / (canais.length + 1);
    for (var k = 0; k < canais.length; k++) {
      var x = passo * (k + 1);
      var base = raizParaCima ? 0 : LADO;
      var ponta = raizParaCima ? -RAIZ : LADO + RAIZ;
      partes += caminho(
        "M" + (x - LADO * 0.07) + "," + base +
        " L" + x + "," + ponta +
        " L" + (x + LADO * 0.07) + "," + base + "Z",
        pintar(dente, canais[k]), fdi, canais[k]
      );
    }

    // --- as 4 paredes: trapezios entre o quadrado externo e o miolo ---
    var p = dente.paredes;
    partes += caminho("M" + a + "," + a + " L" + b + "," + a + " L" + j + "," + i + " L" + i + "," + i + "Z",
      pintar(dente, p.CIMA), fdi, p.CIMA);
    partes += caminho("M" + b + "," + a + " L" + b + "," + b + " L" + j + "," + j + " L" + j + "," + i + "Z",
      pintar(dente, p.DIREITA), fdi, p.DIREITA);
    partes += caminho("M" + b + "," + b + " L" + a + "," + b + " L" + i + "," + j + " L" + j + "," + j + "Z",
      pintar(dente, p.BAIXO), fdi, p.BAIXO);
    partes += caminho("M" + a + "," + b + " L" + a + "," + a + " L" + i + "," + i + " L" + i + "," + j + "Z",
      pintar(dente, p.ESQUERDA), fdi, p.ESQUERDA);

    // --- miolo: onde mastiga (oclusal, ou incisal nos dentes da frente) ---
    partes +=
      '<rect x="' + i + '" y="' + i + '" width="' + (j - i) + '" height="' + (j - i) +
      '" fill="' + pintar(dente, "OCLUSAL") + '" stroke="' + TRACO +
      '" stroke-width="1" class="regiao" data-dente="' + fdi +
      '" data-regiao="OCLUSAL"><title>' +
      (dente.anterior ? "Incisal" : "Oclusal") + "</title></rect>";

    // --- moldura do dente inteiro: escopo DENTE pinta a borda, nao as paredes ---
    if (dente.dente_inteiro) {
      partes +=
        '<rect x="-2" y="-2" width="' + (LADO + 4) + '" height="' + (LADO + 4) +
        '" fill="none" stroke="' + COR[dente.dente_inteiro] +
        '" stroke-width="2.5" rx="3" pointer-events="none"/>';
    }
    // --- marca de condicao existente sem regiao definida ---
    if (dente.condicoes.length && !dente.dente_inteiro) {
      partes +=
        '<circle cx="' + (LADO - 4) + '" cy="4" r="3.5" fill="' + COR.EXISTENTE +
        '" pointer-events="none"><title>' + dente.condicoes.join(", ") + "</title></circle>";
    }
    return partes;
  }

  function desenharFileira(ordem, raizParaCima) {
    var partes = "", marcas = [], x = 0;
    for (var k = 0; k < ordem.length; k++) {
      if (k === 8) x += VAO_QUADRANTE;  // respiro entre os quadrantes
      var fdi = ordem[k];
      partes +=
        '<g transform="translate(' + x + ',0)" class="dente" data-dente="' + fdi + '">' +
        desenharDente(fdi, estado.dentes[fdi], raizParaCima) + "</g>";
      marcas.push({ x: x + LADO / 2, fdi: fdi });
      x += LADO + VAO;
    }
    return { svg: partes, largura: x - VAO, marcas: marcas };
  }

  var SUPERIOR = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
  var INFERIOR = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];

  function desenhar(alvo) {
    var cima = desenharFileira(SUPERIOR, true);
    var baixo = desenharFileira(INFERIOR, false);
    var largura = Math.max(cima.largura, baixo.largura);
    var yCima = RAIZ + 6;
    var yBaixo = yCima + LADO + FAIXA_NUMEROS + 16;
    var altura = yBaixo + LADO + RAIZ + 10;

    var svg =
      '<svg width="' + (largura + 24) + '" height="' + altura +
      '" viewBox="-12 0 ' + (largura + 24) + " " + altura +
      '" role="img" aria-label="Odontograma">';
    svg += '<g transform="translate(0,' + yCima + ')">' + cima.svg + "</g>";
    svg +=
      '<g font-size="12" font-family="ui-monospace,monospace" fill="#475569" text-anchor="middle">';
    cima.marcas.forEach(function (m) {
      svg += '<text x="' + m.x + '" y="' + (yCima + LADO + 16) + '">' + m.fdi + "</text>";
    });
    baixo.marcas.forEach(function (m) {
      svg += '<text x="' + m.x + '" y="' + (yBaixo - 8) + '">' + m.fdi + "</text>";
    });
    svg += "</g>";
    svg +=
      '<line x1="-8" y1="' + (yCima + LADO + 23) + '" x2="' + (largura + 8) +
      '" y2="' + (yCima + LADO + 23) + '" stroke="#CBD5E1"/>';
    svg += '<g transform="translate(0,' + yBaixo + ')">' + baixo.svg + "</g>";
    svg += "</svg>";
    alvo.innerHTML = svg;
  }

  function montar(opcoes) {
    var alvo = document.getElementById(opcoes.alvo);
    estado = opcoes.estado;
    aoClicar = opcoes.aoClicar || function () {};

    desenhar(alvo);

    alvo.addEventListener("click", function (evento) {
      var parte = evento.target.closest(".regiao");
      if (!parte) return;
      aoClicar({
        dente: parseInt(parte.getAttribute("data-dente"), 10),
        regiao: parte.getAttribute("data-regiao")
      });
    });

    return {
      atualizar: function (novoEstado) {
        estado = novoEstado;
        desenhar(alvo);
      },
      estado: function () {
        return estado;
      }
    };
  }

  window.Odontograma = { montar: montar };
})();
```

- [ ] **Step 8: Escrever `app/clinico/rotas.py` e o template**

`app/clinico/rotas.py`:

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.service import arvore
from app.clinico.service import estado_do_odontograma, historico
from app.shared.db import obter_sessao
from app.templates import templates

router = APIRouter()


@router.get("/odontograma")
def sem_paciente():
    """Sem paciente escolhido nao ha o que desenhar: volta para a busca."""
    return RedirectResponse("/pacientes", status_code=303)


@router.get("/odontograma/{paciente_id}", response_class=HTMLResponse)
def tela(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        estado = estado_do_odontograma(
            sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    return templates.TemplateResponse(
        request,
        "odontograma.html",
        {
            "aba": "odontograma",
            "estado": estado,
            "catalogo": arvore(sessao, clinica_id=usuario.clinica_id),
            "historico": historico(
                sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
            ),
        },
    )
```

`app/templates/odontograma.html`:

```html
{% extends "base.html" %}
{% block titulo %}{{ estado.paciente.nome }} — BDDente{% endblock %}
{% block conteudo %}
<h1>{{ estado.paciente.nome }}</h1>
<p class="legenda-topo">
  {{ estado.paciente.codigo_legado or '—' }} ·
  <a href="/pacientes">voltar para a lista</a> ·
  <a href="/anamnese/{{ estado.paciente.id }}">anamnese</a> ·
  <a href="/prontuario/{{ estado.paciente.id }}.pdf">prontuário em PDF</a>
</p>

<div class="odonto-area">
  <div class="odonto-desenho">
    <div id="odontograma"></div>
    <div class="legenda-cores">
      <span><i style="background:var(--planejado)"></i>Planejado</span>
      <span><i style="background:var(--realizado)"></i>Realizado</span>
      <span><i style="background:var(--existente)"></i>Já existente</span>
      <span><i style="background:#fff;border:1px solid #94A3B8"></i>Sem nada</span>
    </div>
  </div>

  {% include "_painel_lancamento.html" %}
</div>

<h2 class="titulo-historico">Histórico</h2>
<table>
  <thead>
    <tr><th>Data</th><th>Dente</th><th>Tratamento</th><th>Situação</th>
        <th style="text-align:right">Valor</th></tr>
  </thead>
  <tbody>
  {% for item in historico %}
    <tr>
      <td>{{ item.data.strftime('%d/%m/%Y') if item.data else '—' }}</td>
      <td>{{ item.dente or 'boca toda' }}</td>
      <td>{{ item.procedimento }}</td>
      <td>{{ 'Realizado' if item.status == 'REALIZADO' else 'Planejado' }}</td>
      <td style="text-align:right" class="numero">R$ {{ item.valor }}</td>
    </tr>
  {% else %}
    <tr><td colspan="5" style="color:var(--texto-fraco)">Nenhum lançamento ainda.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}

{% block scripts %}
<script type="application/json" id="estado-inicial">{{ estado | tojson }}</script>
<script type="application/json" id="catalogo">{{ catalogo | tojson }}</script>
<script src="/static/odontograma.js"></script>
<script src="/static/painel.js"></script>
{% endblock %}
```

Crie `app/templates/_painel_lancamento.html` e `app/static/painel.js` **vazios** por
enquanto — a Task 15 os preenche. Sem eles o template quebra.

Acrescente ao final de `app/static/bddente.css`:

```css
/* --- odontograma --- */
.odonto-area { display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }
.odonto-desenho {
  flex: 1 1 640px;
  min-width: 0;
  background: #FCFCFD;
  border: 1px solid #F1F5F9;
  border-radius: 12px;
  padding: 16px 10px;
  overflow-x: auto;
}
#odontograma svg { display: block; margin: auto; }
.regiao { cursor: pointer; }
.regiao:hover { stroke: var(--roxo); stroke-width: 2; }
.legenda-cores {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #475569;
  margin-top: 14px;
  padding-left: 6px;
}
.legenda-cores i {
  width: 11px; height: 11px; border-radius: 3px;
  display: inline-block; margin-right: 5px; vertical-align: -1px;
}
.titulo-historico { font-size: 16px; margin: 26px 0 8px; }
```

Em `app/main.py`, adicione `from app.clinico import rotas as clinico_rotas` e
`app.include_router(clinico_rotas.router)`.

- [ ] **Step 9: Acrescentar `arvore` em `app/catalogo/service.py`**

```python
from app.catalogo.models import Categoria, Preco, Procedimento


def arvore(sessao: Session, *, clinica_id: int) -> list[dict]:
    """Catalogo agrupado por categoria, na ordem da tela. Alimenta o painel de
    lancamento e a tela de tratamentos."""
    categorias = list(
        sessao.scalars(
            select(Categoria)
            .where(Categoria.clinica_id == clinica_id)
            .order_by(Categoria.ordem, Categoria.nome)
        )
    )
    procedimentos = list(
        sessao.scalars(
            select(Procedimento)
            .where(Procedimento.clinica_id == clinica_id, Procedimento.ativo.is_(True))
            .order_by(Procedimento.nome)
        )
    )
    por_categoria: dict[int, list[dict]] = {}
    for p in procedimentos:
        por_categoria.setdefault(p.categoria_id, []).append(
            {
                "id": p.id,
                "codigo": p.codigo,
                "nome": p.nome,
                "escopo_sugerido": p.escopo_sugerido.value,
                "regioes_sugeridas": [r.value for r in (p.regioes_sugeridas or [])],
                "duracao_min": p.duracao_min,
            }
        )
    return [
        {
            "id": c.id,
            "codigo": c.codigo,
            "nome": c.nome,
            "procedimentos": por_categoria.get(c.id, []),
        }
        for c in categorias
        if por_categoria.get(c.id)
    ]
```

- [ ] **Step 10: Rodar e ver passar**

Run: `pytest tests/shared tests/clinico -v`
Expected: PASS

- [ ] **Step 11: Olhar com os próprios olhos**

Os testes garantem a geometria, não que a tela esteja bonita. Suba e veja:

```bash
uvicorn app.main:app --reload
```
Abra `http://localhost:8000/pacientes`, clique num paciente e confira:
32 dentes em duas fileiras · respiro entre os quadrantes · numeração FDI no meio ·
1 a 3 hastes conforme o dente · hover roxo na região sob o cursor.

- [ ] **Step 12: Commitar**

```bash
git add app/shared/dentes.py app/clinico/service.py app/clinico/rotas.py app/catalogo/service.py app/templates/odontograma.html app/templates/_painel_lancamento.html app/static/odontograma.js app/static/painel.js app/static/bddente.css app/main.py tests/shared/test_geometria_dente.py tests/clinico
git commit -m "feat: odontograma em SVG com geometria vinda do servidor"
```

---

### Task 15: Painel de lançamento

O painel fica **sempre visível ao lado do odontograma**. O fluxo é: clica no dente (ou numa região), escolhe o tratamento, o escopo e as regiões já vêm **pré-marcados conforme o hábito dela**, confere e lança.

O botão **"Repetir em outro dente"** existe porque 46% das consultas com mais de um lançamento repetem o mesmo tratamento em vários dentes: ele mantém o tratamento carregado e transforma cada clique seguinte num lançamento.

**Files:**
- Create: `app/templates/_painel_lancamento.html`, `app/static/painel.js` (preencher os vazios da Task 14)
- Modify: `app/static/bddente.css`
- Test: `tests/clinico/test_painel.py`

**Interfaces:**
- Consumes: `window.Odontograma.montar` (Task 14), `POST /api/lancamento` (Task 13), o JSON `#catalogo`.
- Produces: nenhuma API nova. O painel é HTML + JS que consomem o que já existe.

- [ ] **Step 1: Escrever o teste que falha**

`tests/clinico/test_painel.py`:

```python
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.catalogo.models import Categoria, Procedimento
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

PAINEL = Path("app/templates/_painel_lancamento.html")
JS = Path("app/static/painel.js")


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    paciente = Paciente(clinica_id=clinica.id, nome="Amanda")
    sessao.add_all([categoria, paciente])
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.MESIAL, Regiao.OCLUSAL],
    )
    sessao.add(proc)
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        yield c, paciente, proc


def test_o_painel_fica_ao_lado_do_odontograma_sempre_visivel(cliente):
    """Nao e modal nem outra tela: ela precisa ver o dente enquanto lanca."""
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert 'class="odonto-area"' in html
    assert html.index('id="odontograma"') < html.index('id="painel"')


def test_o_painel_traz_as_categorias_e_os_tratamentos(cliente):
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert "Dentistica" in html or "Dentística" in html
    assert "Restauracao Classe II" in html


def test_as_oito_regioes_aparecem_como_caixas_marcaveis(cliente):
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    for regiao in Regiao:
        assert f'value="{regiao.value}"' in html


def test_o_painel_oferece_planejado_e_realizado(cliente):
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    for status in StatusLancamento:
        assert f'value="{status.value}"' in html


def test_o_botao_repetir_em_outro_dente_existe(cliente):
    """46% das consultas com mais de um lancamento repetem o mesmo tratamento."""
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert "Repetir em outro dente" in html


def test_o_sugerido_do_procedimento_viaja_para_a_tela(cliente):
    c, paciente, proc = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    bruto = re.search(r'id="catalogo"[^>]*>(.*?)</script>', html, re.S)
    assert bruto
    import json

    catalogo = json.loads(bruto.group(1))
    achado = next(
        p for cat in catalogo for p in cat["procedimentos"] if p["id"] == proc.id
    )
    assert achado["escopo_sugerido"] == "REGIOES"
    assert achado["regioes_sugeridas"] == ["MESIAL", "OCLUSAL"]


# --- contrato do JS ------------------------------------------------------------

def test_o_js_pre_marca_o_sugerido_mas_nao_impede_mudar():
    """A tela sugere, nao impoe: qualquer tratamento pode ir em qualquer regiao."""
    fonte = JS.read_text(encoding="utf-8")
    assert "regioes_sugeridas" in fonte
    assert "disabled" not in fonte or "modo_repetir" in fonte


def test_o_js_manda_o_lancamento_para_a_api_certa():
    fonte = JS.read_text(encoding="utf-8")
    assert "/api/lancamento" in fonte
    assert "atualizar" in fonte  # redesenha o odontograma com o estado devolvido


def test_o_js_trata_erro_da_api_em_vez_de_falhar_calado():
    fonte = JS.read_text(encoding="utf-8")
    assert "catch" in fonte
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/clinico/test_painel.py -v`
Expected: FAIL — o painel e o JS estão vazios

- [ ] **Step 3: Escrever `app/templates/_painel_lancamento.html`**

```html
<aside class="painel" id="painel">
  <div class="painel-alvo" id="painel-alvo">
    Clique num dente para começar
  </div>

  <label class="rotulo" for="painel-categoria">Categoria</label>
  <select id="painel-categoria">
    <option value="">Escolha…</option>
    {% for categoria in catalogo %}
      <option value="{{ categoria.id }}">{{ categoria.nome }}</option>
    {% endfor %}
  </select>

  <label class="rotulo" for="painel-procedimento">Tratamento</label>
  <select id="painel-procedimento" disabled>
    <option value="">Escolha a categoria primeiro…</option>
    {% for categoria in catalogo %}
      {% for procedimento in categoria.procedimentos %}
        <option value="{{ procedimento.id }}" data-categoria="{{ categoria.id }}" hidden>
          {{ procedimento.nome }}
        </option>
      {% endfor %}
    {% endfor %}
  </select>

  <label class="rotulo">Onde</label>
  <div class="escopos" id="painel-escopos">
    <label><input type="radio" name="escopo" value="BOCA"> Boca toda</label>
    <label><input type="radio" name="escopo" value="DENTE"> Dente inteiro</label>
    <label><input type="radio" name="escopo" value="REGIOES" checked> Regiões</label>
  </div>

  <fieldset class="regioes" id="painel-regioes">
    <legend>Coroa</legend>
    <label><input type="checkbox" name="regiao" value="MESIAL"> Mesial</label>
    <label><input type="checkbox" name="regiao" value="DISTAL"> Distal</label>
    <label><input type="checkbox" name="regiao" value="VESTIBULAR"> Vestibular</label>
    <label><input type="checkbox" name="regiao" value="LINGUAL"> Lingual</label>
    <label><input type="checkbox" name="regiao" value="OCLUSAL">
      <span id="rotulo-oclusal">Oclusal</span></label>
    <legend class="legenda-raiz">Raiz</legend>
    <label><input type="checkbox" name="regiao" value="CANAL_MESIAL"> Canal mesial</label>
    <label><input type="checkbox" name="regiao" value="CANAL_CENTRAL"> Canal central</label>
    <label><input type="checkbox" name="regiao" value="CANAL_DISTAL"> Canal distal</label>
  </fieldset>

  <label class="rotulo">Situação</label>
  <div class="escopos">
    <label><input type="radio" name="status" value="PLANEJADO" checked> Planejado</label>
    <label><input type="radio" name="status" value="REALIZADO"> Realizado</label>
  </div>

  <div class="linha-dupla">
    <div>
      <label class="rotulo" for="painel-data">Data</label>
      <input type="date" id="painel-data">
    </div>
    <div>
      <label class="rotulo" for="painel-valor">Valor (R$)</label>
      <input type="text" id="painel-valor" inputmode="decimal" placeholder="0,00">
    </div>
  </div>

  <label class="rotulo" for="painel-observacao">Observação</label>
  <input type="text" id="painel-observacao" placeholder="opcional">

  <p class="painel-erro" id="painel-erro" hidden></p>

  <button type="button" class="primario" id="painel-lancar" disabled>Lançar</button>
  <button type="button" class="secundario" id="painel-repetir" disabled>
    Repetir em outro dente
  </button>
  <p class="painel-dica" id="painel-dica" hidden>
    Modo repetir ligado — cada clique no odontograma lança este mesmo tratamento.
    <a href="#" id="painel-parar-repetir">parar</a>
  </p>
</aside>
```

- [ ] **Step 4: Escrever `app/static/painel.js`**

```javascript
/* BDDente — painel de lancamento, ao lado do odontograma.
 *
 * A tela SUGERE, nunca impede: o escopo e as regioes vem pre-marcados conforme o
 * habito da dentista (calculado do historico na migracao), e ela pode mudar tudo.
 * Qualquer tratamento pode ir em qualquer regiao — o historico real mostra o
 * mesmo tratamento em escopos diferentes.
 */
(function () {
  "use strict";

  var estadoInicial = JSON.parse(document.getElementById("estado-inicial").textContent);
  var catalogo = JSON.parse(document.getElementById("catalogo").textContent);

  var porId = {};
  catalogo.forEach(function (categoria) {
    categoria.procedimentos.forEach(function (p) { porId[p.id] = p; });
  });

  var el = function (id) { return document.getElementById(id); };
  var alvo = { dente: null, regiao: null };
  var repetindo = false;

  var odontograma = window.Odontograma.montar({
    alvo: "odontograma",
    estado: estadoInicial,
    aoClicar: function (clique) {
      if (repetindo) {
        alvo = clique;
        enviar();
        return;
      }
      alvo = clique;
      mostrarAlvo();
      if (elEscopo() === "REGIOES") marcarSomente([clique.regiao]);
      atualizarBotoes();
    }
  });

  function elEscopo() {
    var escolhido = document.querySelector('input[name="escopo"]:checked');
    return escolhido ? escolhido.value : "REGIOES";
  }

  function regioesMarcadas() {
    return Array.prototype.slice
      .call(document.querySelectorAll('input[name="regiao"]:checked'))
      .map(function (c) { return c.value; });
  }

  function marcarSomente(valores) {
    document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
      caixa.checked = valores.indexOf(caixa.value) !== -1;
    });
  }

  function mostrarAlvo() {
    if (alvo.dente === null) {
      el("painel-alvo").textContent = "Clique num dente para começar";
      return;
    }
    var dente = estadoInicial.dentes[alvo.dente];
    var nomeOclusal = dente && dente.anterior ? "Incisal" : "Oclusal";
    el("rotulo-oclusal").textContent = nomeOclusal;
    el("painel-alvo").innerHTML =
      "Dente <b>" + alvo.dente + "</b>" +
      (elEscopo() === "REGIOES" && alvo.regiao
        ? " · " + (alvo.regiao === "OCLUSAL" ? nomeOclusal : alvo.regiao.toLowerCase())
        : "");
  }

  function atualizarBotoes() {
    var procedimento = el("painel-procedimento").value;
    var escopo = elEscopo();
    var temAlvo = escopo === "BOCA" || alvo.dente !== null;
    var temRegiao = escopo !== "REGIOES" || regioesMarcadas().length > 0;
    var pronto = Boolean(procedimento) && temAlvo && temRegiao;
    el("painel-lancar").disabled = !pronto;
    el("painel-repetir").disabled = !Boolean(procedimento);
    el("painel-regioes").hidden = escopo !== "REGIOES";
  }

  // --- categoria filtra os tratamentos ---
  el("painel-categoria").addEventListener("change", function () {
    var categoria = this.value;
    var seletor = el("painel-procedimento");
    seletor.disabled = !categoria;
    seletor.value = "";
    Array.prototype.slice.call(seletor.options).forEach(function (opcao) {
      if (!opcao.value) return;
      opcao.hidden = opcao.getAttribute("data-categoria") !== categoria;
    });
    atualizarBotoes();
  });

  // --- escolher o tratamento pre-marca o habito dela ---
  el("painel-procedimento").addEventListener("change", function () {
    var procedimento = porId[this.value];
    if (procedimento) {
      var radio = document.querySelector(
        'input[name="escopo"][value="' + procedimento.escopo_sugerido + '"]'
      );
      if (radio) radio.checked = true;
      if (procedimento.escopo_sugerido === "REGIOES") {
        var sugeridas = procedimento.regioes_sugeridas.slice();
        // a regiao que ela acabou de clicar tem prioridade sobre a sugestao
        if (alvo.regiao && sugeridas.indexOf(alvo.regiao) === -1) sugeridas = [alvo.regiao];
        marcarSomente(sugeridas);
      }
    }
    mostrarAlvo();
    atualizarBotoes();
  });

  document.querySelectorAll('input[name="escopo"]').forEach(function (radio) {
    radio.addEventListener("change", function () { mostrarAlvo(); atualizarBotoes(); });
  });
  document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
    caixa.addEventListener("change", atualizarBotoes);
  });

  // --- enviar ---
  function mostrarErro(texto) {
    var caixa = el("painel-erro");
    caixa.textContent = texto;
    caixa.hidden = !texto;
  }

  function enviar() {
    var escopo = elEscopo();
    var valorBruto = el("painel-valor").value.trim().replace(/\./g, "").replace(",", ".");
    var corpo = {
      paciente_id: estadoInicial.paciente.id,
      procedimento_id: parseInt(el("painel-procedimento").value, 10),
      escopo: escopo,
      dente: escopo === "BOCA" ? null : alvo.dente,
      regioes: escopo === "REGIOES" ? regioesMarcadas() : [],
      status: document.querySelector('input[name="status"]:checked').value,
      data: el("painel-data").value || null,
      valor: valorBruto || null,
      observacao: el("painel-observacao").value.trim() || null,
      numero_odontograma: estadoInicial.odontograma.numero
    };

    el("painel-lancar").disabled = true;
    mostrarErro("");

    fetch("/api/lancamento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo)
    })
      .then(function (resposta) {
        return resposta.json().then(function (dados) {
          if (!resposta.ok) throw new Error(dados.detail || "não foi possível lançar");
          return dados;
        });
      })
      .then(function (dados) {
        estadoInicial = dados.estado;
        odontograma.atualizar(dados.estado);
        if (!repetindo) {
          alvo = { dente: null, regiao: null };
          mostrarAlvo();
        }
        atualizarBotoes();
      })
      .catch(function (erro) {
        mostrarErro(erro.message);
        atualizarBotoes();
      });
  }

  el("painel-lancar").addEventListener("click", enviar);

  // --- repetir em outro dente ---
  el("painel-repetir").addEventListener("click", function () {
    repetindo = true;
    el("painel-dica").hidden = false;
    el("painel").classList.add("repetindo");
  });
  el("painel-parar-repetir").addEventListener("click", function (evento) {
    evento.preventDefault();
    repetindo = false;
    el("painel-dica").hidden = true;
    el("painel").classList.remove("repetindo");
  });

  mostrarAlvo();
  atualizarBotoes();
})();
```

- [ ] **Step 5: Acrescentar o CSS do painel**

Ao final de `app/static/bddente.css`:

```css
/* --- painel de lancamento --- */
.painel {
  flex: 0 0 290px;
  border: 1px solid var(--borda);
  border-radius: 12px;
  padding: 16px;
  background: #fff;
}
.painel.repetindo { border-color: var(--roxo); box-shadow: 0 0 0 3px var(--roxo-cl); }
.painel-alvo {
  background: var(--roxo-cl);
  color: var(--roxo-esc);
  border-radius: var(--raio);
  padding: 9px 12px;
  font-size: 13px;
  margin-bottom: 14px;
}
.rotulo {
  display: block;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #94A3B8;
  margin: 12px 0 5px;
}
.painel select,
.painel input[type="text"],
.painel input[type="date"] {
  width: 100%;
  border: 1px solid var(--borda);
  border-radius: var(--raio);
  padding: 8px 10px;
  font-size: 13px;
  background: #fff;
}
.painel select:focus,
.painel input:focus {
  outline: 0;
  border-color: var(--roxo);
  box-shadow: 0 0 0 3px var(--roxo-cl);
}
.escopos { display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
.regioes {
  border: 1px solid var(--borda);
  border-radius: var(--raio);
  padding: 9px 11px;
  margin: 10px 0 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
  font-size: 12.5px;
}
.regioes legend {
  grid-column: 1 / -1;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  color: #94A3B8;
  padding: 0;
}
.regioes .legenda-raiz { margin-top: 6px; }
.linha-dupla { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.painel button { width: 100%; margin-top: 14px; }
button.secundario {
  background: #fff;
  color: var(--roxo-esc);
  border: 1px solid var(--roxo-brd);
  border-radius: var(--raio);
  padding: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
button.secundario:hover:not(:disabled) { background: var(--roxo-cl); }
button.secundario:disabled { color: #CBD5E1; border-color: var(--borda); cursor: not-allowed; }
.painel-erro {
  color: #B91C1C;
  background: #FEE2E2;
  border-radius: var(--raio);
  padding: 8px 10px;
  font-size: 12.5px;
  margin: 12px 0 0;
}
.painel-dica {
  font-size: 12px;
  color: var(--roxo-esc);
  background: var(--roxo-cl);
  border-radius: var(--raio);
  padding: 8px 10px;
  margin: 10px 0 0;
}
```

- [ ] **Step 6: Rodar e ver passar**

Run: `pytest tests/clinico -v`
Expected: PASS

- [ ] **Step 7: Testar o fluxo à mão**

Os testes cobrem o contrato, não a experiência. Suba (`uvicorn app.main:app --reload`),
abra um paciente e faça o percurso inteiro:

1. Clicar na face de mastigação do dente 16 → o painel mostra "Dente 16 · oclusal"
2. Escolher Dentística → Restauração Classe II → escopo e regiões se pré-marcam
3. Lançar → o dente 16 fica vermelho **sem a página recarregar**
4. Clicar em "Repetir em outro dente" → clicar em 26, 36, 46 → os três ficam vermelhos
5. Clicar em "parar" → voltar ao modo normal
6. Escolher escopo "Boca toda" → o bloco de regiões some; lançar funciona sem dente

- [ ] **Step 8: Commitar**

```bash
git add app/templates/_painel_lancamento.html app/static/painel.js app/static/bddente.css tests/clinico/test_painel.py
git commit -m "feat: painel de lancamento com pre-marcacao e repetir em outro dente"
```

---

### Task 16: Tela de tratamentos

Catálogo agrupado pelas 12 categorias, com criação e edição de tratamento, escopo sugerido e preço por convênio.

**Files:**
- Modify: `app/catalogo/service.py`, `app/main.py`
- Create: `app/catalogo/rotas.py`, `app/templates/tratamentos.html`
- Test: `tests/catalogo/__init__.py`, `tests/catalogo/test_tratamentos.py`

**Interfaces:**
- Consumes: `app.catalogo.models.*`, `app.auth.auditoria.registrar`.
- Produces:
  - `app.catalogo.service.salvar_procedimento(sessao, *, clinica_id, usuario_id, procedimento_id=None, codigo, nome, categoria_id, escopo_sugerido, regioes_sugeridas, duracao_min=None, ativo=True) -> Procedimento`
  - `app.catalogo.service.definir_preco(sessao, *, clinica_id, usuario_id, procedimento_id, convenio_id, valor, vigente_desde=None) -> Preco`
  - `app.catalogo.service.preco_de(sessao, *, procedimento_id, convenio_id) -> Decimal | None` — o mais recente vigente.
  - `app.catalogo.service.CodigoRepetido` — exceção.
  - Rotas `GET /tratamentos`, `POST /tratamentos`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/catalogo/test_tratamentos.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.catalogo.models import Categoria, Convenio, Procedimento
from app.catalogo.service import (
    CodigoRepetido, arvore, definir_preco, preco_de, salvar_procedimento,
)
from app.shared.tipos import Escopo, Regiao


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    convenio = Convenio(clinica_id=clinica.id, codigo="001", nome="PARTICULAR")
    sessao.add_all([categoria, convenio])
    sessao.flush()
    return clinica, usuario, categoria, convenio


def test_cria_tratamento_novo(sessao, base):
    clinica, usuario, categoria, _ = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    assert p.id is not None
    assert sessao.get(Procedimento, p.id).nome == "Clareamento"


def test_edita_tratamento_existente_sem_criar_outro(sessao, base):
    clinica, usuario, categoria, _ = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        codigo="900", nome="Clareamento a laser", categoria_id=categoria.id,
        escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[Regiao.VESTIBULAR],
    )
    sessao.flush()
    assert sessao.query(Procedimento).count() == 1
    guardado = sessao.get(Procedimento, p.id)
    assert guardado.nome == "Clareamento a laser"
    assert guardado.regioes_sugeridas == [Regiao.VESTIBULAR]


def test_codigo_repetido_na_mesma_clinica_e_recusado(sessao, base):
    clinica, usuario, categoria, _ = base
    for _ in range(1):
        salvar_procedimento(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
            nome="A", categoria_id=categoria.id,
            escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
        )
        sessao.flush()
    with pytest.raises(CodigoRepetido):
        salvar_procedimento(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
            nome="B", categoria_id=categoria.id,
            escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
        )


def test_desativar_tira_do_painel_mas_nao_apaga(sessao, base):
    """Prontuario antigo continua apontando para o tratamento: nunca se apaga."""
    clinica, usuario, categoria, _ = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Antigo", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[], ativo=False,
    )
    sessao.flush()
    assert sessao.get(Procedimento, p.id) is not None
    nomes = [
        proc["nome"]
        for cat in arvore(sessao, clinica_id=clinica.id)
        for proc in cat["procedimentos"]
    ]
    assert "Antigo" not in nomes


def test_preco_por_convenio(sessao, base):
    clinica, usuario, categoria, convenio = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        convenio_id=convenio.id, valor=Decimal("450.00"),
    )
    sessao.flush()
    assert preco_de(sessao, procedimento_id=p.id, convenio_id=convenio.id) == Decimal("450.00")


def test_preco_novo_nao_apaga_o_antigo_e_vence(sessao, base):
    """O historico de precos importa: um lancamento de 2015 foi cobrado ao preco
    de 2015."""
    clinica, usuario, categoria, convenio = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="X", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        convenio_id=convenio.id, valor=Decimal("100.00"), vigente_desde=date(2015, 1, 1),
    )
    definir_preco(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, procedimento_id=p.id,
        convenio_id=convenio.id, valor=Decimal("450.00"), vigente_desde=date(2026, 1, 1),
    )
    sessao.flush()
    from app.catalogo.models import Preco

    assert sessao.query(Preco).count() == 2
    assert preco_de(sessao, procedimento_id=p.id, convenio_id=convenio.id) == Decimal("450.00")


def test_preco_inexistente_devolve_none(sessao, base):
    clinica, usuario, categoria, convenio = base
    p = salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="X", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    assert preco_de(sessao, procedimento_id=p.id, convenio_id=convenio.id) is None


def test_salvar_deixa_rastro_na_auditoria(sessao, base):
    clinica, usuario, categoria, _ = base
    salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="X", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "procedimento")
    ).all()
    assert len(linhas) == 1 and linhas[0].acao == "CRIAR"


def test_a_tela_agrupa_por_categoria(sessao, base):
    from fastapi.testclient import TestClient

    from app.main import criar_app
    from app.shared.db import obter_sessao

    clinica, usuario, categoria, _ = base
    salvar_procedimento(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, codigo="900",
        nome="Clareamento", categoria_id=categoria.id,
        escopo_sugerido=Escopo.DENTE, regioes_sugeridas=[],
    )
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        html = c.get("/tratamentos").text
    assert "Dentistica" in html
    assert "Clareamento" in html
    assert 'href="/tratamentos" class="ativo"' in html
```

Crie `tests/catalogo/__init__.py` vazio.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/catalogo -v`
Expected: FAIL com `ImportError: cannot import name 'salvar_procedimento'`

- [ ] **Step 3: Acrescentar em `app/catalogo/service.py`**

```python
from datetime import date
from decimal import Decimal

from app.auth.auditoria import registrar
from app.catalogo.models import Preco
from app.shared.tipos import Escopo, Regiao


class CodigoRepetido(ValueError):
    """Ja existe outro tratamento com este codigo nesta clinica."""


def salvar_procedimento(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    procedimento_id: int | None = None,
    codigo: str,
    nome: str,
    categoria_id: int,
    escopo_sugerido: Escopo,
    regioes_sugeridas: "list[Regiao]",
    duracao_min: int | None = None,
    ativo: bool = True,
) -> Procedimento:
    codigo = codigo.strip()
    conflito = sessao.scalars(
        select(Procedimento).where(
            Procedimento.clinica_id == clinica_id, Procedimento.codigo == codigo
        )
    ).first()
    if conflito is not None and conflito.id != procedimento_id:
        raise CodigoRepetido(f"o codigo {codigo} ja e usado por '{conflito.nome}'")

    if procedimento_id is None:
        procedimento = Procedimento(clinica_id=clinica_id, codigo=codigo)
        sessao.add(procedimento)
        acao, antes = "CRIAR", None
    else:
        procedimento = sessao.scalars(
            select(Procedimento).where(
                Procedimento.id == procedimento_id,
                Procedimento.clinica_id == clinica_id,
            )
        ).one()
        acao = "ATUALIZAR"
        antes = {
            "codigo": procedimento.codigo,
            "nome": procedimento.nome,
            "escopo_sugerido": procedimento.escopo_sugerido.value,
        }

    procedimento.codigo = codigo
    procedimento.nome = nome.strip()
    procedimento.categoria_id = categoria_id
    procedimento.escopo_sugerido = escopo_sugerido
    procedimento.regioes_sugeridas = list(regioes_sugeridas)
    procedimento.duracao_min = duracao_min
    procedimento.ativo = ativo
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao=acao,
        entidade="procedimento",
        entidade_id=procedimento.id,
        antes=antes,
        depois={
            "codigo": codigo,
            "nome": procedimento.nome,
            "escopo_sugerido": escopo_sugerido.value,
            "ativo": ativo,
        },
    )
    return procedimento


def definir_preco(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    procedimento_id: int,
    convenio_id: int,
    valor: Decimal,
    vigente_desde: date | None = None,
) -> Preco:
    """Cria uma nova vigencia. O preco antigo NUNCA e sobrescrito: um lancamento
    de 2015 foi cobrado ao preco de 2015, e o extrato tem de continuar explicavel."""
    preco = Preco(
        procedimento_id=procedimento_id,
        convenio_id=convenio_id,
        valor=Decimal(valor).quantize(Decimal("0.01")),
        vigente_desde=vigente_desde or date.today(),
    )
    sessao.add(preco)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="CRIAR",
        entidade="preco",
        entidade_id=preco.id,
        depois={
            "procedimento_id": procedimento_id,
            "convenio_id": convenio_id,
            "valor": str(preco.valor),
        },
    )
    return preco


def preco_de(
    sessao: Session, *, procedimento_id: int, convenio_id: int, em: date | None = None
) -> Decimal | None:
    """O preco vigente na data pedida (hoje, por padrao)."""
    quando = em or date.today()
    preco = sessao.scalars(
        select(Preco)
        .where(
            Preco.procedimento_id == procedimento_id,
            Preco.convenio_id == convenio_id,
            Preco.vigente_desde <= quando,
        )
        .order_by(Preco.vigente_desde.desc(), Preco.id.desc())
    ).first()
    return preco.valor if preco else None
```

- [ ] **Step 4: Escrever `app/catalogo/rotas.py` e o template**

`app/catalogo/rotas.py`:

```python
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.catalogo.models import Categoria, Convenio
from app.catalogo.service import CodigoRepetido, arvore, definir_preco, salvar_procedimento
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao
from app.templates import templates

router = APIRouter()


def _contexto(sessao: Session, clinica_id: int, erro: str | None = None) -> dict:
    return {
        "aba": "tratamentos",
        "catalogo": arvore(sessao, clinica_id=clinica_id),
        "categorias": list(
            sessao.scalars(
                select(Categoria)
                .where(Categoria.clinica_id == clinica_id)
                .order_by(Categoria.ordem)
            )
        ),
        "convenios": list(
            sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
        ),
        "escopos": list(Escopo),
        "regioes": list(Regiao),
        "erro": erro,
    }


@router.get("/tratamentos", response_class=HTMLResponse)
def listar(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    return templates.TemplateResponse(
        request, "tratamentos.html", _contexto(sessao, usuario.clinica_id)
    )


@router.post("/tratamentos")
def salvar(
    request: Request,
    procedimento_id: str = Form(""),
    codigo: str = Form(...),
    nome: str = Form(...),
    categoria_id: int = Form(...),
    escopo_sugerido: Escopo = Form(...),
    # list[Regiao] direto em Form nao funciona de forma confiavel; convertemos a mao.
    regiao: list[str] = Form([]),
    convenio_id: str = Form(""),
    valor: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        procedimento = salvar_procedimento(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            procedimento_id=int(procedimento_id) if procedimento_id else None,
            codigo=codigo,
            nome=nome,
            categoria_id=categoria_id,
            escopo_sugerido=escopo_sugerido,
            regioes_sugeridas=[Regiao(valor) for valor in regiao],
        )
        if convenio_id and valor:
            definir_preco(
                sessao,
                clinica_id=usuario.clinica_id,
                usuario_id=usuario.id,
                procedimento_id=procedimento.id,
                convenio_id=int(convenio_id),
                valor=Decimal(valor.replace(".", "").replace(",", ".")),
            )
    except (CodigoRepetido, InvalidOperation, ValueError) as erro:
        sessao.rollback()
        return templates.TemplateResponse(
            request,
            "tratamentos.html",
            _contexto(sessao, usuario.clinica_id, erro=str(erro)),
            status_code=200,
        )

    sessao.commit()
    return RedirectResponse("/tratamentos", status_code=303)
```

`app/templates/tratamentos.html`:

```html
{% extends "base.html" %}
{% block titulo %}Tratamentos — BDDente{% endblock %}
{% block conteudo %}
<h1>Tratamentos</h1>
<p class="legenda-topo">
  {{ catalogo | length }} categorias em uso ·
  {{ catalogo | map(attribute='procedimentos') | map('length') | sum }} tratamentos ativos
</p>

<div class="odonto-area">
  <div style="flex:1 1 520px;min-width:0">
    {% for categoria in catalogo %}
      <h2 class="titulo-historico">{{ categoria.nome }}</h2>
      <table>
        <thead><tr><th>Código</th><th>Tratamento</th><th>Onde costuma ser</th></tr></thead>
        <tbody>
        {% for procedimento in categoria.procedimentos %}
          <tr>
            <td class="codigo">{{ procedimento.codigo }}</td>
            <td class="nome">{{ procedimento.nome }}</td>
            <td>
              {% if procedimento.escopo_sugerido == 'BOCA' %}Boca toda
              {% elif procedimento.escopo_sugerido == 'DENTE' %}Dente inteiro
              {% else %}{{ procedimento.regioes_sugeridas | join(', ') | lower or 'regiões' }}
              {% endif %}
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p style="color:var(--texto-fraco)">Nenhum tratamento cadastrado ainda.</p>
    {% endfor %}
  </div>

  <aside class="painel">
    <div class="painel-alvo">Novo tratamento</div>
    <form method="post" action="/tratamentos">
      <label class="rotulo" for="codigo">Código</label>
      <input type="text" id="codigo" name="codigo" required>

      <label class="rotulo" for="nome">Nome</label>
      <input type="text" id="nome" name="nome" required>

      <label class="rotulo" for="categoria_id">Categoria</label>
      <select id="categoria_id" name="categoria_id" required>
        {% for categoria in categorias %}
          <option value="{{ categoria.id }}">{{ categoria.nome }}</option>
        {% endfor %}
      </select>

      <label class="rotulo">Onde costuma ser</label>
      <div class="escopos">
        {% for escopo in escopos %}
          <label>
            <input type="radio" name="escopo_sugerido" value="{{ escopo.value }}"
                   {{ 'checked' if escopo.value == 'DENTE' }}>
            {{ {'BOCA':'Boca toda','DENTE':'Dente inteiro','REGIOES':'Regiões'}[escopo.value] }}
          </label>
        {% endfor %}
      </div>

      <fieldset class="regioes">
        <legend>Regiões sugeridas</legend>
        {% for r in regioes %}
          <label><input type="checkbox" name="regiao" value="{{ r.value }}">
            {{ r.value | lower | replace('_', ' ') }}</label>
        {% endfor %}
      </fieldset>

      <div class="linha-dupla">
        <div>
          <label class="rotulo" for="convenio_id">Convênio</label>
          <select id="convenio_id" name="convenio_id">
            <option value="">—</option>
            {% for convenio in convenios %}
              <option value="{{ convenio.id }}">{{ convenio.nome }}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label class="rotulo" for="valor">Valor (R$)</label>
          <input type="text" id="valor" name="valor" inputmode="decimal" placeholder="0,00">
        </div>
      </div>

      {% if erro %}<p class="painel-erro">{{ erro }}</p>{% endif %}
      <button type="submit" class="primario">Salvar</button>
    </form>
  </aside>
</div>
{% endblock %}
```

Em `app/main.py`, adicione `from app.catalogo import rotas as catalogo_rotas` e
`app.include_router(catalogo_rotas.router)`.

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/catalogo -v`
Expected: PASS (9 testes)

- [ ] **Step 6: Commitar**

```bash
git add app/catalogo/service.py app/catalogo/rotas.py app/templates/tratamentos.html app/main.py tests/catalogo
git commit -m "feat: tela de tratamentos com categorias, escopo sugerido e preco por convenio"
```

---

### Task 17: Anamnese

Questionário de saúde por paciente, com as 37 perguntas do catálogo migrado. Respostas Sim/Não e texto livre.

**Files:**
- Modify: `app/clinico/service.py`, `app/clinico/rotas.py`
- Create: `app/templates/anamnese.html`
- Test: `tests/clinico/test_anamnese.py`

**Interfaces:**
- Consumes: `app.clinico.models.PerguntaAnamnese`, `app.clinico.models.RespostaAnamnese`, `app.auth.auditoria.registrar`.
- Produces:
  - `app.clinico.service.anamnese(sessao, *, clinica_id, paciente_id) -> list[dict]` — `pergunta_id`, `codigo`, `texto`, `tipo_resposta`, `resposta`, `respondido_em`.
  - `app.clinico.service.responder(sessao, *, clinica_id, usuario_id, paciente_id, respostas: dict[int, str]) -> int` — devolve quantas gravou.
  - Rotas `GET /anamnese/{paciente_id}`, `POST /anamnese/{paciente_id}`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/clinico/test_anamnese.py`:

```python
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Auditoria, Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.clinico.models import PerguntaAnamnese, RespostaAnamnese
from app.clinico.service import anamnese, responder
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    paciente = Paciente(clinica_id=clinica.id, nome="Amanda")
    sessao.add(paciente)
    perguntas = [
        PerguntaAnamnese(
            clinica_id=clinica.id, codigo=f"{i:02d}",
            texto=f"Pergunta {i}", tipo_resposta=1, ordem=i,
        )
        for i in range(1, 4)
    ]
    sessao.add_all(perguntas)
    sessao.flush()
    return clinica, usuario, paciente, perguntas


def test_paciente_novo_ve_o_questionario_em_branco(sessao, base):
    clinica, _, paciente, _ = base
    itens = anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    assert len(itens) == 3
    assert all(item["resposta"] is None for item in itens)


def test_o_questionario_vem_na_ordem_do_catalogo(sessao, base):
    clinica, _, paciente, _ = base
    itens = anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    assert [item["codigo"] for item in itens] == ["01", "02", "03"]


def test_pergunta_inativa_nao_aparece(sessao, base):
    clinica, _, paciente, perguntas = base
    perguntas[1].ativa = False
    sessao.flush()
    codigos = [
        item["codigo"]
        for item in anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    ]
    assert codigos == ["01", "03"]


def test_responder_grava_e_aparece_na_proxima_leitura(sessao, base):
    clinica, usuario, paciente, perguntas = base
    gravadas = responder(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        respostas={perguntas[0].id: "Sim", perguntas[2].id: "toma losartana"},
    )
    sessao.flush()
    assert gravadas == 2
    por_codigo = {
        item["codigo"]: item
        for item in anamnese(sessao, clinica_id=clinica.id, paciente_id=paciente.id)
    }
    assert por_codigo["01"]["resposta"] == "Sim"
    assert por_codigo["03"]["resposta"] == "toma losartana"
    assert por_codigo["02"]["resposta"] is None
    assert por_codigo["01"]["respondido_em"] == date.today()


def test_responder_de_novo_atualiza_em_vez_de_duplicar(sessao, base):
    clinica, usuario, paciente, perguntas = base
    for resposta in ("Sim", "Não"):
        responder(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, respostas={perguntas[0].id: resposta},
        )
        sessao.flush()
    assert sessao.query(RespostaAnamnese).count() == 1
    assert sessao.scalars(select(RespostaAnamnese)).one().resposta == "Não"


def test_resposta_vazia_nao_cria_linha(sessao, base):
    clinica, usuario, paciente, perguntas = base
    assert (
        responder(
            sessao, clinica_id=clinica.id, usuario_id=usuario.id,
            paciente_id=paciente.id, respostas={perguntas[0].id: "   "},
        )
        == 0
    )
    sessao.flush()
    assert sessao.query(RespostaAnamnese).count() == 0


def test_responder_deixa_rastro_na_auditoria(sessao, base):
    clinica, usuario, paciente, perguntas = base
    responder(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        respostas={perguntas[0].id: "Sim"},
    )
    sessao.flush()
    linhas = sessao.scalars(
        select(Auditoria).where(Auditoria.entidade == "resposta_anamnese")
    ).all()
    assert len(linhas) == 1


def test_a_tela_mostra_as_perguntas_e_grava_o_formulario(sessao, base):
    clinica, usuario, paciente, perguntas = base
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        html = c.get(f"/anamnese/{paciente.id}").text
        assert "Pergunta 1" in html
        assert "Amanda" in html

        resposta = c.post(
            f"/anamnese/{paciente.id}", data={f"pergunta_{perguntas[0].id}": "Sim"}
        )
        assert resposta.status_code == 303
    sessao.flush()
    assert sessao.query(RespostaAnamnese).count() == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/clinico/test_anamnese.py -v`
Expected: FAIL com `ImportError: cannot import name 'anamnese'`

- [ ] **Step 3: Acrescentar em `app/clinico/service.py`**

```python
from app.clinico.models import PerguntaAnamnese, RespostaAnamnese


def anamnese(sessao: Session, *, clinica_id: int, paciente_id: int) -> list[dict]:
    perguntas = list(
        sessao.scalars(
            select(PerguntaAnamnese)
            .where(
                PerguntaAnamnese.clinica_id == clinica_id,
                PerguntaAnamnese.ativa.is_(True),
            )
            .order_by(PerguntaAnamnese.ordem, PerguntaAnamnese.codigo)
        )
    )
    respostas = {
        r.pergunta_id: r
        for r in sessao.scalars(
            select(RespostaAnamnese).where(RespostaAnamnese.paciente_id == paciente_id)
        )
    }
    return [
        {
            "pergunta_id": p.id,
            "codigo": p.codigo,
            "texto": p.texto,
            "tipo_resposta": p.tipo_resposta,
            "resposta": respostas[p.id].resposta if p.id in respostas else None,
            "respondido_em": respostas[p.id].respondido_em if p.id in respostas else None,
        }
        for p in perguntas
    ]


def responder(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    respostas: dict[int, str],
) -> int:
    """Grava as respostas preenchidas. Devolve quantas gravou.

    Resposta em branco nao cria linha: nao respondido e diferente de respondido
    com vazio, e a ficha de saude precisa distinguir os dois.
    """
    guardadas = {
        r.pergunta_id: r
        for r in sessao.scalars(
            select(RespostaAnamnese).where(RespostaAnamnese.paciente_id == paciente_id)
        )
    }
    gravadas = 0
    for pergunta_id, texto in respostas.items():
        limpo = (texto or "").strip()
        if not limpo:
            continue
        existente = guardadas.get(pergunta_id)
        antes = {"resposta": existente.resposta} if existente else None
        if existente is None:
            existente = RespostaAnamnese(
                paciente_id=paciente_id, pergunta_id=pergunta_id, resposta=limpo
            )
            sessao.add(existente)
        else:
            existente.resposta = limpo
        existente.respondido_em = date.today()
        sessao.flush()
        registrar(
            sessao,
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            acao="CRIAR" if antes is None else "ATUALIZAR",
            entidade="resposta_anamnese",
            entidade_id=existente.id,
            antes=antes,
            depois={"pergunta_id": pergunta_id, "resposta": limpo},
        )
        gravadas += 1
    sessao.flush()
    return gravadas
```

- [ ] **Step 4: Acrescentar as rotas e o template**

Em `app/clinico/rotas.py`:

```python
from fastapi import Form
from app.clinico.service import anamnese, responder
from app.pacientes.service import obter as obter_paciente


@router.get("/anamnese/{paciente_id}", response_class=HTMLResponse)
def tela_anamnese(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    paciente = obter_paciente(
        sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
    )
    if paciente is None:
        raise HTTPException(status_code=404, detail="paciente nao encontrado")
    return templates.TemplateResponse(
        request,
        "anamnese.html",
        {
            "aba": "odontograma",
            "paciente": paciente,
            "itens": anamnese(
                sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id
            ),
        },
    )


@router.post("/anamnese/{paciente_id}")
async def gravar_anamnese(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    formulario = await request.form()
    respostas = {
        int(chave.removeprefix("pergunta_")): str(valor)
        for chave, valor in formulario.items()
        if chave.startswith("pergunta_")
    }
    responder(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        paciente_id=paciente_id,
        respostas=respostas,
    )
    sessao.commit()
    return RedirectResponse(f"/anamnese/{paciente_id}", status_code=303)
```

`app/templates/anamnese.html`:

```html
{% extends "base.html" %}
{% block titulo %}Anamnese — {{ paciente.nome }}{% endblock %}
{% block conteudo %}
<h1>Anamnese — {{ paciente.nome }}</h1>
<p class="legenda-topo">
  <a href="/odontograma/{{ paciente.id }}">voltar para o odontograma</a>
</p>

<form method="post" action="/anamnese/{{ paciente.id }}" style="max-width:720px">
  <table>
    <thead><tr><th style="width:60%">Pergunta</th><th>Resposta</th></tr></thead>
    <tbody>
    {% for item in itens %}
      <tr>
        <td>{{ item.texto }}</td>
        <td>
          {% if item.tipo_resposta == 1 %}
            <label><input type="radio" name="pergunta_{{ item.pergunta_id }}" value="Sim"
                   {{ 'checked' if item.resposta == 'Sim' }}> Sim</label>
            <label style="margin-left:12px">
              <input type="radio" name="pergunta_{{ item.pergunta_id }}" value="Não"
                     {{ 'checked' if item.resposta in ('Não', 'N') }}> Não</label>
          {% else %}
            <input type="text" name="pergunta_{{ item.pergunta_id }}"
                   value="{{ item.resposta or '' }}" style="width:100%">
          {% endif %}
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  <button type="submit" class="primario" style="margin-top:16px">Salvar respostas</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/clinico/test_anamnese.py -v`
Expected: PASS (8 testes)

- [ ] **Step 6: Commitar**

```bash
git add app/clinico/service.py app/clinico/rotas.py app/templates/anamnese.html tests/clinico/test_anamnese.py
git commit -m "feat: anamnese por paciente"
```

---

### Task 18: Prontuário em PDF

Atende o **direito de acesso** da LGPD (a paciente pode pedir os dados dela) e serve para encaminhamento a outro profissional.

**Files:**
- Create: `app/clinico/prontuario.py`
- Modify: `app/clinico/rotas.py`
- Test: `tests/clinico/test_prontuario.py`

**Interfaces:**
- Consumes: `app.clinico.service.historico`, `app.clinico.service.anamnese`, `app.pacientes.service.obter`.
- Produces:
  - `app.clinico.prontuario.gerar(sessao, *, clinica_id, paciente_id, clinica_nome) -> bytes`
  - Rota `GET /prontuario/{paciente_id}.pdf`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/clinico/test_prontuario.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.sessao import NOME_COOKIE, assinar
from app.auth.service import criar_usuario
from app.catalogo.models import Categoria, Procedimento
from app.clinico.prontuario import gerar
from app.clinico.service import lancar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    paciente = Paciente(
        clinica_id=clinica.id, codigo_legado="6612/PT",
        nome="Amanda Ribeiro Nogueira", nascimento=date(1990, 3, 2),
    )
    sessao.add_all([categoria, paciente])
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    sessao.add(proc)
    sessao.flush()
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=proc.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL, Regiao.OCLUSAL], status=StatusLancamento.REALIZADO,
        data=date(2024, 6, 25), valor=Decimal("180.00"),
    )
    sessao.flush()
    return clinica, usuario, paciente


def test_gera_um_pdf_de_verdade(sessao, base):
    clinica, _, paciente = base
    conteudo = gerar(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id,
        clinica_nome=clinica.nome,
    )
    assert conteudo.startswith(b"%PDF")
    assert len(conteudo) > 800


def test_paciente_sem_historico_ainda_gera_pdf(sessao, base):
    """Ficha nova tambem tem de poder ser impressa."""
    clinica, _, _ = base
    novo = Paciente(clinica_id=clinica.id, nome="Sem Historico")
    sessao.add(novo)
    sessao.flush()
    assert gerar(
        sessao, clinica_id=clinica.id, paciente_id=novo.id, clinica_nome=clinica.nome
    ).startswith(b"%PDF")


def test_nome_com_acento_nao_quebra_a_geracao(sessao, base):
    """Kátia, Sant'Anna, José — o banco dela e cheio deles."""
    clinica, _, _ = base
    p = Paciente(clinica_id=clinica.id, nome="José Carlos Sant'Anna Küçük")
    sessao.add(p)
    sessao.flush()
    assert gerar(
        sessao, clinica_id=clinica.id, paciente_id=p.id, clinica_nome=clinica.nome
    ).startswith(b"%PDF")


def test_paciente_de_outra_clinica_e_recusado(sessao, base):
    clinica, _, _ = base
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="Alheio")
    sessao.add(alheio)
    sessao.flush()
    with pytest.raises(LookupError):
        gerar(
            sessao, clinica_id=clinica.id, paciente_id=alheio.id,
            clinica_nome=clinica.nome,
        )


def test_a_rota_devolve_o_pdf_como_anexo(sessao, base):
    clinica, usuario, paciente = base
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario.id))
        resposta = c.get(f"/prontuario/{paciente.id}.pdf")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.content.startswith(b"%PDF")


def test_a_rota_exige_sessao(sessao, base):
    _, _, paciente = base
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get(f"/prontuario/{paciente.id}.pdf").status_code == 303
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/clinico/test_prontuario.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.clinico.prontuario'`

- [ ] **Step 3: Implementar `app/clinico/prontuario.py`**

```python
"""Prontuario do paciente em PDF.

Atende o direito de acesso da LGPD e serve para encaminhamento. Usa fpdf2, que e
Python puro — sem dependencia de sistema para instalar no Windows nem no container.
"""

from datetime import date

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.clinico.service import anamnese, historico
from app.pacientes.service import obter as obter_paciente

ROXO = (91, 33, 182)
CINZA = (100, 116, 139)


class _Folha(FPDF):
    def __init__(self, clinica_nome: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.clinica_nome = clinica_nome
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        self.set_font("helvetica", "B", 15)
        self.set_text_color(*ROXO)
        self.cell(0, 8, "BDDente", new_x="LMARGIN", new_y="NEXT")
        self.set_font("helvetica", "", 9)
        self.set_text_color(*CINZA)
        self.cell(0, 5, self.clinica_nome, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_draw_color(196, 181, 253)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(
            0, 5,
            f"Emitido em {date.today().strftime('%d/%m/%Y')} · pagina {self.page_no()}",
            align="C",
        )

    def titulo(self, texto: str) -> None:
        self.ln(3)
        self.set_font("helvetica", "B", 11)
        self.set_text_color(15, 23, 42)
        self.cell(0, 7, texto, new_x="LMARGIN", new_y="NEXT")

    def linha(self, rotulo: str, valor: str) -> None:
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*CINZA)
        self.cell(38, 6, rotulo)
        self.set_text_color(15, 23, 42)
        self.multi_cell(0, 6, valor or "—", new_x="LMARGIN", new_y="NEXT")


def _texto(valor: object) -> str:
    """fpdf2 com as fontes embutidas so escreve latin-1. Trocamos o que nao couber
    em vez de deixar a geracao estourar num nome com acento incomum."""
    bruto = "" if valor is None else str(valor)
    return bruto.encode("latin-1", "replace").decode("latin-1")


def gerar(
    sessao: Session, *, clinica_id: int, paciente_id: int, clinica_nome: str
) -> bytes:
    paciente = obter_paciente(
        sessao, clinica_id=clinica_id, paciente_id=paciente_id
    )
    if paciente is None:
        raise LookupError("paciente nao encontrado nesta clinica")

    folha = _Folha(_texto(clinica_nome))
    folha.add_page()

    folha.set_font("helvetica", "B", 14)
    folha.set_text_color(15, 23, 42)
    folha.cell(0, 9, _texto(paciente.nome), new_x="LMARGIN", new_y="NEXT")

    folha.titulo("Dados do paciente")
    folha.linha("Codigo", _texto(paciente.codigo_legado))
    folha.linha(
        "Nascimento",
        paciente.nascimento.strftime("%d/%m/%Y") if paciente.nascimento else "—",
    )
    folha.linha("CPF", _texto(paciente.cpf))
    folha.linha(
        "Telefones",
        ", ".join(_texto(t.numero) for t in paciente.telefones) or "—",
    )
    if paciente.revisar_motivo:
        folha.linha("A conferir", _texto(", ".join(paciente.revisar_motivo)))

    folha.titulo("Historico de tratamentos")
    itens = historico(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if not itens:
        folha.set_font("helvetica", "", 9.5)
        folha.set_text_color(*CINZA)
        folha.cell(0, 6, "Nenhum lancamento registrado.", new_x="LMARGIN", new_y="NEXT")
    else:
        folha.set_font("helvetica", "B", 8.5)
        folha.set_text_color(*CINZA)
        for largura, cabecalho in (
            (24, "Data"), (18, "Dente"), (86, "Tratamento"),
            (26, "Situacao"), (24, "Valor"),
        ):
            folha.cell(largura, 6, cabecalho)
        folha.ln(6)
        folha.set_font("helvetica", "", 9)
        folha.set_text_color(15, 23, 42)
        for item in itens:
            folha.cell(24, 5.5, item["data"].strftime("%d/%m/%Y") if item["data"] else "—")
            folha.cell(18, 5.5, str(item["dente"]) if item["dente"] else "boca")
            folha.cell(86, 5.5, _texto(item["procedimento"])[:52])
            folha.cell(
                26, 5.5,
                "Realizado" if item["status"] == "REALIZADO" else "Planejado",
            )
            folha.cell(24, 5.5, f"R$ {item['valor']}")
            folha.ln(5.5)

    respostas = [
        item
        for item in anamnese(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
        if item["resposta"]
    ]
    if respostas:
        folha.titulo("Anamnese")
        folha.set_font("helvetica", "", 9)
        for item in respostas:
            folha.set_text_color(*CINZA)
            folha.multi_cell(0, 5, _texto(item["texto"]), new_x="LMARGIN", new_y="NEXT")
            folha.set_text_color(15, 23, 42)
            folha.multi_cell(
                0, 5, "   " + _texto(item["resposta"]), new_x="LMARGIN", new_y="NEXT"
            )

    return bytes(folha.output())
```

- [ ] **Step 4: Acrescentar a rota**

Em `app/clinico/rotas.py`:

```python
from fastapi.responses import Response

from app.auth.models import Clinica  # noqa — leitura do nome da clinica
from app.clinico.prontuario import gerar as gerar_prontuario


@router.get("/prontuario/{paciente_id}.pdf")
def prontuario_pdf(
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    clinica = sessao.get(Clinica, usuario.clinica_id)
    try:
        conteudo = gerar_prontuario(
            sessao,
            clinica_id=usuario.clinica_id,
            paciente_id=paciente_id,
            clinica_nome=clinica.nome if clinica else "BDDente",
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="prontuario-{paciente_id}.pdf"'
        },
    )
```

> **Exceção consciente à fronteira de módulo.** `clinico/rotas.py` importa
> `auth.models.Clinica` só para ler o nome no cabeçalho do PDF. Se `auth` ganhar uma
> `service.clinica(id)`, troque por ela. Está anotado aqui para não virar precedente.

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/clinico/test_prontuario.py -v`
Expected: PASS (6 testes)

- [ ] **Step 6: Commitar**

```bash
git add app/clinico/prontuario.py app/clinico/rotas.py tests/clinico/test_prontuario.py
git commit -m "feat: exportacao do prontuario em PDF"
```

---

### Task 19: Deploy, backup e teste de restauração

**Backup nunca restaurado não conta como backup.** Esta task só está pronta quando a restauração tiver sido exercitada de verdade.

**Files:**
- Create: `fly.toml`, `scripts/backup.py`, `scripts/restaurar.py`, `docs/OPERACAO.md`
- Modify: `app/main.py` (redirect da raiz), `.github/workflows/ci.yml`
- Test: `tests/test_operacao.py`

**Interfaces:**
- Produces:
  - `scripts/backup.py` — `python -m scripts.backup [destino]`; gera `bddente-AAAA-MM-DD.dump`.
  - `scripts/restaurar.py` — `python -m scripts.restaurar <arquivo> <url-destino>`; restaura e **confere** as contagens.
  - Rota `GET /` → redireciona para `/pacientes`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_operacao.py`:

```python
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
    linha = next(l for l in texto.splitlines() if l.startswith("SECRET_KEY="))
    assert len(linha.split("=", 1)[1]) < 80  # e uma instrucao, nao uma chave
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_operacao.py -v`
Expected: FAIL — a rota `/` não existe e os arquivos não foram criados

- [ ] **Step 3: Acrescentar a rota raiz**

Em `criar_app()`, dentro de `app/main.py`:

```python
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/pacientes", status_code=303)
```

- [ ] **Step 4: Escrever `fly.toml`**

```toml
app = "bddente"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 1

  [[http_service.checks]]
    grace_period = "10s"
    interval = "30s"
    method = "GET"
    path = "/saude"
    timeout = "5s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

- [ ] **Step 5: Escrever os scripts de backup e restauração**

`scripts/backup.py`:

```python
"""Backup do banco. Roda diariamente.

    python -m scripts.backup [pasta-destino]

Guarda um dump comprimido por dia. Nao apaga nada sozinho: prontuario tem guarda
minima de 10 anos e a decisao de descartar backup antigo e da clinica, nao do script.
"""

import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from app.config import config


def main() -> int:
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "backups")
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"bddente-{date.today().isoformat()}.dump"

    url = urlparse(config.database_url.replace("postgresql+psycopg://", "postgresql://"))
    comando = [
        "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
        f"--file={arquivo}",
        f"--host={url.hostname}", f"--port={url.port or 5432}",
        f"--username={url.username}", (url.path or "/bddente").lstrip("/"),
    ]
    resultado = subprocess.run(
        comando, env={"PGPASSWORD": url.password or "", "PATH": "/usr/bin:/bin"}
    )
    if resultado.returncode != 0:
        print("backup FALHOU", file=sys.stderr)
        return resultado.returncode

    tamanho = arquivo.stat().st_size
    if tamanho < 100_000:
        # Um dump de 5.561 pacientes e 44.812 lancamentos nunca e pequeno assim.
        print(f"backup suspeito: apenas {tamanho} bytes", file=sys.stderr)
        return 2
    print(f"backup gravado: {arquivo} ({tamanho // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/restaurar.py`:

```python
"""Restaura um backup num banco de destino e CONFERE o resultado.

    python -m scripts.restaurar backups/bddente-2026-08-25.dump \\
        postgresql://usuario:senha@host:5432/bddente_restaurado

Backup nunca restaurado nao conta como backup. Este script existe para que o teste
de restauracao seja um comando, nao um projeto.
"""

import subprocess
import sys
from urllib.parse import urlparse

import psycopg

MINIMOS = {"paciente": 5_561, "lancamento": 44_812, "lancamento_regiao": 29_350}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 64

    arquivo, destino = sys.argv[1], sys.argv[2]
    url = urlparse(destino)
    resultado = subprocess.run(
        [
            "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
            f"--host={url.hostname}", f"--port={url.port or 5432}",
            f"--username={url.username}", f"--dbname={(url.path or '').lstrip('/')}",
            arquivo,
        ],
        env={"PGPASSWORD": url.password or "", "PATH": "/usr/bin:/bin"},
    )
    if resultado.returncode != 0:
        print("restauracao FALHOU", file=sys.stderr)
        return resultado.returncode

    with psycopg.connect(destino) as conexao:
        for tabela, esperado in MINIMOS.items():
            encontrado = conexao.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]
            marca = "ok" if encontrado >= esperado else "FALHOU"
            print(f"  {tabela}: {encontrado} (esperado >= {esperado}) {marca}")
            if encontrado < esperado:
                return 3

    print("restauracao conferida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Crie `scripts/__init__.py` vazio.

- [ ] **Step 6: Escrever `docs/OPERACAO.md`**

```markdown
# Operação do BDDente

## Deploy

    fly deploy

Segredos (uma vez):

    fly secrets set SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
    fly postgres attach <nome-do-banco>

Migrations e o primeiro usuário rodam à mão depois do deploy:

    fly ssh console -C "alembic upgrade head"
    fly ssh console --pty -C "python -m scripts.criar_usuario katia@exemplo.com 'Katia'"

## Requisitos que o provedor precisa cumprir

Dado de saúde é dado pessoal sensível pela LGPD — a categoria de maior proteção.
Confira, e anote a data da conferência:

- **HTTPS obrigatório** — garantido pelo `force_https` no `fly.toml`.
- **Criptografia em repouso no banco.** O Postgres gerenciado do Fly.io cifra os
  volumes; se um dia o banco mudar de provedor, isto tem de ser reconfirmado antes
  da migração, não depois.
- **Região do dado.** `primary_region = "gru"` (São Paulo) mantém o prontuário no
  Brasil.

## Backup

Diário, automático, com retenção do provedor mais uma cópia própria:

    python -m scripts.backup backups/

O script recusa dump menor que 100 KB — um banco com 5.561 pacientes e 44.812
lançamentos nunca é tão pequeno, então tamanho pequeno significa dump truncado.

O script **não apaga backup antigo**. Prontuário tem guarda mínima de 10 anos após o
último atendimento (e, se a paciente era menor, o prazo começa quando ela faz 18).
Descartar backup é decisão da clínica, não do script.

## Teste de restauração — TRIMESTRAL, obrigatório

Backup nunca restaurado não conta como backup. A cada três meses:

    createdb bddente_restaurado
    python -m scripts.restaurar backups/bddente-AAAA-MM-DD.dump \
        postgresql://usuario:senha@localhost:5432/bddente_restaurado

O script confere as contagens e falha alto se faltar registro. Anote a data do último
teste bem-sucedido aqui:

| Data do teste | Backup usado | Resultado |
|---|---|---|
| (preencher no primeiro teste) | | |

## Se der problema

- **Aplicação não sobe:** `fly logs`. O health check é `GET /saude`.
- **Migration travada:** `fly ssh console -C "alembic current"` mostra onde parou.
- **Dado de paciente parece errado:** consulte `revisar_motivo` na tabela `paciente`
  e `lancamento` — a migração marca o que é suspeito em vez de corrigir no chute.
- **Nunca rode `DELETE`.** Toda exclusão do sistema é lógica (`excluido_em`).
```

- [ ] **Step 7: Rodar e ver passar**

Run: `pytest -v`
Expected: PASS — a suíte inteira

- [ ] **Step 8: Fazer o primeiro backup e a primeira restauração de verdade**

Este passo **não é opcional**. É o que transforma o backup em backup.

```bash
python -m scripts.backup backups/
docker compose exec db createdb -U bddente bddente_restaurado
python -m scripts.restaurar backups/bddente-$(date +%F).dump \
  postgresql://bddente:bddente@localhost:5432/bddente_restaurado
```
Expected: `restauracao conferida.` com as três contagens em `ok`

Anote a data na tabela de `docs/OPERACAO.md`.

- [ ] **Step 9: Commitar**

```bash
git add fly.toml scripts docs/OPERACAO.md app/main.py tests/test_operacao.py
git commit -m "feat: deploy no Fly.io, backup diario e teste de restauracao"
```

---

## Quando o MVP está pronto

Marque só quando todos passarem:

- [ ] `pytest -v` verde, incluindo os testes de migração contra o extrato real
- [ ] `ruff check .` sem erros
- [ ] `python -m migracao` termina com **conferência aprovada**
- [ ] O banco tem `5561 | 44812 | 29350 | 3461389.07`
- [ ] Login funciona, sessão expira, `/pacientes` sem sessão vai para `/login`
- [ ] Buscar um paciente e abrir o odontograma leva menos de 3 segundos
- [ ] Lançar um tratamento numa região pinta o dente sem recarregar a página
- [ ] "Repetir em outro dente" lança em 4 dentes com 4 cliques
- [ ] O PDF do prontuário abre e tem o histórico dentro
- [ ] Uma restauração de backup foi feita e conferida, com a data anotada

## O que fica pendente de gente, não de código

| Item | Quem resolve |
|---|---|
| Traduzir os 309 códigos de ícone (`OICO14`, `d01RX`…) — 3 códigos cobrem metade dos 9.629 registros | **Dra. Kátia**, ~15 minutos de conversa |
| Validar o odontograma com quem vai usar — o layout foi aprovado pelo desenvolvedor, não pela dentista | **Dra. Kátia**, antes de congelar a tela |
| Confirmar o espelhamento mesial/distal olhando um caso real que ela lembre | **Dra. Kátia** — o teste cruzado da Task 14 garante consistência interna, não que a convenção do Dentalis fosse essa |
| Nomes dos convênios 003 a 006, que não existem no banco antigo | **Dra. Kátia** |
| Fotos e radiografias: não existem no backup | **Dra. Kátia** — se houver em outro lugar, é escopo novo |

## Limites conhecidos e conscientes do MVP

Nenhum destes é esquecimento — são escolhas, anotadas para não virarem surpresa:

- **A camada azul (`condicao`) é somente leitura.** Os 9.629 registros históricos são
  migrados e desenhados no odontograma, mas o MVP não tem tela para registrar uma
  condição nova. A spec pede a camada como exibição; criar condição entra quando os
  309 códigos forem traduzidos e houver vocabulário para oferecer na tela.
- **Não há tela de edição de cadastro de paciente.** O MVP lê e busca; a correção dos
  dados marcados em `revisar_motivo` é um passo seguinte.
- **Um usuário só, sem perfis.** Foi decisão da spec. A `auditoria` já grava
  `usuario_id`, então acrescentar gente depois não muda o schema.
- **Sem paginação na lista de pacientes.** A busca limita a 100 resultados. Com 5.561
  cadastros e uma busca no centro da tela, paginar seria resolver um problema que ela
  não tem.
- **Os filtros "Com pendência" e "Em aberto" peneiram em Python** sobre uma folga de
  10× o limite vinda do banco. Se um dia o volume crescer, isso vira subconsulta.
