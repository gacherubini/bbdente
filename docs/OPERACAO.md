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

A máquina do app tem `min_machines_running = 1`: **ela não dorme mais**, e isso mudou
em 27/08/2026. O relógio dos lembretes (`app/agenda/relogio.py`) bate de 15 em 15
minutos para avisar cada paciente na hora dela — máquina dormindo é relógio parado. O
Evolution/WhatsApp vai exigir o mesmo socket vivo. **Custo: ~US$ 3 a 5/mês a mais**, e
ele é do pacote "lembrete por WhatsApp", não do relógio sozinho.

Se um dia os lembretes forem desligados de vez, voltar para `0` devolve a economia — e
é a única mudança necessária.

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

O primeiro usuário roda à mão, uma vez:

    fly ssh console --pty -C "python -m scripts.criar_usuario katia@exemplo.com 'Katia'"

### Migration: o deploy aplica sozinho, e para se falhar

O `release_command` do `fly.toml` roda `alembic upgrade head` numa máquina
temporária com a **imagem nova**, antes de ela receber trânsito. Se a migration
falhar, o Fly aborta o deploy e a versão anterior continua no ar — o banco nunca
fica à frente de um código que não subiu.

**Nunca troque isso por `fly ssh console -C "alembic upgrade head"`.** A armadilha
é silenciosa: esse comando roda o Alembic de dentro da imagem que já está em
produção — a anterior, que não contém o arquivo da migration nova. Ele responde
com sucesso e não faz nada, `alembic current` continua marcando a revisão velha
como `(head)` (na visão daquela imagem ela é mesmo a última), e o código novo sobe
procurando uma coluna que não existe.

Migration que **remove** ou **renomeia** coluna continua precisando de duas etapas:
o `release_command` roda antes do código novo, então a coluna sumiria debaixo do
código antigo que ainda está atendendo. Quebre em duas — a que só acrescenta vai
com o deploy que passa a usar; a que remove vai no deploy seguinte, quando ninguém
mais lê a coluna.

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

    # a migration de produção sai junto com o deploy (release_command);
    # aqui falta só levar a tabela nova pelo túnel
    fly proxy 5433:5432 -a bddente-db

    # a tabela, só ela
    .venv/bin/pg_dump --data-only --table=parcela         "postgresql://bddente:bddente@localhost:5432/bddente" > parcela.sql
    psql "postgres://postgres:<senha>@localhost:5433/bddente" < parcela.sql

Confira a contagem no destino antes de considerar feito. Para o financeiro:
28.244 parcelas, soma cobrada R$ 5.808.797,26, soma paga R$ 2.378.315,73.

## O lembrete de WhatsApp

### Hoje: nada sai para ninguém

O encanamento inteiro está pronto e testado, mas **desligado por dois motivos
independentes**, e é preciso desfazer os dois para uma mensagem sair:

1. `configuracao_clinica.lembrete_ativo` nasce `false` — deploy que já sai mandando
   mensagem para paciente é a definição de acidente.
2. Quem "envia" é o `ProvedorFake`, que registra no banco o que enviaria e não fala
   com ninguém.

A tela `/configuracoes` diz isso em voz alta: enquanto o provedor for o de mentira, ela
mostra *"nenhum WhatsApp conectado — o envio está simulado"* em vez de fingir uma
conexão que não existe.

### Ligar de verdade, quando o número existir

A decisão foi por **Baileys** (via Evolution API), e não pela API oficial. Ela vem com
quatro condições que o plano trata como obrigatórias — a primeira é a que mais importa:

1. **O número é o pessoal da mãe do dono do projeto, já usado no dia a dia** — decisão
   dele, tomada em 27/08/2026, revertendo o "chip novo" do plano original. E a troca é
   defensável: a detecção do WhatsApp pesa razão de resposta, distância no grafo de
   contatos e ritmo robótico, então um número recém-criado que começa a mandar
   mensagem parecida para desconhecidos é o perfil exato que ela procura — enquanto um
   número com anos de conversa real, no qual várias pacientes já são contato, é o
   oposto. **A probabilidade de bloqueio cai; o prejuízo, se acontecer, sobe**, porque
   o que se perde é o WhatsApp pessoal dela, e banimento aqui é permanente e sem
   apelação. As condições 2 e 3 deixam de ser recomendação e passam a ser
   inegociáveis por causa disso.
2. **Volume e ritmo humanos**: teto diário e pausa aleatória de 20 a 90 segundos entre
   envios, já no código. A detecção pesa razão de resposta, distância no grafo de
   contatos e ritmo robótico — e um lembrete para paciente conhecida, em volume baixo e
   irregular, é o perfil oposto disso.
3. **Playbook de queda** (abaixo), com o critério de desistir: **duas quedas em 30 dias
   e migra-se para a API oficial**, sem nova discussão.
4. **O provedor é uma interface** (`app/agenda/whatsapp/`) com implementação escolhida
   por variável de ambiente. Migrar depois de um banimento é trocar um segredo e
   reiniciar, não reescrever a funcionalidade.

O `fly.toml` já está com `min_machines_running = 1` desde 27/08/2026 (o relógio
precisava dele antes da Evolution). Manter a máquina e um socket vivos custa **+US$ 3 a
5/mês** sobre a conta original, e esse custo existe *por causa* da escolha não
oficial — entra na conta. Para comparação, a API oficial cobra da
ordem de US$ 0,008 por mensagem *utility* no Brasil, uns US$ 0,80/mês com 100 consultas,
e deixaria a máquina continuar dormindo.

### Quem dispara, e quando

**Cada paciente é avisada na hora dela.** O vencimento é `hora da consulta menos 24 h`
(a antecedência é ajustável na tela), e um relógio dentro do próprio app bate de
**15 em 15 minutos** até passar por ele. Consulta das 21h é avisada entre 21h00 e
21h15 da véspera; a das 8h, às 8h da véspera. **Não existe "hora do disparo".**

Isso mudou em 27/08/2026. Antes era uma leva por dia às 18h, e ninguém recebia as 24
horas prometidas: quem tinha consulta às 22h era avisado 28 horas antes, e quem tinha
às 8h, 14 horas antes.

O relógio mora dentro do app de propósito. Ele precisa bater o dia inteiro, e o
Evolution já obriga a máquina a ficar de pé; com ela acordada de qualquer forma, um
serviço de cron de terceiro seria mais uma conta para manter, mais um segredo e mais
uma coisa para quebrar em silêncio. **Ele nunca levanta exceção**: banco reiniciando,
deploy no meio, rede caindo — erra a batida, registra no log e tenta de novo em quinze
minutos.

**Quem marcou depois da hora de avisar não recebe.** Marcou às 12h de hoje para as 9h
de amanhã? O vencimento passou às 9h da manhã, e não sai mensagem. Aparece na tela de
Configurações como "marcado depois da hora de avisar", para alguém ligar. Atraso do
próprio sistema (uma queda do app) **não** conta como isso: a conta é com a hora em que
o horário foi marcado, não com o relógio de agora.

#### O gatilho de emergência

Para forçar uma passada sem esperar a próxima batida, há o botão **"Enviar agora os que
já venceram"** na tela de Configurações — e ele não adianta lembrete nenhum: manda o
que já venceu, e o que ainda não venceu continua esperando a hora da paciente.

Por fora, o mesmo caminho tem um endereço. É um `POST`, não um `GET` — para que um
crawler não dispare a agenda inteira:

    POST /tarefas/lembretes
    X-Tarefa-Token: <o segredo>

Segredo, uma vez:

    fly secrets set TAREFAS_TOKEN="$(python -c 'import secrets;print(secrets.token_hex(32))')"

**Token errado responde 404, nunca 401.** Um 401 confirmaria que o endereço existe.
Ambiente sem `TAREFAS_TOKEN` também responde 404: não pode haver uma porta que qualquer
um abre mandando o cabeçalho vazio.

O endpoint é idempotente por construção (`UNIQUE (agendamento_id, tipo)`), então pode
ser chamado dez vezes seguidas sem mandar nada duas vezes.

**Não é preciso contratar serviço de cron nenhum**, e vale registrar por que a ideia
foi abandonada em 27/08/2026: o relógio mora dentro do app agora. Se um dia alguém
quiser um monitor externo assim mesmo, fica a armadilha já mapeada — **GitHub Actions
agendado não serve**, porque o GitHub desliga workflow agendado depois de 60 dias sem
commit no repositório, e este é um app de clínica: vai ficar meses parado.

**Como se percebe que parou.** O relógio está dentro do app, então "o relógio parou" é
a mesma coisa que "o app caiu" — e disso o healthcheck do Fly (`/saude`, de 30 em 30
segundos) já cuida. A tela de Configurações mostra "última mensagem enviada" como
informação; ela **não** vira alarme vermelho, porque um feriado prolongado sem consulta
deixaria a faixa vermelha à toa, e alarme que grita sem motivo se aprende a ignorar.

### A chave geral, e o que ela faz com a fila

`/configuracoes` tem um LIGADO/DESLIGADO que governa as duas fases: desligada, nem a
reserva roda, e nada entra em fila.

**Religar não dispara acumulado**, e isso é consequência do desenho, não de um `if`
extra: a fila é *derivada da agenda*, não guardada. Ao religar, o próximo disparo olha
as consultas das próximas horas e reserva do zero — o que ficou para trás está sob o
corte de 6 horas e vira `EXPIRADO`, nunca uma enxurrada de mensagens sobre consulta que
já aconteceu.

Enquanto está desligada, **a agenda diz que está desligada**, numa linha no topo.
Silêncio que parece funcionamento é a pior forma de desligar: ela confiaria que a
paciente foi avisada, e a paciente não foi.

### Playbook de queda

Vale a partir do dia em que houver um provedor de verdade.

1. **Como se percebe:** `/configuracoes` mostra `DESCONECTADO` e os envios começam a
   falhar; a agenda mostra a faixa de aviso.
2. **Como se reconecta:** ler o QR code de novo na tela de Configurações.
3. **Quando desistir:** duas quedas em 30 dias → migrar para a API oficial. A troca é
   de variável de ambiente, e o resto do sistema não muda.
4. **Enquanto está fora:** o horário continua sendo marcado normalmente. O lembrete é
   um acessório da agenda; a agenda não depende dele.

### Antes do primeiro envio real

- Ligar com um **agendamento de teste para o número dela mesma**, e conferir o texto
  recebido.
- Só então ligar a chave geral — e quem liga é a dentista, não o deploy.
- Lembrar que quase ninguém recebe no começo: `paciente.aceita_whatsapp` nasce nulo nos
  5.559 cadastros migrados, e nulo não recebe. A base de autorização cresce consulta a
  consulta, pelo botão "perguntar" no cartão da agenda.

### Como uma paciente pede para parar de receber

**Alguém clica no botão da ficha dela**, que grava "pediu para não receber" com
auditoria dos dois lados. É o único caminho, e é de propósito: **não existe responder
"PARAR"**, porque ninguém lê as respostas. Por isso a mensagem também nunca oferece
isso — ela pede que a paciente avise na recepção ou ligue. Prometer um canal que não
existe é pior que não oferecer canal nenhum.

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
- **Lembrete não saiu:** `/configuracoes` responde quase sempre. Nesta ordem: a chave
  geral está ligada? o "último disparo" é de hoje (se não, o cron parou)? a lista de
  "não vão receber" diz o motivo de cada uma? Um lembrete em `ENVIANDO` significa "não
  sei se saiu" e **não** é reenviado sozinho — é decisão de uma pessoa.
- **Lembrete saiu com o texto errado:** o texto que saiu fica congelado em
  `lembrete.texto`, exatamente como foi enviado. O modelo atual está em
  `/configuracoes` e pode ter mudado depois.
- **Nunca rode `DELETE`.** Toda exclusão do sistema é lógica (`excluido_em`).
