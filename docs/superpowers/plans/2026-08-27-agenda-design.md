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

**Em desenho.** Requisitos já dados pelo dono do projeto: lembrete 24h antes para quem tem horário marcado; conexão do WhatsApp da própria dentista via Baileys ou Evolution API; **a conexão fica numa tela de Configurações**, para ela conectar e reconectar sozinha; **os textos das mensagens são templates editáveis por ela**.

Quatro coisas precisam estar resolvidas no papel antes de escrever qualquer linha, e nenhuma é detalhe:

1. **A máquina dorme.** `auto_stop_machines = "suspend"` e `min_machines_running = 0` no `fly.toml`. Um lembrete que precisa disparar às 18h de terça não dispara sozinho numa máquina suspensa.
2. **Baileys e Evolution não são API oficial.** Automatizam o WhatsApp Web com o número real. O risco concreto é o número do consultório ser banido — e é por ele que as pacientes acham a clínica.
3. **LGPD.** "Consulta amanhã às 14h" é uma coisa; "canal no dente 36" é outra. Precisa estar definido o que pode e o que nunca pode virar variável de template, e onde essa regra mora no código.
4. **Reenvio e idempotência.** O que impede a mesma paciente de receber duas vezes, e o que acontece com um lembrete cujo horário já passou quando o processo finalmente roda. Isso é schema, não prosa.

Mais: **sessão do Baileys é estado com disco** (o container do Fly não tem disco que sobreviva a restart — ver `docs/OPERACAO.md`), e **Baileys é Node num sistema Python**, o que significa um segundo runtime na imagem ou um segundo serviço.

A decisão entre API oficial e não oficial é do dono do projeto, não do plano.
