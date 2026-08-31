# Trabalhando neste repositório

BDDente é um prontuário odontológico que substitui um sistema FoxPro de 1996. Ele roda
em produção real num consultório, com 30 anos de histórico clínico dentro. Isso muda o
que "pronto" significa aqui: **preservar o dado vale mais que qualquer elegância de
código.**

Leia o [`README.md`](README.md) para o mapa geral. Este arquivo é o que você precisa
saber antes de editar qualquer coisa.

## Regras que não se quebram

Violar qualquer uma delas reprova o trabalho em review, mesmo que os testes passem.

1. **Nunca `DELETE` no código de aplicação.** Toda exclusão é lógica, via `excluido_em`.
   Guarda mínima de 10 anos (CFO); dado de saúde é dado pessoal sensível (LGPD).
   *Exceção anotada:* desconectar o WhatsApp em `/configuracoes` **apaga a
   credencial** — e ela vive na Evolution, não aqui. A regra protege dado de
   paciente; credencial revogada não é dado de paciente, é lixo que só serve para
   vazar. O fato vai para a `auditoria`; o conteúdo, não.
   *Exceção anotada:* corrigir o alvo de um lançamento **apaga as linhas de
   `lancamento_regiao`** dele e escreve as novas. Aquela tabela não é registro de
   paciente, é a lista de faces DESTE lançamento: trocar mesial por distal tem de
   deixar só distal, e uma linha marcada como excluída ali continuaria pintando o
   dente — o contrário de corrigir. O lançamento em si continua com exclusão
   lógica, e o alvo antigo fica inteiro na `auditoria`.

2. **Fronteira de módulo.** Um módulo só acessa outro pela `service.py` dele. Nunca
   importe `models` de outro módulo, nunca faça `JOIN` em tabela de outro módulo.
   Precisa do nome do convênio? `catalogo.service.nomes_de_convenio()`. Precisa do
   paciente? `pacientes.service.obter()`.
   *Exceção anotada:* `clinico/rotas.py` importa `auth.models.Clinica` só para ler o
   nome no cabeçalho do PDF. Está comentado no código para não virar precedente.

3. **`clinica_id` em toda tabela raiz**, e toda consulta filtra por ele. É uma clínica
   só hoje; a coluna existe desde o dia 1 para não reescrever o schema depois.

4. **A notação canônica de dente é FDI** (`11`–`18`, `21`–`28`, `31`–`38`, `41`–`48`).
   O índice sequencial 1–32 do Dentalis **só existe dentro de `migracao/`**, guardado
   como `codigo_legado`. Nenhum código fora de `migracao/` manipula índice legado.

5. **Toda escrita gera linha em `auditoria`** — quem, o quê, quando, antes e depois.
   Use `auth.auditoria.registrar()`. Ela nunca guarda senha nem hash.

6. **Nunca versione dado de paciente.** `dados_extraidos/`, `*.sqlite`, `*.csv`,
   `*.dbf`, `.env` estão no `.gitignore`. O remoto é público. Sempre `git add` com
   caminhos explícitos — nunca `git add -A`.

7. **TDD.** Escreva o teste, veja falhar, então implemente. Vale principalmente para a
   lógica pura de `shared/dentes.py` e `migracao/posdente.py`, que é onde mora o risco.

8. **Mensagem para paciente só carrega o que está em
   `agenda/mensagem.py::ContextoDaMensagem`.** Nome, dia, hora e dados da clínica —
   nove campos, e a lista é positiva. Nunca tratamento, dente, região, valor,
   documento nem a `observacao` do horário: dado de saúde é dado sensível, e mensagem
   de WhatsApp é lida na tela de bloqueio, no ônibus, pela chefe. A barreira é o tipo
   (`renderizar()` recebe o dataclass, nunca um `dict`) e há dois testes de contrato
   que falham se alguém acrescentar campo. **Leia o docstring antes de alargar.**

9. **Nomes de domínio em português**: `paciente`, `lancamento`, `regiao`, `escopo`,
   `condicao`. Nomes de biblioteca ficam como são.

## Onde mora o risco

**Espelhamento mesial/distal.** Mesial é "em direção à linha média" — o que significa
lados opostos da tela nos quadrantes 1/4 versus 2/3. Errar isso grava 44.812 registros
invertidos, e o erro é silencioso: tudo parece funcionar.

Duas fontes independentes decidem isso, e existe um teste cruzado que prova que elas
concordam nos 32 dentes (`tests/shared/test_geometria_dente.py`):

- `migracao/posdente.py` — decodifica a coordenada de tela do Dentalis
- `app/shared/dentes.py` — decide qual parede do desenho é qual região

**Se você mexer em uma, o teste cruzado tem que continuar passando.** E note o que ele
garante: que as duas fontes concordam entre si — não que a convenção do Dentalis fosse
a clinicamente correta. Essa confirmação só a dentista pode dar.

**O carnê do Dentalis.** Ele não tinha tabela de carnê: quando o paciente pagava
uma parcela, o sistema **regravava o saldo restante** numa linha nova, com o mesmo
vencimento. Sete linhas caindo 1.200, 1.050, 900… com R$ 150 pagos em cada não são
sete dívidas de R$ 5.250 — são uma dívida de R$ 1.200 paga em sete vezes.

Somar todas as linhas inflava o "a receber" em **R$ 1.392.888,31 (41%)**. As 5.163
linhas já superadas entram no banco com o valor como veio e ficam marcadas em
`parcela.substituida`; a soma da dívida pula as marcadas, e a do dinheiro recebido
**não** — cada degrau registra um pagamento que aconteceu de verdade.

Se mexer em `migracao/financeiro.py`, a regra de detecção é deliberadamente
estreita e tem de continuar assim: mesmo paciente, mesmo vencimento, valores
estritamente decrescentes e cada degrau igual ao valor pago naquela linha. Alargar
isso apaga dívida de verdade.

**A agenda não é prontuário, e a ponte entre as duas é de mão única.** Um
`agendamento` sem paciente (`paciente_id` nulo + `nome_avulso`) é a anotação de um
telefonema — não entra em PDF, não soma dinheiro, não afirma nada sobre a saúde de
ninguém. Por isso marcar horário nunca exige cadastro. O sentido do acoplamento é
`agenda.service` → `clinico.service` e `pacientes.service`; a volta
(`agenda.service.vincular_paciente`) é chamada de `clinico/api.py`, **nunca** de
`clinico/service.py`, senão é ciclo de import de verdade. E `vincular_paciente()`
não levanta exceção por decisão, não por descuido: ela roda depois de o prontuário
estar gravado, e **o prontuário é mais importante que a agenda** — id velho numa aba
aberta há uma hora não pode fazer um tratamento se perder.

**A regra de espelhamento não pode vazar para o JavaScript.** `odontograma.js` recebe
`paredes` e `canais_tela` prontos do servidor e não sabe anatomia. Há um teste que
falha se o JS voltar a calcular isso sozinho.

## Ambiente

Tudo roda pelo venv do projeto — **use os binários dele, nunca o `python`/`pip` do
sistema**:

```bash
.venv/bin/python   .venv/bin/pytest   .venv/bin/ruff   .venv/bin/alembic
```

O Postgres local sobe com `docker compose up -d`. Se a 5432 já estiver ocupada por
outro projeto, defina `DB_PORT` no `.env` e ajuste as URLs junto — o `docker-compose.yml`
lê `${DB_PORT:-5432}`.

Os testes precisam do banco `bddente_teste` e da variável:

```bash
DATABASE_URL_TESTE=postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste \
  .venv/bin/pytest -q
```

Sem a variável no ambiente, o `conftest.py` cai no `.env` local.

**A suíte roda no relógio da clínica.** A agenda guarda hora de parede, e o libpq
manda o fuso do processo para o Postgres como `TimeZone` da sessão — então um
`agendado_para` gravado às 21h numa máquina em UTC volta do banco como 21h UTC e
vira 18h na parede. Máquina fora de `America/Sao_Paulo` reprova três testes de
`tests/agenda/test_lembretes.py` sem que haja nada errado no código; o `fly.toml`
e o `ci.yml` já põem `TZ=America/Sao_Paulo` pelo mesmo motivo. Fora do Brasil:

```bash
TZ=America/Sao_Paulo .venv/bin/pytest -q --ignore=tests/migracao
```

### Peculiaridades do lint que já custaram tempo

O `ruff` deste repo usa `select = ["E", "F", "I", "UP", "B"]`. Consequências:

- `datetime.UTC`, nunca `timezone.utc` (`UP017`)
- nada de variável chamada `l` (`E741`)
- imports ordenados pelo isort — rode `.venv/bin/ruff check --fix` em vez de brigar
- `Depends()`/`Form()` em default de argumento são permitidos por
  `flake8-bugbear.extend-immutable-calls` no `pyproject.toml`; não "conserte" isso
- `alembic/versions/*.py` ignora `E501` — as migrations são geradas, não formatadas
  à mão

## Comandos

| O quê | Comando |
|---|---|
| Testes | `.venv/bin/pytest -q` |
| Lint | `.venv/bin/ruff check .` (com `--fix` para arrumar import) |
| Subir o app | `.venv/bin/uvicorn app.main:app --reload` |
| Migration nova | `.venv/bin/alembic revision --autogenerate -m "..."` |
| Aplicar migrations | `.venv/bin/alembic upgrade head` |
| Criar usuário | `.venv/bin/python -m scripts.criar_usuario email "Nome"` |
| Migrar o histórico | `.venv/bin/python -m migracao` (ver [`docs/MIGRACAO.md`](docs/MIGRACAO.md)) |

### Quanto os testes demoram, e por quê

`pytest -q` inteiro leva **minutos na sua máquina e segundos no CI**, e a diferença
não é um problema a resolver: `tests/migracao/` migra o extrato real do Dentalis
— 5.561 pacientes, 44.812 lançamentos — contra o Postgres de verdade, várias
vezes. No CI esses testes se **pulam sozinhos**, porque o extrato é prontuário e
nunca entra no repositório.

Enquanto estiver mexendo em qualquer coisa que não seja migração, rode

```bash
.venv/bin/pytest -q --ignore=tests/migracao     # ~47 s, 992 testes
```

e deixe a suíte inteira para antes do commit. **Uma rodada só por vez:** duas
invocações do pytest ao mesmo tempo brigam pelo mesmo `bddente_teste`, e a
segunda derruba o schema debaixo da primeira — o sintoma é uma rodada que nunca
termina e erros que não se reproduzem.

O custo fixo do setup era de 9 a 100 segundos por invocação até 27/08/2026,
quando o `conftest.py` trocou `alembic downgrade base` por `DROP DATABASE`
(0,35 s, e sem herdar sujeira da rodada anterior). O caminho de volta das
migrations continua coberto, agora por `tests/test_migrations.py`.

O que sobrou de lento é trabalho de verdade, e está medido: `tudo_migrado`, em
`tests/migracao/test_migracao_completa.py`, é fixture **de função** e é usada por
**11 testes** — a migração inteira roda 11 vezes, do zero, cada uma. Passá-la para
`scope="session"` é a otimização óbvia que ainda não foi feita: os 11 testes só
contam e leem, então compartilhar o banco migrado entre eles não os faria enxergar
um ao outro de um jeito que importe. Fica anotado como escolha em aberto, não como
esquecimento.

## Por onde começar, dado o que você quer fazer

| Quero... | Olhe primeiro |
|---|---|
| entender o domínio | `docs/superpowers/specs/2026-08-25-bddente-mvp-design.md` |
| mexer no odontograma | `app/shared/dentes.py`, depois `app/static/odontograma.js` |
| mexer no atendimento sem paciente | `app/static/rascunho.js` e `app/clinico/api.py` |
| mexer em lançamento | `app/clinico/service.py` (`lancar`, `editar_lancamento`, `estado_do_odontograma`) |
| mexer na correção de um lançamento | `app/static/painel.js` (o painel corrige) e `app/static/historico.js` (a tabela) |
| mexer na busca de paciente | `app/pacientes/service.py` (`buscar`) |
| mexer no financeiro | `app/financeiro/service.py`, depois `app/static/graficos.js` |
| mexer na agenda | `app/agenda/service.py` (`grade`, `marcar`), depois `app/templates/agenda_semana.html` |
| mexer na migração | `migracao/AGENTS.md` |
| entender uma decisão | o plano em `docs/superpowers/plans/` explica o *porquê* de cada task |

## Ao terminar

Rode `.venv/bin/ruff check .` e `.venv/bin/pytest -q` antes de dizer que acabou, e cole
a saída. Se algum teste falha, diga que falha. Um trabalho que "deve estar funcionando"
não está verificado.

## Limites conscientes do MVP

Nenhum destes é esquecimento — são escolhas registradas para não virarem surpresa:

- A camada azul (`condicao`) é **somente leitura**: os 9.629 registros históricos são
  desenhados, mas não há tela para registrar condição nova. Isso espera a tradução dos
  309 códigos de ícone do Dentalis.
- **O cadastro edita a ficha, não o histórico.** Nome, telefone, nascimento,
  convênio, CPF, endereço residencial, quem indicou e observação são editáveis;
  `codigo_legado` não é (é a chave que liga o cadastro aos 30 anos migrados), e o
  endereço comercial que veio do Dentalis é lido mas não editado.
- **CPF com dígito errado entra marcado, nunca recusado** (`cpf_suspeito`) — a
  mesma régua do telefone: quem cadastra está com a pessoa na frente.
- **O atendimento da boca em branco vive só no navegador** até ser concluído. O
  menu `Odontograma` abre um odontograma sem dono; os tratamentos marcados ficam
  em `localStorage` e no `POST /api/atendimento` viram lançamentos de uma vez só.
  Consequência aceita: rascunho não atravessa computadores, e fechar o navegador
  antes de concluir perde o que foi marcado. A alternativa — gravar lançamento
  sem paciente — criaria dado clínico órfão, que é pior.
- Um usuário só, **sem papéis nem permissões** — não confundir com a tela
  `/perfil`, que existe e serve para a própria pessoa ver seus dados e trocar a
  senha. A `auditoria` já grava `usuario_id`, então acrescentar gente depois não
  muda o schema.
- **Trocar a senha derruba as sessões abertas.** O cookie carrega uma marca
  derivada do `senha_hash` (`auth.senha.impressao`), conferida a cada pedido.
  Por isso `assinar()` recebe o `Usuario`, não o `id`: sem o hash não dá para
  emitir cookie. Cookie sem marca é recusado — não há período de tolerância.
- Sem paginação: a busca limita a 100 resultados. O corte acontece no banco,
  **depois** do `ORDER BY` — trocar a ordem da lista troca quais 100 aparecem.
- Só dentição permanente (32 dentes). Decíduo fica para v2.
- **Dois cadastros do banco não são pessoas do ARQCLIEN**, e é de propósito:
  `SEM-CODIGO` guarda os 33 lançamentos cujo `CODICLIE` já vinha vazio do Dentalis, e
  `1104/OR` é alguém que só existia no arquivo de orçamento mas tinha anamnese
  respondida. Ambos entram marcados em `revisar_motivo`. Por isso `paciente` tem
  5.561 linhas para 5.559 cadastros vindos do ARQCLIEN.
- **Forma de pagamento não existe no histórico.** 28.234 das 28.244 parcelas do
  Dentalis têm `CODTPAG = '00'` (vazio). Só faz sentido para o que for registrado
  daqui para frente — por isso não há gráfico de "recebido por forma de pagamento".
- **A leitura do carnê espera confirmação da Dra. Kátia.** São R$ 1,4 milhão de
  diferença no que a clínica acha que tem a receber. Nenhuma linha foi perdida: se
  ela disser que são cobranças separadas, um `UPDATE parcela SET substituida=false`
  desfaz.
- **O "a fazer" da lista de pacientes e o "a receber" do financeiro são números
  diferentes.** O primeiro é tratamento planejado e não feito; o segundo é
  tratamento feito e não pago. Nunca chame os dois de "em aberto".
- **A sessão do WhatsApp nunca entra no banco do BDDente.** Ela mora dentro da
  Evolution — na base `evolution`, que é dela e só dela no mesmo cluster, e nos
  arquivos do volume dela (`infra/evolution/fly.toml`).
  O BDDente guarda da conexão três colunas que já aparecem na tela — estado, número
  e a hora em que foi visto — e há um teste de schema que reprova coluna nova cujo
  nome sugira guardar credencial. Pela mesma razão, **a agenda lê esse estado do
  banco e nunca fala com o provedor**: ela é a tela mais aberta do sistema e não
  pode ficar lenta por causa de um acessório.
- **`condicao.dente` pode ser nulo**: 5.522 dos 9.629 ícones do Dentalis (`OICOn`) são
  da boca inteira, não de um dente. Entram guardados, mas não são desenhados.
