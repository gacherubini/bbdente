# Operação do BDDente

## Deploy

Na primeira vez, crie a app e o banco (região `iad`, Ashburn/Virgínia — escolhida por
custo). O banco é o Postgres não gerenciado do Fly, na menor máquina que ele oferece:

    fly orgs create bddente          # org separada: a conta do BDDente não se
                                     # mistura com outros projetos da mesma conta
    fly apps create bddente --org bddente
    fly postgres create --name bddente-db --org bddente --region iad \
        --vm-size shared-cpu-1x --vm-memory 256 \
        --initial-cluster-size 1 --volume-size 3

Uma org nova do Fly só libera recursos depois de ter cartão cadastrado, em
`https://fly.io/dashboard/bddente/billing`.

O volume de 3 GB é folga: o banco migrado inteiro tem menos de 200 MB, mas o WAL e os
índices crescem, e aumentar volume depois dá mais trabalho que pagar por 2 GB parados.

Depois, a cada versão: **não precisa rodar nada**. A Action `deploy` sobe sozinha
quando o CI passa na `main` (`.github/workflows/deploy.yml`). Ela precisa do segredo
`FLY_API_TOKEN` no repositório — crie com:

    fly tokens create deploy -a bddente
    gh secret set FLY_API_TOKEN --body "<o token>"

Para subir à mão, quando quiser:

    fly deploy

## Quanto isto custa, e por quê

| Item | Configuração | Ordem de grandeza |
|---|---|---|
| App | `shared-cpu-1x`, 512 MB, desliga quando ocioso | ~US$ 1/mês |
| Postgres | `shared-cpu-1x`, 256 MB, volume de 3 GB, um nó só | ~US$ 2,50/mês |

A máquina do app tem `min_machines_running = 0`: dorme quando ninguém está usando e
acorda na primeira requisição. Isso custa alguns segundos na primeira tela do dia e
economiza as 20 horas diárias em que o consultório está fechado. Se um dia a espera
incomodar, troque para `1` no `fly.toml` — é a única mudança necessária.

**Um nó de Postgres, não dois.** Réplica dobraria a conta para proteger contra a queda
de uma máquina; o que protege o prontuário de verdade é o backup, e ele é mais barato.

Segredos (uma vez):

    fly secrets set SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
    fly secrets set COOKIE_SEGURO=true
    fly postgres attach bddente-db

O `attach` grava `DATABASE_URL` no formato `postgres://...`; a `app/config.py`
converte para o formato do psycopg 3 sozinha — não edite o segredo à mão.

`COOKIE_SEGURO=true` faz o cookie de sessão só viajar por HTTPS. O padrão é `false`
porque o navegador recusa cookie `secure` em `http://localhost`, no desenvolvimento.

Migrations e o primeiro usuário rodam à mão depois do deploy:

    fly ssh console -C "alembic upgrade head"
    fly ssh console --pty -C "python -m scripts.criar_usuario katia@exemplo.com 'Katia'"

### Migration que o código novo já usa: aplique ANTES do deploy

A ordem importa e a armadilha é silenciosa. `fly ssh console -C "alembic upgrade
head"` roda o Alembic **de dentro da imagem em produção** — que ainda é a
anterior e não contém o arquivo da migration nova. O comando responde com
sucesso e não faz nada: `alembic current` continua marcando a revisão velha como
`(head)`, porque na visão daquela imagem ela é mesmo a última.

Se o deploy subir primeiro, o código novo procura uma coluna que não existe e a
tela quebra até alguém perceber. Para migration aditiva — coluna nova e nulável,
tabela nova — aplique **antes**, pelo túnel, com o código da sua máquina:

    fly proxy 5433:5432 -a bddente-db
    DATABASE_URL="postgres://postgres:<senha>@localhost:5433/bddente"         .venv/bin/alembic upgrade head

A `<senha>` sai de `fly ssh console -a bddente -C "printenv DATABASE_URL"`.
Migration aditiva é compatível com o código antigo: a coluna fica lá, sem ninguém
usar, até o deploy chegar. Migration que **remove** ou **renomeia** coluna não
tem esse conforto — ela precisa ser quebrada em duas, uma antes e outra depois do
deploy.

## Primeira carga: levar os 30 anos de histórico para produção

A migração roda **na máquina local**, contra o Postgres do `docker compose` — o
extrato do Dentalis é prontuário e nunca entra na imagem nem no repositório. Para
produção, o que viaja é o banco já migrado e conferido:

    .venv/bin/alembic upgrade head
    .venv/bin/python -m migracao          # termina com "conferencia aprovada"
    .venv/bin/python -m scripts.backup backups/

Com o dump em mãos, abra o túnel para o banco do Fly e restaure nele:

    fly proxy 5433:5432 -a <nome-do-banco-no-fly>
    .venv/bin/python -m scripts.restaurar backups/bddente-AAAA-MM-DD.dump \
        postgres://postgres:<senha>@localhost:5433/bddente

O `restaurar` confere as contagens no destino e falha alto se faltar registro. Só
depois disso crie o usuário da dentista:

    fly ssh console --pty -C "python -m scripts.criar_usuario katia@exemplo.com 'Katia'"

Repetir a migração é seguro: cada etapa é idempotente e nada é gravado se a
conferência reprovar.

### Levar só uma etapa nova para produção

Quando uma etapa é acrescentada depois que produção já está no ar — foi o caso do
financeiro, em 26/08/2026 — não é preciso recarregar o banco inteiro. Rode a etapa
localmente contra o Postgres do `docker compose`, confira, e leve **só a tabela
nova** pelo túnel:

    .venv/bin/alembic upgrade head        # local
    .venv/bin/python -m migracao          # idempotente; refaz só o que falta

    # a migration primeiro, pelo túnel (ver "Migration aditiva", acima)
    fly proxy 5433:5432 -a bddente-db
    DATABASE_URL="postgres://postgres:<senha>@localhost:5433/bddente"         .venv/bin/alembic upgrade head

    # depois a tabela, só ela
    .venv/bin/pg_dump --data-only --table=parcela         "postgresql://bddente:bddente@localhost:5432/bddente" > parcela.sql
    psql "postgres://postgres:<senha>@localhost:5433/bddente" < parcela.sql

Confira a contagem no destino antes de considerar feito. Para o financeiro:
28.244 parcelas, soma cobrada R$ 5.808.797,26, soma paga R$ 2.378.315,73.

## Requisitos que o provedor precisa cumprir

Dado de saúde é dado pessoal sensível pela LGPD — a categoria de maior proteção.
Confira, e anote a data da conferência:

- **HTTPS obrigatório** — garantido pelo `force_https` no `fly.toml`.
- **Criptografia em repouso no banco.** Os volumes do Fly.io são cifrados em disco; se
  um dia o banco mudar de provedor, isto tem de ser reconfirmado antes da migração,
  não depois.
- **Região do dado: Estados Unidos** (`iad`, Ashburn/Virgínia), escolhida por custo.
  A LGPD permite transferência internacional de dado pessoal sensível, mas ela é uma
  decisão a ser registrada, não um detalhe de infraestrutura: quem responde pelo
  prontuário é a clínica. Se a Dra. Kátia quiser o dado no Brasil, troque
  `primary_region` para `gru` no `fly.toml` e recrie o banco em `gru` — o resto do
  procedimento é igual.

## Backup

Duas camadas: os snapshots diários que o Fly.io tira do volume (retenção de 5 dias,
não configurável no plano barato) e uma cópia própria, guardada fora dele.

Cinco dias é pouco para prontuário — a cópia própria não é redundância, é o backup
de verdade. Se quiser uma terceira camada, `fly postgres create --enable-backups`
liga o backup contínuo em WAL, que custa alguns centavos de armazenamento por mês.

A cópia própria roda **na máquina da clínica**, não dentro do container — o container
não tem disco que sobreviva a um restart, e a imagem não leva o `pg_dump`. Abra o
túnel para o banco do Fly e rode o script contra ele:

    fly proxy 5433:5432 -a <nome-do-banco-no-fly>

E, em outro terminal:

    DATABASE_URL=postgres://postgres:<senha>@localhost:5433/bddente \
        python -m scripts.backup backups/

O script recusa dump menor que 100 KB — o banco migrado dá 1,2 MB de dump (34 MB em
disco), então dump pequeno significa dump truncado.

O `pg_dump` precisa estar instalado na máquina (no Windows, `scoop install postgresql`);
a versão do cliente pode ser mais nova que a do servidor, o contrário não.

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
| 26/08/2026 | `bddente-2026-08-26.dump` (banco local recém-migrado) | conferido: 5.561 / 44.812 / 29.350 |

## Se der problema

- **Aplicação não sobe:** `fly logs`. O health check é `GET /saude`.
- **Migration travada:** `fly ssh console -C "alembic current"` mostra onde parou.
- **Dado de paciente parece errado:** consulte `revisar_motivo` na tabela `paciente`
  e `lancamento` — a migração marca o que é suspeito em vez de corrigir no chute.
- **Nunca rode `DELETE`.** Toda exclusão do sistema é lógica (`excluido_em`).
