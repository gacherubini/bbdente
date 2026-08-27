# BDDente Agenda — Design e Plano de Implementação

**Data:** 2026-08-27
**Status:** plano para implementar — Fase 2 (WhatsApp) ainda em desenho
**Origem:** pedido do dono do projeto — uma aba de Agenda, intuitiva, com visão de semana e de mês

---

## 1. O problema

A Dra. Kátia marca horário no papel. Quem usa o sistema está com paciente na cadeira e telefone na mão: alguém liga, ela precisa achar um buraco na semana, escrever um nome e desligar. Qualquer coisa que exija mais de dois cliques ou uma decisão administrativa ("cadastre a paciente primeiro") volta para o papel no segundo dia.

Três verdades do consultório mandam no desenho:

1. **A maioria dos atendimentos hoje não tem horário marcado.** A agenda não pode assumir que o mundo passa por ela.
2. **Quem liga muitas vezes ainda não é paciente.** "Maria, indicação da Ana, 11 99999-9999" tem de caber num horário sem virar ficha.
3. **O que aconteceu de verdade já está no prontuário.** A agenda é uma promessa; o prontuário é o fato. Guardar o fato duas vezes é criar duas versões dele.

---

## 2. Decisões principais (resumo)

| Decisão | Escolha | Por quê |
|---|---|---|
| Módulo | `app/agenda/` novo (`models`, `service`, `rotas`) | Dono das próprias tabelas; fronteira igual às outras |
| Horário exige paciente cadastrado? | **Não.** `paciente_id` nulo + `nome_avulso`/`telefone_avulso` | Marcar horário não é dado clínico — ver §3.1 |
| Horário marcado vira lançamento? | **Nunca automaticamente** | O prontuário registra o que foi feito, não o que foi prometido |
| "Foi atendida" é status guardado? | **Não — é derivado do prontuário** | Ver §3.2 |
| Faltou / desmarcou | **Guardado** em `situacao` | Ninguém consegue derivar ausência |
| Data e hora | `Date` + `Time` ingênuos, relógio de parede da clínica | Ver §4 |
| Conflito de horário | **Avisa, nunca bloqueia** | Mesma régua do CPF suspeito e do telefone estranho |
| Desenho da semana | Grade hora × dia com cartões dentro das células | Ver §5 |
| Navegação | Pela URL (`?vista=&dia=`), servidor renderiza | Voltar funciona, dá para mandar link, imprime, dispensa JS |
| JavaScript | Só no campo "Quem" do formulário | Mesma regra do odontograma: uma ilha, não um framework |

---

## 3. Modelo de domínio

### 3.1 Um horário pode não ter paciente — e isso não contradiz o AGENTS.md

O `AGENTS.md` registra que o atendimento da boca em branco vive só no navegador porque "gravar lançamento sem paciente criaria dado clínico órfão, que é pior". A tentação é aplicar a mesma regra aqui e exigir cadastro para marcar horário. **Seria o erro oposto.**

A diferença é o que a linha significa. Um `lancamento` órfão é um pedaço de prontuário de ninguém: um fato clínico sem dono, que a lei manda guardar por 10 anos e que nunca mais se consegue atribuir. Um `agendamento` sem paciente é a anotação de um telefonema — o mesmo pedaço de papel que ela já usa hoje. Não é prontuário, não entra em PDF, não soma dinheiro, e não afirma nada sobre a saúde de ninguém.

A alternativa é pior de um jeito concreto: **criar um `Paciente` para cada pessoa que liga enche o cadastro de fantasmas.** A base tem 5.561 linhas para 5.559 pessoas, e as duas exceções estão documentadas justamente porque cadastro que não é gente incomoda para sempre. Metade de quem marca não aparece.

**A regra:** o horário pode ser avulso; o **atendimento**, não. No instante em que um tratamento é lançado, o fluxo é o que já existe — `POST /api/atendimento` cria o paciente com aviso de parecidos — e o agendamento é vinculado ao cadastro que nasceu ali. Avulso é etapa, não estado permanente.

Restrição no banco: `CHECK (paciente_id IS NOT NULL OR nome_avulso <> '')`.

### 3.2 "Atendida" é derivado, "faltou" é guardado

Se `ATENDIDO` fosse status escrito no agendamento, alguém teria de escrevê-lo. Quem? A dentista, clicando num botão que não muda nada para ela. No dia em que esquecer — ou no caso comum de atender alguém que não estava na agenda — a agenda estaria mentindo, e mentindo em silêncio.

A verdade sobre atendimento já está no prontuário. Então: **um horário aparece como atendido quando o paciente dele tem lançamento realizado naquele dia.** Uma consulta agregada, nenhuma escrita, nenhuma segunda cópia da verdade.

Isso paga um bônus grande: **quem foi atendido sem hora marcada aparece na agenda de graça**, no rodapé do dia. A agenda é útil na primeira semana, quando ainda está vazia de horários — e isso é o que decide se ela vai ser usada.

O que não dá para derivar fica guardado em `situacao`: `MARCADO` (padrão), `CONFIRMADO`, `FALTOU`, `DESMARCADO`.

`DESMARCADO` **não** é `excluido_em`. Exclusão lógica é para engano — marcou no dia errado, duplicou. Desmarcar é história do consultório. A tela só oferece "desmarcar"; excluir fica atrás de "foi engano".

Se um horário está `FALTOU` e o prontuário mostra atendimento no dia, **o derivado ganha na tela**: o fato vence a anotação. Tem teste.

### 3.3 Schema

```
agendamento
  id                 serial PK
  clinica_id         FK clinica     NOT NULL   index
  paciente_id        FK paciente    NULL       index      -- NULL = horário avulso
  nome_avulso        varchar(160)   NULL                  -- "Maria, indicação da Ana"
  telefone_avulso    varchar(24)    NULL
  dia                date           NOT NULL
  inicio             time           NOT NULL              -- relógio da clínica (§4)
  duracao_min        smallint       NOT NULL default 30
  situacao           situacao_agendamento NOT NULL default 'MARCADO'
  observacao         text           NULL
  criado_por         FK usuario     NULL
  criado_em          timestamptz    NOT NULL default now()
  excluido_em        timestamptz    NULL                  -- engano, nunca "desmarcou"

  CHECK (paciente_id IS NOT NULL OR coalesce(nome_avulso, '') <> '')
  CHECK (duracao_min BETWEEN 5 AND 600)
  INDEX ix_agendamento_clinica_dia   (clinica_id, dia)
  INDEX ix_agendamento_paciente_dia  (paciente_id, dia)

enum situacao_agendamento = MARCADO | CONFIRMADO | FALTOU | DESMARCADO
```

- **`fim` não é coluna.** É `inicio + duracao_min`, propriedade Python — mesma regra do `Parcela.saldo`.
- **`clinica_id` desde o dia 1**, e toda consulta filtra por ele.
- **`procedimento_id` fica de fora** (§8). O que vai ser feito cabe em `observacao`.
- **`profissional_id` fica de fora.** Um usuário, sem papéis.
- **FK para `paciente` declarada por nome**, sem importar o modelo — como `financeiro/models.py` faz.
- **Toda escrita chama `auth.auditoria.registrar()`** com `antes`/`depois`. Remarcar deixa os dois horários na auditoria — é por isso que não existe tabela de histórico de remarcação.

### 3.4 Fronteiras: quem chama quem

```
agenda.service ──> pacientes.service.contatos_de()      nome + telefone da lista inteira
               ──> clinico.service.atendidos_por_dia()  quem tem lançamento realizado no período

clinico.api    ──> agenda.service.vincular_paciente()   ao concluir atendimento com agendamento_id
```

Duas coisas para não errar:

1. **O sentido do acoplamento no `clinico` vive em `api.py`, nunca em `service.py`.** `agenda.service` importa `clinico.service`; se `clinico.service` importasse `agenda.service`, seria ciclo de import de verdade.
2. **A composição fica na service da agenda, não na rota.** Para duas telas (semana e mês), montar na rota viraria a mesma montagem escrita duas vezes.

**Orçamento de consultas: 3 por tela, semana ou mês.** Tem teste que conta.

---

## 4. Fuso e data — leia antes de escrever qualquer coluna

O `fly.toml` diz por que `TZ=America/Sao_Paulo` existe: a máquina roda em UTC e a clínica está em UTC-3; sem isso, `date.today()` vira o dia seguinte a partir das 21h no Brasil. A agenda multiplica a armadilha, porque agora existe **hora**.

1. **`dia` é `Date` e `inicio` é `Time`, ingênuos, relógio de parede da clínica.** Não é `timestamptz`. "Maria às 14h" quer dizer 14h no relógio da parede — hoje e daqui a três anos. Se o horário de verão voltar (foi extinto em 2019, não abolido para sempre), um `timestamptz` deslocaria os horários já marcados em uma hora; relógio de parede não desloca nada.
2. **A consulta da semana é `WHERE dia BETWEEN %s AND %s`** num índice `Date` — sem `AT TIME ZONE`, sem depender do fuso da sessão do Postgres. Mesmo desenho de `lancamento.data_realizada` e `parcela.vencimento`.
3. **`criado_em` e `excluido_em` continuam `DateTime(timezone=True)` com `datetime.now(UTC)`** — carimbos técnicos (e `UTC`, não `timezone.utc`, por causa do `UP017` do ruff).
4. **Nenhuma função de `agenda/service.py` chama `date.today()`.** O dia vem por parâmetro; quem resolve "hoje" é a rota. É o que torna o módulo testável sem congelar relógio.
5. **A semana começa na segunda.** Sábado sempre aparece; **domingo só se tiver alguma coisa**.
6. **Teste que não depende da máquina:** `semana_de(date(2026,8,27))` devolve 24/08 a 30/08, independentemente de que dia é hoje.

---

## 5. Alternativas de interface

### A — Calendário proporcional (Google Calendar)

- **A favor:** todo mundo já viu; o buraco livre é espaço vazio visível; 90 min *parecem* 90 min; abre caminho para arrastar-e-soltar.
- **Contra:** sem biblioteca, exige posicionamento absoluto, pixel por minuto e resolução de faixas para sobreposição — o tipo de código que o repositório evita de propósito. Num consultório de ~5 horas por dia, 80% da grade é pixel vazio. E cai mal no celular, que é onde ela está quando o telefone toca.

### B — Lista empilhada por dia (caderno)

- **A favor:** Jinja2 puro, zero JS, perfeito no celular, lê igual ao caderno de papel.
- **Contra:** **não responde à pergunta que importa no telefone** — "onde eu encaixo ela?". Achar um buraco entre 14h e 16h exige ler e subtrair de cabeça.

### C — Grade hora × dia, com cartões dentro das células (recomendada)

Semana = `grid` CSS de faixas de hora (linhas) por dia (colunas). Cada célula guarda zero ou mais cartões. Nada é posicionado por pixel: quem posiciona é a própria grade. A faixa de horas sai do dado da semana, com piso 08h e teto 19h.

- **A favor:** o buraco livre é uma **célula vazia** — a pergunta do telefone se responde de relance, que era a única vantagem real de (A). Custo de implementação de (B). Sobreposição não precisa de algoritmo. Em tela estreita, as colunas empilham — que é exatamente (B), de graça.
- **Contra:** 90 min não fica três vezes mais alto. Mitigação: o cartão escreve `14:00–15:30` e a célula seguinte mostra uma marca fina de continuação.
- **A célula vazia é um link:** `/agenda/novo?dia=2026-08-27&hora=09:00`. Marcar é clicar no buraco, digitar o nome, Enter. **Dois cliques, sem escolher data em lugar nenhum** — a data e a hora vieram do lugar onde ela clicou. Esse é o ponto do desenho inteiro.

**Recomendação: C.**

**O mês é outra pergunta, e por isso é outro desenho.** Ninguém lê detalhe de mês; lê "que semana está cheia". Grade 7 × 5-6, cada célula com o número do dia, até 3 linhas `hh:mm Nome`, "+N" quando passa, e uma barra fina de ocupação. Clicar no dia abre a semana dele.

---

## 6. As telas

### 6.1 Semana — `GET /agenda?vista=semana&dia=2026-08-27`

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Agenda                                              ┌────────┬─────┐        │
│  24 a 30 de agosto de 2026                           │ Semana │ Mês │        │
│                             ‹ anterior   hoje   próxima ›                    │
├────────┬─────────┬─────────┬─────────┬─────────┬─────────┬───────────────────┤
│        │  seg 24 │  ter 25 │ ●qua 26 │  qui 27 │  sex 28 │  sáb 29           │
├────────┼─────────┼─────────┼─────────┼─────────┼─────────┼───────────────────┤
│ 08:00  │         │         │         │         │         │                   │
├────────┼─────────┼─────────┼─────────┼─────────┼─────────┼───────────────────┤
│ 09:00  │┌───────┐│         │┌───────┐│         │         │                   │
│        ││AMANDA ││    +    ││MARIA ✓││    +    │    +    │        +          │
│        ││09:00· ││         ││09:30· ││         │         │                   │
│        ││30min  ││         ││60min  ││         │         │                   │
│        ││51 9…  ││         ││canal  ││         │         │                   │
│        │└───────┘│         │└───────┘│         │         │                   │
├────────┼─────────┼─────────┼─────────┼─────────┼─────────┼───────────────────┤
│ 10:00  │    +    │┌───────┐│↳ (segue)│    +    │┌───────┐│        +          │
│        │         ││Maria  ││         │         ││JÚLIA ✗││                   │
│        │         ││(sem   ││         │         ││faltou ││                   │
│        │         ││cadas- ││         │         │└───────┘│                   │
│        │         ││tro)   ││         │         │         │                   │
│        │         │└───────┘│         │         │         │                   │
├────────┴─────────┴─────────┴─────────┴─────────┴─────────┴───────────────────┤
│ sem hora marcada │         │PEDRO L. │ANA C.   │         │                   │
└──────────────────────────────────────────────────────────────────────────────┘
   ● hoje    ✓ confirmado    ✗ faltou    • atendida
```

Um cartão contém: **nome** (link para `/odontograma/{id}`, ou texto se avulso), **hora de início–fim**, **telefone como link `tel:`** (ela está com o telefone na mão), a observação truncada, e o selo de situação. Ao passar o mouse/tocar: `Confirmar · Atender · Faltou · Remarcar · Desmarcar`.

O **rodapé "sem hora marcada"** lista quem teve lançamento realizado no dia sem horário na agenda. Vem do prontuário — e é por isso que não tem hora: `lancamento` guarda data, não hora (§8).

### 6.2 Mês — `GET /agenda?vista=mes&dia=2026-08-27`

Grade 7 colunas × 5-6 linhas. Cada célula: número do dia, barra de ocupação, até 3 linhas `hh:mm Nome`, "+N". Clicar no dia abre a semana; clicar num nome abre o odontograma.

### 6.3 Marcar — `GET /agenda/novo?dia=2026-08-27&hora=09:00`

O detalhe que decide a usabilidade: **o campo de busca É o campo de nome.** Escolher da lista grava `paciente_id`; digitar e apertar Enter grava `nome_avulso` com o que ela digitou. Uma pergunta, duas saídas — sem "esta paciente já existe? [sim] [não]" antes de ela poder escrever qualquer coisa.

Sem JavaScript, o formulário continua funcionando: o campo vira texto livre e grava avulso.

---

## 7. Rotas

```
GET  /agenda?vista=semana|mes&dia=YYYY-MM-DD    a tela (uma rota, duas vistas)
GET  /agenda/novo?dia=&hora=                    formulário, já preenchido pelo clique
POST /agenda                                    marca, e volta para a semana do dia
GET  /agenda/{id}                               formulário de edição (remarcar)
POST /agenda/{id}                               grava dia/hora/duração/anotação
POST /agenda/{id}/situacao                      confirmar | faltou | desmarcar
POST /agenda/{id}/excluir                       foi engano — exclusão lógica
```

Tudo `POST` de formulário com `303` de volta: funciona sem JS, o botão "voltar" não reenvia, e não há endpoint JSON novo (o único que a tela consome, `/api/pacientes`, já existe).

---

## 8. Limites conscientes do primeiro corte

Nenhum é esquecimento; cada um tem motivo.

- **Sem arrastar-e-soltar para remarcar.** Exige ilha de JS com toque, teclado e desfazer. Digitar a hora nova são três teclas.
- **Sem horário de funcionamento configurável, sem almoço, sem férias.** A faixa vem do dado, com piso 08h e teto 19h. Depende da pergunta 2 do §10.
- **Sem série/recorrência.** Recorrência traz "editar só esta ou todas?", o problema mais caro de qualquer agenda.
- **Sem vista de dia.** Semana e mês foram o pedido; o dia já tem tela — `/atendimentos?dia=`.
- **Sem múltiplos profissionais ou cadeiras.** Uma dentista, sem papéis, como o resto do sistema.
- **Não existe hora no prontuário.** `lancamento` guarda `data_realizada`, não hora. Por isso quem foi atendido sem horário aparece no rodapé do dia. Acrescentar hora ao lançamento seria mudar o prontuário por causa da agenda, e mexeria nos 44.812 registros migrados que nunca terão essa hora.
- **`data_planejada` não vira horário marcado.** Converter automaticamente encheria a agenda de fantasmas vindos de 30 anos de histórico.
- **A agenda não conta faltas por paciente.** O dado fica gravado desde o primeiro dia; a contagem é uma consulta quando ela quiser. Não entra agora porque "esta paciente já faltou 3 vezes" é um julgamento sobre uma pessoa, e quem decide isso é a dentista.
- **Conflito avisa, nunca bloqueia.**
- **Horário avulso não vira paciente sozinho.** Só quando um atendimento é concluído.
- **O horário desmarcado continua no banco e riscado na tela.** Some da contagem, não da história.

---

## 9. Tarefas, em ordem

```
Fase 1 — o dado
  1. Tabela agendamento + enum + migration
  2. agenda/service.py — marcar, listar, remarcar, situação
  3. Fronteiras novas: clinico.atendidos_por_dia() e pacientes.contatos_de()

Fase 2 — ver e marcar (a agenda já serve no fim desta fase)
  4. Tela da semana
  5. Marcar horário
  6. O cartão: confirmar, faltou, desmarcar, remarcar

Fase 3 — o mês e a ponte com o atendimento
  7. Tela do mês
  8. Atender a partir da agenda

Fase 4
  9. Fechamento: aba, documentação, deploy
```

O detalhamento de cada task, com os requisitos e a lista de testes, está no relatório do agente que produziu este plano e é reproduzido na íntegra ao implementar. Os pontos que não podem se perder:

- **Task 1:** enum PG criado **na migration** com `.create(bind, checkfirst=True)` e `create_type=False` no model — é o padrão de `0001_schema_inicial.py`; autogenerate sozinho não faz isso direito.
- **Task 2:** o telefone avulso passa pelo **mesmo** `pacientes/telefone.py` do cadastro e da migração — uma régua só no sistema inteiro. Número estranho entra como veio, nunca é recusado.
- **Task 3:** `atendidos_por_dia` devolve id, nunca nome. A semana inteira gasta **3 consultas** — tem teste que conta.
- **Task 5:** o campo "Quem" usa `/api/pacientes`, que já existe. **Nunca uma segunda busca** — achar na agenda e não achar no atendimento vira suporte. O JS não decide regra nenhuma.
- **Task 6:** desmarcar mostra o horário **riscado**, não o some: a célula continua dizendo que alguém tinha aquele horário, e ela não remarca em cima achando que sempre esteve vazio.
- **Task 8:** `agendamento_id` desconhecido, de outra clínica ou já vinculado **não derruba o atendimento**. O prontuário é mais importante que a agenda.
- **Task 9:** `tests/test_layout.py` passa a esperar a aba nova — o teste muda porque o requisito mudou, e a mudança fica no commit.

---

## 10. Perguntas para a Dra. Kátia (nenhuma bloqueia o começo)

1. **A agenda deve ser a tela que abre o sistema?** É uma linha para voltar atrás.
2. **Que horas o consultório abre e fecha? Tem almoço fixo? Sábado, sim ou não?** É o único ajuste que muda a cara da grade.
3. **Quanto dura uma consulta típica?** Proposto: 30 min, com 60 e 90 a um clique.
4. **Ela quer registrar no horário o que vai ser feito** (escolhendo do catálogo, o que traria `procedimento.duracao_min`, que já existe no banco), ou a anotação livre basta?
5. **Falta interessa como número?**
6. **"Quem vem" e "o que foi feito" são a mesma tela na cabeça dela?** Hoje são duas abas.

---

## 11. Fase 2 — lembrete por WhatsApp

A agenda vale sozinha; o lembrete não vale nada sem ela. Por isso é fase separada,
e por isso nada aqui pode atrasar a Fase 1.

### 11.1 O que o lembrete é

Um dia antes da consulta, a paciente recebe no WhatsApp uma mensagem dizendo que
tem horário amanhã, a que horas, e como avisar se não puder vir. Só isso.

O que ele **não** é: não é confirmação de duas vias (ninguém lê a resposta no
primeiro corte), não é cobrança, não é marketing, não é recall de limpeza, e não
diz uma palavra sobre o que vai ser feito na boca dela.

### 11.2 Quem recebe — e o horário de quem não é da base

A agenda aceita dois tipos de pessoa no mesmo campo (§3.1): a paciente cadastrada
(`paciente_id`) e o telefonema anônimo (`nome_avulso` + `telefone_avulso`). O
lembrete segue essa mesma divisão, e a diferença entre as duas **não é técnica, é
de consentimento**:

| Quem | Telefone | Autorização | Recebe? |
|---|---|---|---|
| Paciente da base, com WhatsApp e `aceita_whatsapp = true` | ficha | perguntada na cadeira | **sim** |
| Paciente da base, `aceita_whatsapp` `NULL` ou `false` | ficha | não temos | não — `DESCARTADO/sem_permissao` |
| Paciente da base sem telefone aproveitável | — | — | não — `DESCARTADO/sem_numero` |
| Avulso **com** telefone digitado no agendamento | `telefone_avulso` | o próprio telefonema | **sim** |
| Avulso **sem** telefone | — | — | não — `DESCARTADO/sem_numero`, **e o horário é marcado do mesmo jeito** |

A última linha é o requisito em uma frase: **não ter WhatsApp nunca impede de
marcar.** Não é erro, não é bloqueio, não é diálogo de confirmação. O horário
entra na grade e a tela apenas mostra, no cartão, um selo cinza `sem lembrete`.

**Por que o avulso pode receber sem `aceita_whatsapp` e a paciente migrada não.**
Parece contraditório e não é. Os 5.559 telefones migrados foram coletados entre
1996 e 2025 para outra finalidade, sem registro nenhum de autorização — presumir
autorização deles é exatamente o que a lei não deixa. O telefone avulso é ditado
**agora, ao telefone, para marcar aquela consulta**; mandar o lembrete daquela
consulta é a finalidade para a qual ele acabou de ser dado. São situações
diferentes e por isso têm regra diferente.

Ainda assim ela manda: ao lado do campo de telefone no formulário do horário fica
`[x] avisar no WhatsApp na véspera`, marcado por padrão, que grava
`agendamento.avisar_avulso`. Se a pessoa disser "não me manda mensagem", ela
desmarca ali.

**Quando o avulso vira paciente** (Task 8: concluir o atendimento cria o cadastro
e vincula o agendamento), o telefone vai para a ficha e **`aceita_whatsapp` nasce
`NULL`** — o "pode avisar deste horário" não é autorização permanente para
sempre. A tela do horário mostra o selo "sem permissão de WhatsApp · perguntar"
com botão de um clique, e a autorização de verdade é registrada com a paciente ali
na frente.

### 11.3 Os quatro pontos duros, com resposta e preço

#### A. A máquina do Fly dorme

`fly.toml`: `auto_stop_machines = "suspend"`, `min_machines_running = 0`. A máquina
suspende quando ninguém usa e acorda na primeira requisição HTTP. **Às 18h de terça
não há ninguém usando** — o consultório fechou. Nada dispara sozinho.

Com a decisão por Baileys (§11.4), a saída é **`min_machines_running = 1`**:
não é só disparar, é manter um socket vivo. Custo: **+US$ 3 a 5/mês** sobre a conta
atual de ~US$ 3,50. O gatilho do horário passa a ser cron dentro do container.

Duas restrições do Fly que fecham as alternativas: máquina com `schedule` **não
pode** usar `suspend` — a opção "agendar a própria máquina do app" é incompatível
com o `fly.toml` de hoje; e máquina agendada não serve para horário preciso, o que
aqui não importa (um lembrete de 24h antes tolera sair 18:07).

Mesmo com cron interno, o endpoint existe, porque cron que morre morre em silêncio:

```
POST /tarefas/lembretes
  header X-Tarefa-Token: <segredo em fly secrets, comparado com hmac.compare_digest>
  sem sessão, sem cookie
  token errado responde 404, não 401 — o endpoint não se anuncia
  responde {"reservados": n, "enviados": n, "descartados": n, "expirados": n}
```

`POST` e não `GET` para que um crawler não dispare a agenda inteira. E ele é
idempotente (§11.6): pode ser chamado dez vezes seguidas. Contramedida contra o
cron morto, de graça: a tela de Configurações mostra "último disparo: ontem às
18:03" e vira faixa vermelha se passar de 48h. É a única coisa que vai perceber
que parou.

#### B. Baileys é Node num sistema Python

Hoje: `Dockerfile` de uma linha útil sobre `python:3.12-slim`, um processo
(`uvicorn`), deploy que é `flyctl deploy` e nada mais.

| Forma | O que acontece | Veredito |
|---|---|---|
| **Node na mesma imagem** (Node instalado no `python:3.12-slim`, dois processos sob supervisord) | imagem de ~200 MB vira ~400+; dois runtimes para atualizar; dois logs no mesmo fluxo; `/saude` deixa de dizer se o WhatsApp está vivo | **Não.** Põe um runtime estranho dentro do artefato que carrega o prontuário |
| **Segundo app no Fly com a imagem oficial da Evolution API** (que é Baileys empacotado), falando HTTP com o BDDente pela rede privada `.internal`, autenticado por `AUTHENTICATION_API_KEY` | o `Dockerfile` do BDDente **não muda**; `flyctl deploy` continua um comando só; a Evolution sobe uma vez e é atualizada fora de banda | **É esta** |

Nota sobre a decisão: "Baileys" e "Evolution API" não são duas escolhas — a Evolution
**é** o Baileys empacotado num serviço HTTP com sessão persistida. Usar a imagem
pronta é usar Baileys sem colar Node dentro do app do prontuário. Se um dia a
Evolution atrapalhar, o `Protocol` do §11.4 deixa trocar por Baileys cru sem
reescrever a funcionalidade.

#### C. A sessão é estado com disco, e o container não tem disco

O Baileys guarda credenciais de sessão em arquivo (`creds.json` e as chaves do
Signal). O `docs/OPERACAO.md` já diz que **"o container não tem disco que sobreviva
a um restart"**, e este repositório faz **deploy automático a cada push na `main`**.
Na forma ingênua, **todo deploy desconecta o WhatsApp** e exige ler o QR de novo —
a funcionalidade quebrando sozinha toda vez que alguém corrige um botão.

Saída: **sessão no Postgres**. A Evolution API já sabe guardar sessão em
Postgres/Redis, e o banco deste projeto já tem backup, já é cifrado em repouso e já
é restaurado por `scripts/restaurar.py` — é reusar um cofre que existe em vez de
abrir um segundo. Com Evolution em app separado, a sessão vive dentro dela e o
BDDente nunca a vê, que é mais limpo ainda; a tabela abaixo só existe se um dia se
optar por Baileys cru dentro do app:

```
whatsapp_sessao
  clinica_id    PK, FK clinica
  provedor      varchar(20)
  credenciais   bytea NOT NULL     -- CIFRADA com SECRET_KEY, nunca em claro
  numero        varchar(24) NULL
  conectado_em  timestamptz NULL
  atualizado_em timestamptz
```

A sessão **é uma credencial**: cifrada em repouso com a `SECRET_KEY` (um dump
vazado não pode entregar junto o WhatsApp da clínica), nunca em log, e a
`auditoria` registra o *fato* (`CONECTAR`/`DESCONECTAR`), jamais o conteúdo — mesma
família da regra 5 do `AGENTS.md`.

#### D. LGPD: o que pode ir na mensagem e o que nunca vai

Dado de saúde é dado pessoal sensível. Uma mensagem no WhatsApp é lida na tela de
bloqueio, no ônibus, pelo marido, pela chefe. **"Consulta amanhã às 14h" é um
compromisso; "canal no dente 36 amanhã às 14h" é prontuário exposto na notificação
do celular.**

**Pode ir:** primeiro nome (ou nome completo), dia da semana e data, hora,
"amanhã"/"hoje", nome da clínica, nome da dentista, endereço, telefone da clínica.

**Nunca vai:** nome do tratamento, número do dente, região, diagnóstico, qualquer
resposta de anamnese, qualquer valor em R$, dívida ou parcela vencida, CPF, data de
nascimento, o telefone da própria paciente, o nome de qualquer outra paciente — e
**`agendamento.observacao`**.

A observação merece nome próprio: é campo de texto livre, é onde ela escreve como
escreve no papel, e **é onde a informação clínica vai vazar**, porque lá vai estar
"canal 36" ou "avaliar extração". Útil na tela, proibida na mensagem. Dinheiro fica
fora por um segundo motivo além da LGPD: mensagem com valor é cobrança, e cobrança
por WhatsApp tem regra e custo de reputação próprios.

**Onde a regra mora no código** — `app/agenda/mensagem.py`, barreira dupla:

```python
@dataclass(frozen=True)
class ContextoDaMensagem:
    """O ÚNICO caminho por onde dado chega numa mensagem de WhatsApp.

    São nove campos, todos texto, todos de agenda ou de clínica. Dado clínico
    (tratamento, dente, região, anamnese), dinheiro e documento NÃO têm campo
    aqui e por isso não têm como chegar lá — inclusive `agendamento.observacao`,
    que é texto livre e é onde a informação clínica vaza.
    LGPD: dado de saúde é dado sensível, e mensagem é lida na tela de bloqueio.
    """
    primeiro_nome: str
    nome: str
    dia: str
    dia_relativo: str
    hora: str
    clinica: str
    dentista: str
    endereco: str
    telefone_clinica: str

VARIAVEIS_PERMITIDAS = frozenset(...)   # os nomes dos nove campos acima
```

O tipo é a barreira estrutural: `renderizar()` recebe `ContextoDaMensagem`, **nunca
um `dict`** — um `dict` deixa alguém escrever `**vars(agendamento)` em 2027 e
ninguém percebe no review. A allowlist é **positiva** (o que pode), nunca negativa:
lista negativa esquece o campo que for criado depois. E vai um teste de contrato que
falha se `ContextoDaMensagem` ganhar campo fora da lista, com a LGPD escrita no
docstring para quem for alargá-la ler o motivo antes de alargar.

**Registro.** Todo envio grava linha em `auditoria` (`acao="ENVIAR"`,
`entidade="lembrete"`) e o texto integral fica em `lembrete.texto` — o que protege a
clínica se alguém disser que recebeu o que não recebeu, e que não contém dado
clínico justamente por causa da allowlist.

**Como ela pede para parar.** Toda mensagem termina com uma linha de saída. No
primeiro corte ninguém lê as respostas (§11.10), então a frase tem de ser verdadeira:
*"Se preferir não receber mais estes lembretes, é só avisar na recepção ou ligar
para (51) ...."* — e existe um botão na ficha que grava `aceita_whatsapp = false` na
hora. Prometer "responda PARAR" sem ninguém lendo é pior que não prometer. Quando
entrar o webhook (Task 19), a frase muda e o desligamento vira automático.

### 11.4 A decisão: Baileys, e o que ela obriga

**Decidido pelo dono do projeto:** Baileys (via Evolution API), não a API oficial.
Argumento dele: o volume é baixíssimo — uma clínica, poucos lembretes por dia.

O que a pesquisa diz, honestamente, incluindo o que joga contra a decisão:

- Bibliotecas como Baileys fazem engenharia reversa do protocolo do WhatsApp Web e
  se passam por um navegador vinculado à conta. Os Termos de Serviço proíbem cliente
  não oficial, sem ambiguidade. **Banimento é permanente e não há canal de apelação
  que funcione.**
- Os números que circulam em 2026 — "1 em cada 5 contas banidas em um ano",
  "ferramentas duram de 2 a 8 semanas até a detecção", "68% das empresas indianas
  relataram ao menos um ban em 12 meses" — vêm quase todos de **blogs de fornecedores
  de API oficial**, que ganham dinheiro com esse medo. A taxa real não é pública.
- O que **não** depende de fonte interessada, e é o que sustenta a decisão dele: a
  detecção descrita em todas as fontes pesa **razão de resposta baixa**, **distância
  no grafo de contatos** (mandar para estranhos) e **padrão temporal robótico**. Um
  lembrete para paciente que já é contato da clínica, em volume de 5 a 20 por dia,
  com intervalo irregular, é o perfil oposto do que a detecção procura. O risco não é
  zero, mas o volume dele é o de menor risco possível dentro da via não oficial.

Por isso a decisão é aceita **com estas quatro condições, que não são opcionais**:

1. **Número secundário, nunca o da clínica.** Um chip novo (R$ 10–20), "Consultório
   Dra. Kátia — avisos". É a única mitigação que de fato mitiga: se o número cair, a
   clínica perde um robô, não a porta da frente de 30 anos que está na fachada, no
   Google e no WhatsApp de ~500 pacientes. Custo: a mensagem precisa dizer o número
   real para responder ("não responda por aqui — ligue para (51) ...").
2. **Volume e forma humanos.** Teto de 20 mensagens/dia, intervalo **aleatório de 20
   a 90 segundos** entre elas, nunca no mesmo segundo, nunca para quem nunca falou com
   a clínica. Isso está na Task 14 como requisito, com teste.
3. **Playbook de queda em `docs/OPERACAO.md`:** como se percebe (a tela mostra
   `DESCONECTADO` e os envios falham), como se reconecta (ler o QR de novo), e o
   critério de desistir — **duas quedas em 30 dias e migra-se para a oficial**, sem
   nova discussão.
4. **O código é agnóstico desde a primeira linha.** `app/agenda/whatsapp/` expõe uma
   interface só:

   ```python
   class Provedor(Protocol):
       def estado(self) -> EstadoDaConexao: ...
       def enviar(self, *, numero: str, texto: str) -> Envio: ...   # Envio(ok, id_externo, erro)
   ```

   com três implementações: `fake.py` (testes e desenvolvimento), `evolution.py`
   (a que roda) e `oficial.py` (a saída de emergência). Qual roda é variável de
   ambiente. **Migrar depois de um banimento é mudar um segredo e reiniciar, não
   reescrever a funcionalidade.**

Para referência, se um dia a condição 3 for acionada: a API oficial custa da ordem
de **US$ 0,008 por mensagem** de categoria *utility* no Brasil — ~US$ 0,80/mês com
100 consultas, menos que os US$ 3–5 da máquina acordada que a via não oficial exige.
O que ela cobra em troca é burocracia: verificação de negócio, aprovação de template
(24–48h) e, se o número já estiver ativo no app, migração por Coexistência.

### 11.5 Schema da Fase 2

```
lembrete
  id                serial PK
  clinica_id        FK clinica     NOT NULL index
  agendamento_id    FK agendamento NOT NULL index
  tipo              tipo_lembrete  NOT NULL          -- VESPERA (só ele hoje)
  numero            varchar(24)    NULL              -- para onde foi, congelado no envio
  texto             text           NULL              -- exatamente o que saiu; NULL enquanto pendente
  modelo_id         FK modelo_mensagem NULL
  situacao          situacao_lembrete NOT NULL default 'PENDENTE'
  motivo            text           NULL              -- por que não saiu (§11.6)
  tentativas        smallint       NOT NULL default 0
  provedor          varchar(20)    NULL              -- 'evolution' | 'oficial' | 'fake'
  id_externo        varchar(80)    NULL
  agendado_para     timestamptz    NOT NULL
  enviado_em        timestamptz    NULL
  criado_em         timestamptz    NOT NULL default now()
  excluido_em       timestamptz    NULL

  UNIQUE (agendamento_id, tipo)                      -- ← a idempotência mora aqui
        name=uq_lembrete_um_por_agendamento
  INDEX ix_lembrete_fila (clinica_id, situacao, agendado_para)

enum tipo_lembrete      = VESPERA
enum situacao_lembrete  = PENDENTE | ENVIANDO | ENVIADO | FALHOU
                        | DESCARTADO | EXPIRADO | CANCELADO

modelo_mensagem
  id             serial PK
  clinica_id     FK clinica NOT NULL index
  codigo         varchar(30) NOT NULL           -- 'LEMBRETE_VESPERA'
  texto          text NOT NULL
  atualizado_por FK usuario NULL
  atualizado_em  timestamptz
  UNIQUE (clinica_id, codigo)

configuracao_clinica                          -- uma linha por clínica, colunas tipadas
  clinica_id            PK, FK clinica
  lembrete_ativo        boolean  NOT NULL default false   -- a chave geral (§11.7); nasce DESLIGADA
  lembrete_hora         time     NOT NULL default '18:00'
  lembrete_horas_antes  smallint NOT NULL default 24
  lembrete_teto_diario  smallint NOT NULL default 20
  whatsapp_provedor     varchar(20) NULL
  endereco              varchar(200) NULL                 -- variável {endereco}
  telefone_clinica      varchar(24)  NULL                 -- variável {telefone_clinica}
  atualizado_em         timestamptz

agendamento
  + avisar_avulso  boolean NOT NULL default true   -- só significa algo quando paciente_id IS NULL

paciente
  + aceita_whatsapp  boolean NULL             -- NULL = nunca perguntamos, e NULL não recebe
```

Quatro decisões de schema, cada uma com motivo:

- **`configuracao_clinica` tem colunas tipadas, não chave/valor.** Neste repositório
  o `tests/test_schema.py` afirma colunas, e o schema é a documentação. Chave/valor
  genérico é `varchar` para tudo e invisível ao teste.
- **Segredo nenhum entra em tabela.** `AUTHENTICATION_API_KEY` da Evolution vive em
  `fly secrets`, como a `SECRET_KEY`. A única exceção possível é a sessão do QR, que
  nasce em tempo de execução — e mesmo essa não existe se a Evolution guardar a
  própria sessão.
- **`lembrete_ativo` nasce `false`.** Deploy que já sai mandando mensagem para
  paciente é a definição de acidente.
- **`numero` e `texto` ficam congelados no `lembrete`.** Se ela corrigir o telefone
  depois, o registro continua dizendo para onde foi de fato. Mesma filosofia do
  prontuário: o registro guarda o que aconteceu, não o estado de agora.

### 11.6 Idempotência: no schema, não na prosa

**O que impede a mesma paciente de receber duas vezes** é `UNIQUE (agendamento_id,
tipo)`. Não é um `if`, não é um lock, não é disciplina — é o banco recusando a
segunda linha. Vale se o cron disparar duas vezes, se houver duas máquinas durante
um deploy, e se ela clicar em "enviar agora" enquanto o cron roda.

O disparo é em duas fases, e a ordem importa:

**Fase 1 — reservar (só banco, nenhuma rede).** Para cada agendamento entre
`agora + horas_antes` e o fim daquele dia, com situação `MARCADO` ou `CONFIRMADO` e
não excluído, tenta inserir um `lembrete` `PENDENTE`. **Commit.** Se o processo
morrer aqui, ninguém recebeu nada. Já nesta fase se decide quem não vai receber, e a
linha é criada assim mesmo, `DESCARTADO`, com `motivo`:

```
sem_permissao     paciente da base com aceita_whatsapp != true
sem_numero        nenhum telefone aproveitável — da ficha ou o avulso (§11.8)
avulso_recusou    avisar_avulso = false
numero_suspeito   o número existe mas não passa na régua
teto_diario       passou de lembrete_teto_diario naquele dia
```

Guardar o descarte é o que permite a tela dizer *"8 pacientes de amanhã não vão
receber: 6 sem permissão, 2 sem número"* — informação sobre a qual ela consegue agir
hoje, com a paciente na cadeira.

**Fase 2 — despachar (uma mensagem por vez).** Para cada `PENDENTE`, um
`UPDATE ... SET situacao='ENVIANDO' WHERE id=:id AND situacao='PENDENTE' RETURNING id`,
**com commit antes de tocar na rede**. Quem ganhar o `UPDATE` manda. Depois:
`ENVIADO` + `enviado_em` + `id_externo`, ou `FALHOU` + `motivo` + `tentativas += 1`.
Entre um envio e o seguinte, pausa aleatória de 20 a 90 segundos (§11.4, condição 2).

Fica uma janela impossível de fechar: a mensagem sai e o processo morre antes do
commit. A linha fica `ENVIANDO` para sempre. **Regra: `ENVIANDO` nunca é reenviado
automaticamente.** Vai para a tela como *"1 lembrete: não sei se saiu"*, para uma
pessoa decidir. A garantia escolhida é **no máximo uma vez, nunca ao menos uma
vez** — mandar duas vezes queima a paciente e é exatamente o padrão que a detecção
procura. Na dúvida, não manda.

**O lembrete cujo horário já passou.** Um lembrete só sai se ainda faltar um mínimo
para a consulta — **proposto: 6 horas**:

- Faltam 24h: sai, e o texto diz "amanhã".
- Faltam 9h (a máquina não acordou ontem): sai, e o texto diz **"hoje"** — porque
  `{dia_relativo}` é derivado da distância real no momento do envio, não da intenção
  de ontem. Um lembrete atrasado que diz a verdade ainda ajuda; um que chega tarde
  dizendo "amanhã" é pior que nenhum.
- Faltam menos de 6h, ou a consulta já passou: `EXPIRADO`, ninguém recebe. E a tela
  mostra *"3 lembretes expiraram — o disparo não rodou ontem"*, que é o alarme de
  cron morto que realmente vai ser lido.

**Desmarcou depois de reservado.** Na hora de despachar, confere-se de novo a
situação do agendamento. Desmarcou às 17h, não recebe às 18h: `CANCELADO`,
`motivo='desmarcado'`. Tem teste.

### 11.7 A chave geral: desligar o envio por completo

Requisito do dono: **um botão nas Configurações que desliga totalmente o envio.**
É `configuracao_clinica.lembrete_ativo`, e ele governa as duas fases:

- **Desligado, `reservar()` nem roda.** Nenhuma linha de `lembrete` é criada, nada
  entra em fila. `despachar()` também recusa, como segunda tranca, para o caso de
  sobrar `PENDENTE` de antes.
- **Religar não dispara acumulado.** Esta é a propriedade que importa e ela é
  consequência do desenho, não de um `if` extra: **a fila é derivada da agenda, não
  acumulada**. Ao religar, o próximo disparo olha os agendamentos das próximas
  `horas_antes` horas e reserva a partir do zero. O que ficou para trás está sob o
  corte de 6h e vira `EXPIRADO`, nunca uma enxurrada de mensagens sobre consultas
  que já aconteceram.
- **Desligar não apaga nada.** Os `lembrete` já enviados continuam no histórico —
  é registro do que aconteceu.
- **Enquanto está desligado, a agenda diz isso** numa linha discreta no topo:
  *"lembretes de WhatsApp desligados"*, com link para religar. Silêncio que parece
  funcionamento é a pior forma de desligar: ela confia que a paciente foi avisada e
  a paciente não foi.
- **Ligar e desligar geram auditoria** com `antes`/`depois`. É a configuração cuja
  mudança tem consequência para terceiros — precisa dizer quem mexeu e quando.

Diferença deliberada entre esta chave e o `Desconectar` do WhatsApp: a chave geral
para de mandar e **mantém a conexão**; `Desconectar` derruba a sessão e obriga a ler
o QR de novo. Quem quer só parar por uma semana usa a chave; quem trocou de celular
usa o `Desconectar`.

### 11.8 Telefone que não presta

O módulo `app/pacientes/telefone.py` já sabe que número ruim existe:
`parecer_incompleto()` (menos de 8 dígitos), `parecer_longo()` (mais de 11), e
`formatar()` com a regra da casa no docstring — *"nunca inventa dígito para fazer
caber"*. Os cadastros migrados carregam `telefone_incompleto` em `revisar_motivo`.

O WhatsApp é mais exigente que a tela: precisa de `55` + DDD + 8 ou 9 dígitos. Regra
nova, **no mesmo módulo, porque régua de telefone é uma só neste sistema** — e ela
vale igual para o telefone da ficha e para o `telefone_avulso`:

```
numero_para_whatsapp(numero) -> str | None
    10 ou 11 dígitos e DDD entre 11 e 99  ->  '55' + número
    qualquer outra coisa                  ->  None
```

E o que ela **não** faz, de propósito:

- **Não acrescenta o nono dígito.** Um número de 10 dígitos do cadastro de 2005 pode
  ser fixo (que não tem WhatsApp) ou celular anterior ao nono dígito. Somar um "9" é
  inventar dígito — a coisa que este módulo se recusa a fazer desde o primeiro dia.
- **Não chuta DDD.** Número de 8 dígitos de 1996 não tem DDD; supor "51" acerta em
  Porto Alegre e erra em quem se mudou.
- **Só o telefone principal.** Mandar para os três números da mesma pessoa é ruído
  para ela e é padrão de robô para a Meta.

Quem ficar de fora vira `DESCARTADO` com motivo e aparece na tela de Configurações
**com link para a ficha** — onde corrigir o telefone já tira a marca de
`revisar_motivo`. O caminho é: a tela mostra quem não vai receber → ela corrige na
ficha → no dia seguinte a pessoa recebe.

### 11.9 Tasks da Fase 2, em ordem

As tasks 10 a 16 são construídas e testadas com um **provedor de mentira**, que
escreve a mensagem no log em vez de enviar. Reserva, idempotência, expiração,
consentimento, chave geral, templates e tela ficam prontos e cobertos por teste
**sem uma mensagem real e sem o chip novo existir**.

```
Fase 5 — o encanamento (nada é enviado)
 10. Consentimento: paciente.aceita_whatsapp, agendamento.avisar_avulso, selo e botões
 11. numero_para_whatsapp() em pacientes/telefone.py
 12. Tabelas lembrete, modelo_mensagem, configuracao_clinica + migration
 13. app/agenda/mensagem.py — ContextoDaMensagem, allowlist, renderizar()

Fase 6 — o disparo (provedor de mentira)
 14. agenda/lembretes.py — reservar() e despachar()
 15. POST /tarefas/lembretes + cron interno + min_machines_running = 1
 16. Tela /configuracoes, com a chave geral

Fase 7 — o WhatsApp de verdade
 17. Evolution API como app separado no Fly + provedor evolution.py
 18. Conectar/desconectar na tela (QR)
 19. Parar de receber: botão hoje, webhook depois
 20. Operação: OPERACAO.md, playbook de queda, primeiro envio real
```

#### Task 10 — Consentimento

**Requisitos**
- [ ] `paciente.aceita_whatsapp boolean NULL` e `agendamento.avisar_avulso boolean NOT NULL default true`; migration.
- [ ] Três opções explícitas no cadastro e na edição de paciente (não um checkbox, que confunde "não marcou" com "disse não").
- [ ] No formulário do horário, ao lado do telefone avulso: `[x] avisar no WhatsApp na véspera`.
- [ ] Selo no cartão: "sem permissão de WhatsApp · perguntar" com botão de um clique que grava `true`; selo cinza `sem lembrete` para quem não tem número.
- [ ] Botão na ficha que grava `false` ("pediu para não receber").
- [ ] Auditoria com `antes`/`depois` — consentimento é justamente o que se precisa provar depois.
- [ ] Os 5.559 migrados ficam `NULL`. **Nenhum backfill, nenhum default `true`.**

**Testes**
- [ ] paciente migrado nasce `NULL` e `NULL` não recebe
- [ ] avulso com telefone e `avisar_avulso = true` recebe
- [ ] avulso sem telefone **é agendado normalmente** e não recebe
- [ ] avulso que virou paciente nasce com `aceita_whatsapp = NULL`
- [ ] gravar `true` e `false` deixa os dois lados na auditoria
- [ ] paciente de outra clínica dá 404

#### Task 11 — `numero_para_whatsapp()`

**Requisitos**
- [ ] Fica em `app/pacientes/telefone.py` — uma régua só, para ficha e avulso.
- [ ] 10 ou 11 dígitos com DDD 11–99 → `55…`; o resto → `None`.
- [ ] Não acrescenta nono dígito, não chuta DDD, não corta número longo.

**Testes**
- [ ] `'51999998888'` → `'5551999998888'`
- [ ] `'5133133087'` (10 dígitos) → `'555133133087'` — **sem** virar 11
- [ ] `'36535051'` (8 dígitos, sem DDD) → `None`
- [ ] `'32484554844055454'` (dois números colados) → `None`
- [ ] DDD implausível (`'01'`, `'00'`) → `None`
- [ ] número já com `55` na frente não ganha outro `55`

#### Task 12 — As tabelas

**Requisitos**
- [ ] Modelos conforme §11.5, em `app/agenda/models.py` — lembrete é da agenda.
- [ ] Enums criados **na migration** com `.create(bind, checkfirst=True)`, `create_type=False` no model.
- [ ] `UNIQUE (agendamento_id, tipo)` e o índice da fila.
- [ ] `configuracao_clinica` semeada com uma linha por clínica, `lembrete_ativo = false`.
- [ ] `modelo_mensagem` semeado com **um** modelo, `LEMBRETE_VESPERA`.
- [ ] `tests/test_schema.py` ganha as tabelas novas.

**Testes**
- [ ] colunas, enums, nulabilidade e os dois índices
- [ ] **dois lembretes do mesmo (agendamento, tipo) → `IntegrityError`** — o teste que justifica a constraint existir
- [ ] `upgrade`/`downgrade` limpos, enums somem no downgrade
- [ ] a semente cria configuração e modelo, e rodar a migration duas vezes não duplica

#### Task 13 — `agenda/mensagem.py`

**Requisitos**
- [ ] `ContextoDaMensagem` congelado, nove campos, docstring com o motivo LGPD.
- [ ] `VARIAVEIS_PERMITIDAS` positiva, derivada dos campos do dataclass.
- [ ] `renderizar(texto, contexto) -> str`; `validar(texto) -> list[str]` devolve as desconhecidas.
- [ ] Variável desconhecida **no envio** levanta `ModeloInvalido` — ninguém recebe texto quebrado.
- [ ] Variável válida com valor vazio: mesma coisa. *"Te espero em , amanhã"* é tão quebrado quanto.
- [ ] `de_agendamento(...)` é a única fábrica, e **não** recebe o objeto `Agendamento` inteiro — recebe os campos de que precisa. Serve igual para paciente e para avulso.

**Testes**
- [ ] renderiza os nove campos
- [ ] `{tratamento}` levanta `ModeloInvalido`
- [ ] `{endereco}` vazio levanta `ModeloInvalido`
- [ ] `{dia_relativo}` é "amanhã" a 24h e "hoje" a 9h da consulta
- [ ] horário avulso usa `nome_avulso` no `{primeiro_nome}`
- [ ] **contrato:** `ContextoDaMensagem` não tem campo fora da allowlist (falha se alguém acrescentar `observacao`, `procedimento`, `dente`, `valor`, `cpf`)
- [ ] **contrato:** `mensagem.py` não importa `clinico.models`, `financeiro.models` nem `catalogo.models`

#### Task 14 — `agenda/lembretes.py`

**Requisitos**
- [ ] `reservar(sessao, *, clinica_id, agora) -> Resumo` — fase 1 do §11.6, `agora` por parâmetro (nunca `date.today()` por dentro).
- [ ] `despachar(sessao, *, clinica_id, agora, provedor) -> Resumo` — fase 2, uma por vez.
- [ ] **As duas recusam de saída se `lembrete_ativo` for `false`** (§11.7).
- [ ] `IntegrityError` na reserva é caminho normal, não erro: `rollback` do savepoint e segue.
- [ ] Provedor injetado; `fake.py` registra o que "enviaria".
- [ ] `ENVIANDO` nunca é retomado automaticamente.
- [ ] Corte de 6h; `EXPIRADO` para o que passou.
- [ ] Reconfere a situação do agendamento antes de mandar.
- [ ] **Pausa aleatória de 20 a 90 s entre envios e teto diário** — condição 2 do §11.4.
- [ ] Auditoria por envio.

**Testes**
- [ ] rodar duas vezes seguidas manda **uma** mensagem (o teste mais importante da fase)
- [ ] reservar duas vezes não cria duas linhas
- [ ] paciente sem permissão vira `DESCARTADO/sem_permissao`
- [ ] telefone imprestável vira `DESCARTADO/sem_numero` — na ficha e no avulso
- [ ] consulta a 3h vira `EXPIRADO`; a 9h é enviada com "hoje"
- [ ] agendamento desmarcado depois de reservado vira `CANCELADO`, sem envio
- [ ] falha do provedor deixa `FALHOU` com motivo e `tentativas = 1`, e **não** reenvia sozinho
- [ ] linha em `ENVIANDO` é ignorada pela execução seguinte
- [ ] **`lembrete_ativo = false` não cria linha nenhuma e não manda nada**
- [ ] **religar depois de uma semana desligado não dispara acumulado**
- [ ] passar do teto diário vira `DESCARTADO/teto_diario`
- [ ] dado de outra clínica nunca entra

#### Task 15 — O endpoint e o gatilho

**Requisitos**
- [ ] `POST /tarefas/lembretes` com `X-Tarefa-Token` e `hmac.compare_digest`; token errado → 404.
- [ ] Responde contadores em JSON; **nunca nome de paciente no corpo** (isso vai para log de terceiro).
- [ ] `TAREFAS_TOKEN` em `app/config.py` e `fly secrets`.
- [ ] `min_machines_running = 1` no `fly.toml`, com o custo escrito no `OPERACAO.md`.
- [ ] Cron interno no container + o endpoint como gatilho manual/externo de reserva.

**Testes**
- [ ] sem token → 404; token errado → 404; token certo → 200 com contadores
- [ ] chamar duas vezes seguidas não duplica envio
- [ ] a resposta não contém nome nem telefone
- [ ] não exige sessão (é máquina que chama)

#### Task 16 — Tela `/configuracoes`

Detalhada no §12. Requisitos e testes lá.

#### Task 17 — Evolution API de verdade

**Requisitos**
- [ ] `app/agenda/whatsapp/` com o `Protocol` do §11.4 e `fake.py` já pronto.
- [ ] `evolution.py` falando com o app separado pela rede privada `.internal`.
- [ ] `AUTHENTICATION_API_KEY` em `fly secrets`; escolha do provedor por variável de ambiente, padrão `fake`.
- [ ] Erro do provedor vira `Envio(ok=False, erro=...)`; **nunca sobe exceção que derrube o disparo inteiro** — uma paciente com número ruim não pode impedir as outras sete.
- [ ] Timeout curto e explícito em toda chamada de rede.
- [ ] `Dockerfile` do BDDente **inalterado**.

**Testes**
- [ ] o provedor é escolhido pela configuração, e o padrão é `fake`
- [ ] falha de rede vira `FALHOU`, não exceção
- [ ] uma falha no meio da fila não impede as seguintes
- [ ] nenhum teste da suíte toca a rede de verdade (contrato)

#### Task 18 — Conectar e desconectar (QR)

**Requisitos**
- [ ] Botão "Conectar" gera o QR e o mostra; renova sozinho enquanto a tela está aberta.
- [ ] Sessão nunca em log, nunca em auditoria; se ficar no BDDente, cifrada com `SECRET_KEY`.
- [ ] Estado visível: `CONECTADO (número) · DESCONECTADO · AGUARDANDO QR`, com a data do último envio bem-sucedido.
- [ ] "Desconectar" **remove** a credencial — é o único caso em que remover é o certo: credencial revogada é lixo, e a regra do `excluido_em` é sobre dado de paciente, não sobre segredo. Fica anotado como exceção consciente, e o fato vai para a auditoria.
- [ ] Faixa vermelha na agenda quando cai, com link para reconectar.

**Testes**
- [ ] a sessão nunca aparece em claro no banco
- [ ] auditoria registra conectar/desconectar **sem** o payload
- [ ] desconectado, o disparo não tenta enviar: tudo vira `FALHOU/desconectado`
- [ ] a faixa aparece na agenda quando o estado é desconectado

#### Task 19 — Parar de receber

**Requisitos**
- [ ] Botão na ficha já existe desde a Task 10; aqui entra o caminho automático.
- [ ] Webhook de resposta: "PARAR", "SAIR", "CANCELAR", sem caixa e sem acento → `aceita_whatsapp = false` + auditoria.
- [ ] Só então o rodapé da mensagem passa a dizer "responda PARAR".
- [ ] O webhook **não** guarda o conteúdo das respostas — lê e descarta. Guardar conversa de paciente é abrir um prontuário paralelo que ninguém pediu.

**Testes**
- [ ] "parar", "PARAR", "Parar." e "sair" desligam
- [ ] "obrigada!" não desliga
- [ ] desligado não recebe no dia seguinte
- [ ] o corpo da resposta não é gravado em lugar nenhum

#### Task 20 — Operação

**Requisitos**
- [ ] `docs/OPERACAO.md`: o chip novo, o custo do `min_machines_running = 1`, como conferir se rodou, e o **playbook de queda** (§11.4).
- [ ] `AGENTS.md`: a regra da allowlist de variáveis, junto das invioláveis.
- [ ] Primeiro envio real **para o número dela mesma**, com um agendamento de teste, antes de qualquer paciente.
- [ ] Ligar a chave geral é o último passo, e é ela quem liga.
- [ ] `ruff` e `pytest` limpos, saída colada.

### 11.10 Limites conscientes da Fase 2

- **Um lembrete só, o da véspera.** Sem confirmação na marcação, sem "2h antes", sem
  aniversário, sem recall de limpeza. O encanamento serve para todos; o primeiro
  corte manda um.
- **Ninguém lê as respostas no primeiro corte.** Por isso a mensagem não pede
  confirmação — pede que ligue se não puder vir.
- **Sem mídia, sem botão, sem link de confirmar.**
- **Sem reenvio automático de falha.** Falhou, aparece na tela, ela liga. Robô
  insistindo é robô banido.
- **No máximo uma vez, nunca ao menos uma vez.**
- **Sem relatório de entrega e leitura.**
- **Só o telefone principal**, e só quem autorizou — que no começo é quase ninguém, e
  isso é a lei funcionando, não um bug.
- **`min_machines_running` passa a 1**, e é custo direto da escolha por Baileys.

---

## 12. Configurações: onde a tela mora

**Uma tela própria em `/configuracoes`, sem item na navegação principal**, alcançada
por um link no rodapé da lateral (embaixo do crachá, ao lado do "Sair") e pelo aviso
da agenda quando a conexão cai.

A lateral hoje tem **seis** itens — Pacientes, Odontograma, Atendimentos,
Tratamentos, Financeiro, Recebimentos — e a Agenda faz **sete**. As alternativas e
por que caem:

| Alternativa | Por que não |
|---|---|
| **Oitavo item no menu** | O menu lateral é a lista das coisas que ela faz **com paciente**. Configuração é usada duas vezes por ano — quando o WhatsApp cai. Oito itens é onde uma barra lateral deixa de ser lida e passa a ser varrida |
| **Dentro de `/perfil`** | `/perfil` é sobre *a pessoa logada*: nome, senha, sessões. O WhatsApp é *do consultório*. Misturar faz a tela de perfil crescer sem fim |

E o argumento decisivo: **configuração não se acha pelo menu, se acha pelo
problema.** Quando o WhatsApp cai, o caminho não é ela lembrar que existe uma aba; é
a agenda mostrar a faixa vermelha *"o WhatsApp desconectou — reconectar"* que leva
direto lá.

### O que a tela tem

```
┌──────────────────────────────────────────────────────────────────┐
│  Configurações                                                   │
│                                                                  │
│  ── WhatsApp ──────────────────────────────────────────────────  │
│   ● Conectado como (51) 99999-9999                               │
│     Enviando pelo WhatsApp conectado por QR (não oficial)        │
│     Último envio: hoje às 18:03                                  │
│                          [ Ler QR de novo ]  [ Desconectar ]     │
│                                                                  │
│  ── Lembretes ─────────────────────────────────────────────────  │
│   ( ) LIGADO      (•) DESLIGADO   ← a chave geral                │
│       Desligado, ninguém recebe nada. Religar não manda o que    │
│       ficou para trás: a fila é a agenda de amanhã, não um saco  │
│       de mensagens acumuladas.                                   │
│                                                                  │
│   Disparo às [ 18:00 ]   Antecedência: 24 h   Teto: 20/dia       │
│   Último disparo: ontem às 18:03  ✓                              │
│                                                                  │
│   Próximo disparo — 12 consultas amanhã:                         │
│     8 vão receber                                                │
│     3 sem permissão de WhatsApp   → ver quem                     │
│     1 sem número aproveitável     → ver quem                     │
│                              [ Enviar agora os de amanhã ]       │
│                                                                  │
│  ── Texto da mensagem ─────────────────────────────────────────  │
│   [ editor do modelo, variáveis e prévia — §13 ]                 │
│                                                                  │
│  ── Últimos envios ────────────────────────────────────────────  │
│   28/08 18:03  MARIA SILVA      enviado                          │
│   28/08 18:02  JÚLIA PENA       falhou — número sem WhatsApp     │
│   ...                                            (50 últimos)    │
│                                                                  │
│  ── Consultório ───────────────────────────────────────────────  │
│   Endereço [ ................ ]   Telefone [ ............... ]   │
│   (usados nas variáveis {endereco} e {telefone_clinica})         │
└──────────────────────────────────────────────────────────────────┘
```

Seis requisitos que não são decoração:

- **A chave geral é o primeiro controle do bloco**, com o texto explicando que
  religar não dispara acumulado. Chave que a pessoa tem medo de mexer não é chave.
- **A tela diz por qual caminho está enviando**, em uma linha. Quem corre o risco de
  perder o número tem direito de ver na tela qual risco está correndo.
- **"Enviar agora os de amanhã"** é o cinto de segurança quando o cron falha. É
  idempotente por construção (§11.6), então clicar duas vezes não manda duas vezes —
  e é justamente por isso que pode existir sem medo.
- **Quem não vai receber é uma lista com link para a ficha.** É a única parte da tela
  sobre a qual ela consegue agir hoje.
- **"Último disparo" vira faixa vermelha depois de 48h.** É o monitor do cron, e é de
  graça.
- **Nenhum segredo é exibido nem editável na tela.**

### Task 16 — requisitos e testes

**Requisitos**
- [ ] `GET /configuracoes` e `POST /configuracoes` (formulário, 303 de volta), com `usuario_atual`.
- [ ] Link no rodapé da lateral, **sem** item na navegação; `tests/test_layout.py` afirma as duas coisas.
- [ ] A chave geral grava `lembrete_ativo` e vai para a auditoria.
- [ ] Faixa na agenda quando desconectado, quando o último disparo passou de 48h, e linha discreta quando a chave está desligada.
- [ ] `POST /configuracoes/enviar-agora` chama o mesmo `reservar`/`despachar` do cron.
- [ ] A prévia da mensagem usa **dados de exemplo**, nunca uma paciente real — prévia é tela, e tela com nome de paciente vira print no grupo da família.

**Testes**
- [ ] a tela abre, e **não** acrescenta item na navegação
- [ ] o link para `/configuracoes` está no rodapé da lateral
- [ ] ligar/desligar grava e aparece na auditoria com `antes`/`depois`
- [ ] com a chave desligada, "Enviar agora" não manda nada
- [ ] a agenda mostra a linha "lembretes desligados" quando desligado
- [ ] "Enviar agora" duas vezes seguidas manda uma vez só
- [ ] a lista de quem não recebe traz o motivo e o link para a ficha
- [ ] disparo velho vira faixa vermelha na agenda
- [ ] nenhum segredo (token, chave, sessão) aparece no HTML
- [ ] sem sessão, redireciona para o login

---

## 13. Templates de mensagem

**Quantos existem: um.** `LEMBRETE_VESPERA`. Pelo mesmo critério que deixou
`procedimento_id` fora da agenda no primeiro corte: modelo que nada dispara é peso
morto. O de confirmação na marcação é o próximo, e o encanamento já o comporta sem
schema novo.

Ele vive em `modelo_mensagem` (tabela), não numa constante, porque o requisito é que
**ela** edite o texto — e o texto dela vai ser melhor que o meu.

Texto inicial semeado pela migration:

```
Oi {primeiro_nome}! Passando para lembrar do seu horário
{dia_relativo}, {dia}, às {hora}, com a {dentista}.

{clinica} — {endereco}
Se não puder vir, me avise: {telefone_clinica}
```

### As variáveis

| Variável | Vale | De onde vem |
|---|---|---|
| `{primeiro_nome}` | Maria | `paciente.nome` ou `nome_avulso`, primeira palavra |
| `{nome}` | MARIA SILVA SANTOS | `paciente.nome` ou `nome_avulso` |
| `{dia}` | quinta-feira, 28 de agosto | `agendamento.dia` |
| `{dia_relativo}` | amanhã · hoje | distância real **no momento do envio** |
| `{hora}` | 14:00 | `agendamento.inicio` |
| `{clinica}` | Consultório Dra. Kátia | `clinica.nome` |
| `{dentista}` | Dra. Kátia | `usuario.nome` |
| `{endereco}` | Rua X, 100 — Bairro | `configuracao_clinica.endereco` |
| `{telefone_clinica}` | (51) 3333-3333 | `configuracao_clinica.telefone_clinica` |

`{primeiro_nome}` é o padrão de propósito: *"MARIA DA SILVA SANTOS, seu horário"*
soa como cobrança de banco. `{dia_relativo}` é calculado no envio, não na reserva —
é o que faz o lembrete atrasado dizer "hoje" em vez de mentir "amanhã".

### Variável que não existe

Duas situações, dois destinos, e eles não podem ser o mesmo:

**1. Ao salvar o modelo — recusa na entrada.** O formulário valida e volta com a
mensagem: *"não existe a variável `tratamento`. As que existem são: primeiro_nome,
nome, dia, dia_relativo, hora, clinica, dentista, endereco, telefone_clinica."* É
aqui que o erro custa menos, e é a única barreira que impede alguém de escrever
`{observacao}` achando que vai funcionar.

**2. No envio — o lembrete não sai.** Se mesmo assim sobrar um `{x}` desconhecido
(modelo gravado por uma versão anterior, variável removida do código):
`situacao = FALHOU`, `motivo = 'modelo_invalido'`, **ninguém recebe**, e a tela mostra
*"o texto da mensagem tem um erro"* com link para corrigir. As duas alternativas são
piores: mandar `Olá {primeiro_nome}` para a paciente é a assinatura do robô malfeito,
e apagar o marcador em silêncio produz frase truncada sem ninguém saber por quê.
**A clínica é a cara que aparece na mensagem.**

Variável **válida mas vazia** cai na mesma regra — *"Te espero em , amanhã"* é tão
quebrado quanto. Uma regra só, fácil de testar, fácil de lembrar.

### O que nunca pode virar variável

Nome do tratamento · número do dente · região · diagnóstico · qualquer resposta de
anamnese · valor em R$ · dívida ou parcela vencida · CPF · data de nascimento · o
telefone da própria paciente · nome de qualquer outra paciente ·
**`agendamento.observacao`**.

A observação é a que precisa ser dita em voz alta: é texto livre, é onde ela escreve
como escreveria no papel, e é onde vai estar "canal 36" ou "avaliar extração".

**Onde a regra mora, para não se perder com o tempo** — `app/agenda/mensagem.py`, e
são três camadas:

1. **O tipo.** `renderizar()` recebe `ContextoDaMensagem`, dataclass congelado de
   nove campos de texto — **nunca um `dict`**. Não havendo campo, não há caminho.
2. **A allowlist positiva**, derivada dos campos do dataclass. Positiva, não negativa:
   lista do que é proibido esquece o campo criado em 2027.
3. **O teste de contrato**, que falha se `ContextoDaMensagem` ganhar campo fora da
   lista, com a razão LGPD no docstring — para quem for alargá-la ler o motivo
   **antes** de alargar. Mais um teste que falha se `mensagem.py` importar
   `clinico.models`, `financeiro.models` ou `catalogo.models`.

E uma linha em `AGENTS.md`, junto das regras que não se quebram:

> **Mensagem para paciente só carrega o que está em
> `agenda/mensagem.py::ContextoDaMensagem`.** Nome, dia, hora, dados da clínica.
> Nunca tratamento, dente, valor, documento nem a observação do horário — dado de
> saúde é dado sensível, e mensagem é lida na tela de bloqueio.

---

## 14. Perguntas que sobraram para a Dra. Kátia

Nenhuma bloqueia o começo — as Tasks 10 a 16 rodam com provedor de mentira.

7. **Qual número manda os lembretes?** O plano exige um chip novo, só do robô
   (§11.4, condição 1). Falta comprar e dizer qual é.
8. **Que horas o disparo roda?** Proposto: 18h.
9. **O texto da primeira mensagem** — ela escreve, não eu.
10. **Como perguntar a autorização às ~500 ativas?** O plano só oferece um caminho:
    consulta a consulta. Uma mensagem única perguntando "posso mandar mensagem?" já é
    a mensagem que não podia mandar.

---

## 15. Fontes sobre banimento

A decisão por Baileys foi tomada com estas leituras na mesa:

- [Why Cheap WhatsApp Bots Get Your Number Banned — SporeSec](https://sporesec.com/en/blog/whatsapp-unofficial-api-ban-risk)
- [What Is Baileys? WhatsApp Library Guide (2026)](https://whatsapp.checkleaked.cc/blog/what-is-baileys)
- [WhatsApp Automation Ban Risk 2026 — Kraya](https://blog.kraya-ai.com/whatsapp-automation-ban-risk)
- [WhatsApp API and Automation 2026 — Zylos Research](https://zylos.ai/research/2026-01-26-whatsapp-api-automation/)
- [baileys-antiban — padrões de envio humanos](https://github.com/kobie3717/baileys-antiban)

**Ressalva honesta:** a maioria das fontes que quantifica banimento são blogs de
fornecedores de API oficial, cujo incentivo comercial é assustar. Os números ("1 em
5 em um ano", "2 a 8 semanas até a detecção") não são verificáveis. O que não depende
do incentivo é o resto, e é o que sustenta tanto o risco quanto a decisão: o ToS
proíbe cliente não oficial, não há apelação — e a detecção descrita pesa razão de
resposta, distância no grafo de contatos e ritmo robótico, três coisas em que um
lembrete para paciente conhecida, em volume baixo e com intervalo irregular, se sai
bem.
