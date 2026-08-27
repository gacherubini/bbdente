# BDDente

Prontuário odontológico web que substitui o **Dentalis** — o sistema em FoxPro que
rodou no consultório da Dra. Kátia de 1996 a 2024 e hoje é inutilizável.

Entrega login, cadastro de pacientes, odontograma com lançamento de tratamento,
catálogo de tratamentos com preço por convênio, anamnese, prontuário em PDF, financeiro
(produção, a receber e recebimentos) e **agenda** — com os 30 anos de histórico clínico e
financeiro migrados, sem perder um registro.

- Uma dentista, um consultório, 5.559 pacientes no cadastro histórico
- 44.812 lançamentos clínicos e 9.629 condições pré-existentes a preservar
- Uso em produção real desde o primeiro dia: migração, LGPD e backup são escopo do
  MVP, não fase 2

## Situação

**Em produção, em uso real.** 914 testes passando, `ruff` limpo, deploy automático a
cada `push` na `main`.

| Parte | Estado |
|---|---|
| Prontuário: pacientes, odontograma, lançamentos, anamnese, PDF | **no ar** |
| Migração do histórico clínico e financeiro | **executada** — ver [`docs/MIGRACAO.md`](docs/MIGRACAO.md) |
| Financeiro: produção, a receber, recebimentos | **no ar** |
| Agenda: semana, mês, marcar, atender a partir do horário | **no ar** |
| Lembrete por WhatsApp | **encanamento pronto e desligado** — envio simulado, nada sai para ninguém |
| Deploy, backup e restauração | **no ar**, restauração testada — ver [`docs/OPERACAO.md`](docs/OPERACAO.md) |

Os 67 testes que aparecem como `skipped` são todos os da migração: eles só rodam com o
extrato do Dentalis presente, e esse arquivo nunca entra no repositório.

### O lembrete de WhatsApp está desligado por dois motivos independentes

A chave geral (`configuracao_clinica.lembrete_ativo`) nasce `false`, e quem "envia" é um
provedor de mentira que registra o que enviaria. **É preciso desfazer os dois para uma
mensagem sair.** O que falta para ligar de verdade é um chip novo — nunca o número da
clínica — e a conexão por QR code. O porquê de cada condição está em
[`docs/OPERACAO.md`](docs/OPERACAO.md).

## Stack

Python 3.12 · FastAPI · Jinja2 · SQLAlchemy 2 · psycopg 3 · Alembic · PostgreSQL 16 ·
argon2 · itsdangerous · fpdf2 · pytest · Docker · Fly.io

O odontograma é a parte interativa: uma ilha de **SVG + JavaScript sem framework**
conversando com endpoints JSON. Fora dele há uma única ilha pequena, o campo "quem vem"
da agenda. Todo o resto é Jinja2 renderizado no servidor, e **tudo funciona sem
JavaScript** — o formulário da agenda inclusive, que sem o script vira texto livre e
marca horário avulso.

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
  auth/        usuário, sessão, auditoria, identidade da clínica
  pacientes/   cadastro, telefones, endereços, consentimento de WhatsApp
  catalogo/    categorias, tratamentos, convênios, preços
  clinico/     odontograma, lançamentos, condições, anamnese, prontuário em PDF
  financeiro/  parcelas, recebimentos, produção e a receber
  agenda/      horários, grade da semana e do mês, lembrete de WhatsApp
  templates/   Jinja2
  static/      bddente.css, odontograma.js, painel.js, agenda_quem.js

migracao/      pacote separado: lê o extrato do Dentalis e termina numa
               conferência bloqueante. Nenhuma rota importa dele.
scripts/       criar_usuario, backup, restaurar
alembic/       migrations
tests/         espelha a árvore de app/ e migracao/
```

**Monolito modular.** Um módulo só acessa outro pela `service.py` dele — nunca importa
modelo de outro módulo, nunca faz `JOIN` em tabela de outro módulo. O financeiro chama
`pacientes.service.nomes_de()` em vez de consultar a tabela `paciente`; a agenda chama
`clinico.service.atendidos_por_dia()` em vez de olhar `lancamento`.

A ponte entre agenda e prontuário é de mão única: `agenda.service` importa
`clinico.service`, e a volta sai de `clinico/api.py` — nunca da `service.py` dele, senão
é ciclo de import.

## Documentação

| Arquivo | Para quê |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Regras de trabalho no repositório — leia antes de mexer no código |
| [`app/AGENTS.md`](app/AGENTS.md) | Detalhe por módulo: a fronteira, o odontograma, a agenda e o lembrete |
| [`docs/MIGRACAO.md`](docs/MIGRACAO.md) | O procedimento da migração dos dados históricos |
| [`docs/OPERACAO.md`](docs/OPERACAO.md) | Deploy, backup, restauração e a operação do lembrete |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design do MVP: decisões, modelo de domínio, telas |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | Plano de implementação task a task, com o *porquê* de cada decisão |

O plano da agenda ([`docs/superpowers/plans/2026-08-27-agenda-design.md`](docs/superpowers/plans/2026-08-27-agenda-design.md))
tem a discussão inteira do WhatsApp: o risco de banimento com as fontes, a comparação
com a API oficial, e o que fica de fora da mensagem por causa da LGPD.

## Três coisas que não são negociáveis

**Nada é apagado de verdade.** Prontuário odontológico tem guarda mínima de 10 anos
após o último atendimento (e, se o paciente era menor, o prazo começa quando ele faz
18). Toda exclusão é lógica, via coluna `excluido_em`. Não há `DELETE` no código de
aplicação.

**Mensagem para paciente não carrega prontuário.** O que pode ir numa mensagem de
WhatsApp está numa lista *positiva* de nove campos em `app/agenda/mensagem.py`: nome,
dia, hora e dados da clínica. Nunca tratamento, dente, região, valor, documento nem a
anotação do horário — que é texto livre e é justamente onde vai estar escrito "canal 36".
"Consulta amanhã às 14h" é um compromisso; "canal no dente 36 amanhã às 14h" é
prontuário exposto na tela de bloqueio do celular, no ônibus. A barreira é o tipo (a
função de renderizar recebe um dataclass congelado, nunca um `dict`) e há dois testes de
contrato que falham se alguém acrescentar um campo.

**Dado de paciente nunca é versionado.** `dados_extraidos/`, `*.sqlite`, `*.csv`,
`*.dbf` e `.env` estão no `.gitignore`. O repositório remoto é público — um `git add -A`
distraído publica prontuário. Sempre `git add` com caminhos explícitos.
