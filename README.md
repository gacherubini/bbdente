# BDDente

Prontuário odontológico web que substitui o **Dentalis** — o sistema em FoxPro que
rodou no consultório da Dra. Kátia de 1996 a 2024 e hoje é inutilizável.

O MVP entrega login, cadastro de pacientes, odontograma com lançamento de tratamento,
catálogo de tratamentos, anamnese e exportação do prontuário em PDF — **com os 30 anos
de histórico clínico migrados**, sem perder um registro.

- Uma dentista, um consultório, 5.561 pacientes no cadastro histórico
- 44.812 lançamentos clínicos e 9.629 condições pré-existentes a preservar
- Uso em produção real desde o primeiro dia: migração, LGPD e backup são escopo do
  MVP, não fase 2

## Situação

| Parte | Estado |
|---|---|
| Aplicação (19 tasks do plano) | **pronta** — 265 testes passando, `ruff` limpo |
| Migração dos dados históricos | **código pronto, ainda não executada** — ver [`docs/MIGRACAO.md`](docs/MIGRACAO.md) |
| Deploy, backup e restauração | **código pronto**, restauração ainda não testada — ver [`docs/OPERACAO.md`](docs/OPERACAO.md) |

Os 46 testes que aparecem como `skipped` são os da migração: eles só rodam com o
extrato do Dentalis presente, e esse arquivo nunca entra no repositório.

## Stack

Python 3.12 · FastAPI · Jinja2 · SQLAlchemy 2 · psycopg 3 · Alembic · PostgreSQL 16 ·
argon2 · itsdangerous · fpdf2 · pytest · Docker · Fly.io

O odontograma é a única parte interativa: uma ilha de **SVG + JavaScript sem framework**
conversando com endpoints JSON. Todo o resto é Jinja2 renderizado no servidor.

## Começando

Precisa de Python 3.12+, Docker e (opcional) [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"     # ou: .venv/bin/pip install -e ".[dev]"

cp .env.example .env                              # ajuste DB_PORT se a 5432 estiver ocupada
docker compose up -d
docker compose exec db psql -U bddente -c "CREATE DATABASE bddente_teste"

.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.criar_usuario voce@exemplo.com "Seu Nome"
.venv/bin/uvicorn app.main:app --reload
```

Abra <http://localhost:8000/> — a raiz redireciona para `/pacientes`.

**Não há cadastro público, de propósito.** O único jeito de criar usuário é o
`scripts/criar_usuario.py` acima.

### Testes

```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
```

O `pytest` precisa do Postgres de pé e do banco `bddente_teste` criado. A URL vem de
`DATABASE_URL_TESTE` no ambiente ou, na falta dele, do `.env`. Cada sessão de teste
recria o schema do zero pelo próprio Alembic — as migrations que rodam em produção são
exatamente as que os testes exercitam.

## Como o código é organizado

```
app/
  shared/      db, tipos do domínio, notação FDI e geometria do dente
  auth/        usuário, sessão, auditoria
  pacientes/   cadastro, telefones, endereços
  catalogo/    categorias, tratamentos, convênios, preços
  clinico/     odontograma, lançamentos, condições, anamnese, prontuário em PDF
  templates/   Jinja2
  static/      bddente.css, odontograma.js, painel.js

migracao/      pacote separado: lê o extrato do Dentalis e termina numa
               conferência bloqueante. Nenhuma rota importa dele.
scripts/       criar_usuario, backup, restaurar
alembic/       migrations
tests/         espelha a árvore de app/ e migracao/
```

**Monolito modular.** Um módulo só acessa outro pela `service.py` dele — nunca importa
modelo de outro módulo, nunca faz `JOIN` em tabela de outro módulo. Quando o módulo
financeiro chegar, ele chama `clinico.service.lancamentos_do_paciente()`, não consulta
a tabela `lancamento`.

## Documentação

| Arquivo | Para quê |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Regras de trabalho no repositório — leia antes de mexer no código |
| [`docs/MIGRACAO.md`](docs/MIGRACAO.md) | Como rodar a migração dos dados históricos e o que falta |
| [`docs/OPERACAO.md`](docs/OPERACAO.md) | Deploy, backup e teste de restauração |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design do MVP: decisões, modelo de domínio, telas |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | Plano de implementação task a task |

## Duas coisas que não são negociáveis

**Nada é apagado de verdade.** Prontuário odontológico tem guarda mínima de 10 anos
após o último atendimento (e, se o paciente era menor, o prazo começa quando ele faz
18). Toda exclusão é lógica, via coluna `excluido_em`. Não há `DELETE` no código de
aplicação.

**Dado de paciente nunca é versionado.** `dados_extraidos/`, `*.sqlite`, `*.csv`,
`*.dbf` e `.env` estão no `.gitignore`. O repositório remoto é público — um `git add -A`
distraído publica prontuário. Sempre `git add` com caminhos explícitos.
