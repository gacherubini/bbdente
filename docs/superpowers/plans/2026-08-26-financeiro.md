# BDDente Financeiro — Plano de Implementação

**Goal:** Dar ao BDDente o lado do dinheiro — preço visível no catálogo, edição de
paciente, de tratamento e de lançamento, os 30 anos de caixa do Dentalis migrados,
e uma tela de Financeiro com números e gráficos por período.

**Spec:** [`docs/superpowers/specs/2026-08-26-financeiro-design.md`](../specs/2026-08-26-financeiro-design.md)

**Dicionário dos dados legados:** [`dados_extraidos/DICIONARIO.md`](../../../dados_extraidos/DICIONARIO.md) — obrigatório antes da Task 6.

---

## Global Constraints

Valem as mesmas do plano do MVP e do [`AGENTS.md`](../../../AGENTS.md) — não as
repito aqui. As que este trabalho tenta com mais força:

- **Nunca `DELETE`.** Editar preço não sobrescreve preço: grava linha nova em
  `preco` com `vigente_desde`. Editar paciente ou lançamento grava `antes` e
  `depois` na auditoria.
- **Fronteira de módulo.** `financeiro` nunca faz `JOIN` em `lancamento` nem em
  `paciente`. Pede a `clinico.service` e a `pacientes.service`.
- **TDD.** Teste primeiro, vê falhar, então implementa.
- **Sem biblioteca de gráfico.** SVG escrito à mão, como o odontograma.
- **Dinheiro é `Decimal`/`Numeric(12,2)`.** Nunca `float` — nem no Python, nem no
  JavaScript dos gráficos, onde o valor chega já formatado ou em centavos
  inteiros.

---

## Ordem das tasks

```
Fase 1  (não depende de migração — entrega valor no mesmo dia)
  1. Preço na tela de Tratamentos
  2. Editar tratamento e preço
  3. Editar paciente
  4. Editar lançamento

Fase 2  (o caixa de 30 anos)
  5. Tabela parcela + migration
  6. Migração do ARQFAT + conferência bloqueante

Fase 3  (o módulo)
  7. financeiro/service.py — as agregações
  8. Tela do Financeiro: números do período + lista de cobrança
  9. Gráficos em SVG
 10. Registrar recebimento

Fase 4
 11. Desambiguar "em aberto", documentar, carregar em produção
```

---

# Fase 1 — O que o dado já permite

### Task 1: Preço na tela de Tratamentos

**Por quê:** os 606 preços já estão no banco desde a migração do MVP; a tela
simplesmente não os lê. É o menor caminho entre o pedido e a tela.

**Requisitos**

- [ ] `catalogo/service.py` ganha `precos_por_procedimento(sessao, *, clinica_id)`
      devolvendo `{procedimento_id: [(convenio_nome, valor)]}` — **uma consulta
      agregada para o catálogo inteiro**, nunca uma por linha da tabela.
- [ ] Só o preço vigente: `vigente_desde <= hoje`, o mais recente por
      (procedimento, convênio).
- [ ] `arvore()` passa a devolver o preço particular junto de cada procedimento.
- [ ] `tratamentos.html` ganha coluna **Preço**, com o valor particular e, quando
      há mais convênios, um `<details>` "+N convênios".
- [ ] Procedimento sem preço mostra `—`, não `R$ 0,00`. São coisas diferentes:
      "não tem tabela" ≠ "é de graça".

**Testes**

- [ ] preço vigente vence preço antigo do mesmo par procedimento×convênio
- [ ] preço com `vigente_desde` no futuro não aparece
- [ ] procedimento sem preço nenhum não quebra a tela e mostra `—`
- [ ] a tela inteira do catálogo não dispara consulta por linha (contar queries)
- [ ] tratamento de outra clínica não aparece

---

### Task 2: Editar tratamento e preço

**Requisitos**

- [ ] `GET /tratamentos/{id}` — tela de edição: nome, categoria, onde costuma ser,
      regiões sugeridas, ativo/inativo.
- [ ] `POST /tratamentos/{id}` — grava com auditoria `antes`/`depois`.
- [ ] Na mesma tela, preço por convênio. Salvar preço **insere** linha em `preco`
      com `vigente_desde = hoje`; nunca faz `UPDATE`.
- [ ] Preço igual ao vigente não grava linha nova (senão a tabela vira lixo de
      cliques repetidos).
- [ ] Inativar tratamento não o apaga: ele some das listas novas e continua
      desenhado no histórico de quem já o recebeu.

**Testes**

- [ ] editar nome deixa `antes` e `depois` na auditoria
- [ ] trocar preço cria linha nova e mantém a antiga
- [ ] salvar o mesmo preço duas vezes não cria segunda linha
- [ ] inativar some da árvore mas o lançamento histórico continua legível
- [ ] editar tratamento de outra clínica dá 404

---

### Task 3: Editar paciente

**Requisitos**

- [ ] `GET/POST /pacientes/{id}/editar`: nome, telefones, nascimento, convênio.
- [ ] Telefone passa pelo **mesmo** `pacientes/telefone.py` do cadastro e da
      migração. Uma régua só.
- [ ] **Corrigir tira a marca:** se `revisar_motivo` tinha `telefone_incompleto` e
      o telefone novo está completo, a marca sai. Marca que não sai nunca é marca
      que ninguém olha.
- [ ] Auditoria com `antes`/`depois`.
- [ ] Não expõe `codigo_legado` para edição — é a chave do histórico do Dentalis.

**Testes**

- [ ] editar nome grava auditoria com os dois lados
- [ ] telefone corrigido remove a marca; telefone ainda ruim mantém
- [ ] nome vazio é recusado
- [ ] telefone novo entra marcado quando estranho, como na migração
- [ ] paciente de outra clínica dá 404

---

### Task 4: Editar lançamento

**Requisitos**

- [ ] `clinico/service.py` ganha `editar_lancamento(...)`: valor, status, data e
      observação. **Não** muda dente, região nem procedimento — trocar o alvo é
      excluir (lógico) e lançar de novo.
- [ ] Mudar de planejado para realizado move a data para `data_realizada`, e o
      contrário devolve para `data_planejada`. Uma data só existe por vez.
- [ ] `PATCH /api/lancamento/{id}` devolve o estado novo do odontograma.
- [ ] Cada linha do histórico na tela do odontograma vira editável.

**Testes**

- [ ] editar valor grava auditoria com `antes`/`depois`
- [ ] virar realizado move a data de planejada para realizada
- [ ] voltar para planejado devolve a data
- [ ] editar lançamento excluído dá 404
- [ ] editar lançamento de outra clínica dá 404
- [ ] valor negativo é recusado

---

# Fase 2 — O caixa de 30 anos

### Task 5: Tabela `parcela`

**Requisitos**

- [ ] `app/financeiro/models.py` com `Parcela` conforme a §4.2 da spec.
- [ ] `clinica_id` e `paciente_id` obrigatórios, ambos indexados; `excluido_em`.
- [ ] Índice em `(clinica_id, pago_em)` e em `(clinica_id, vencimento)` — são os
      dois eixos de toda consulta do módulo.
- [ ] Migration Alembic `0003_parcela`, gerada por autogenerate.
- [ ] `saldo` é propriedade Python derivada, **não** coluna.

**Testes**

- [ ] `tests/test_schema.py` ganha a tabela: colunas, índices e nulabilidade
- [ ] saldo = cobrado − pago, inclusive quando pago é maior (saldo negativo é
      crédito do paciente, e existe: 112 linhas no extrato)
- [ ] `upgrade` e `downgrade` rodam limpos

---

### Task 6: Migração do `ARQFAT`

**Por quê:** 28.244 parcelas, 5.340 pacientes, nenhum órfão. É o único registro de
quanto dinheiro entrou no consultório em 30 anos.

**Requisitos**

- [ ] `migracao/financeiro.py`, no padrão dos outros: lê o extrato imutável,
      escreve, e a conferência decide.
- [ ] `CODICLIE` resolve pelo `codigo_legado` do paciente. **Zero órfãos
      esperados** — se aparecer um, aborta; não inventa paciente.
- [ ] `DTPAGTO` vazio → `pago_em = None`, `valor_pago = 0`.
- [ ] **21 linhas com data impossível** (ano `0200`, `9200`): entram com a data
      preservada como veio e `revisar_motivo = ['data_impossivel']`. Preservar e
      marcar — nunca chutar o século.
- [ ] `CODTPAG` traduz por `ARQTPAG`; `'00'` (28.234 linhas) vira `None`, não a
      string `'00'`.
- [ ] `codigo_legado` = `CODICLIE|PARCELA|DTVENCTO`, para reconciliar depois.
- [ ] Conferência bloqueante com os seis números da §4.3 da spec.
- [ ] `migracao/conferencia.py` e `scripts/restaurar.py` ganham os mínimos novos.

**Testes** (rodam só com o extrato presente, como os outros de `tests/migracao/`)

- [ ] traz exatamente 28.244 parcelas
- [ ] soma de `valor_cobrado` = R$ 5.808.797,26, ao centavo
- [ ] soma de `valor_pago` = R$ 2.378.315,73, ao centavo
- [ ] 7.546 parcelas sem pagamento
- [ ] 5.340 pacientes distintos, nenhum órfão
- [ ] as 21 linhas de data impossível entram marcadas, e nenhuma outra
- [ ] `CODTPAG = '00'` vira `None`
- [ ] a conferência **reprova** quando falta parcela (o teste que justifica a
      conferência existir)
- [ ] rodar a migração duas vezes não duplica

---

# Fase 3 — O módulo

### Task 7: `financeiro/service.py`

**Requisitos**

- [ ] `resumo(sessao, *, clinica_id, de, ate) -> Resumo` com os quatro números:
      recebido, produzido, a receber, tratamentos.
- [ ] **Produzido e tratamentos vêm de `clinico.service`**, não de `JOIN`.
      Adicionar lá `producao(sessao, *, clinica_id, de, ate)`.
- [ ] `recebido_por_mes(... , ano)` — 12 pontos, e os 12 do ano anterior.
- [ ] `producao_por_dia(..., ano, mes)`.
- [ ] `producao_por_categoria(...)` e `producao_por_convenio(...)` — para as
      pizzas; vêm de `clinico`/`catalogo`.
- [ ] `a_receber(..., desde)` — lista de cobrança, parcelas vencidas com saldo.
- [ ] Toda agregação é **uma consulta**. Nada de laço em Python sobre 28 mil
      linhas.
- [ ] Corte em **1995**: nada anterior entra nos gráficos (Cruzeiro/URV).

**Testes**

- [ ] cada número soma o que promete e ignora o que não é do período
- [ ] parcela excluída logicamente não conta
- [ ] pagamento parcial conta no "recebido" pelo que entrou, e o saldo continua
      em "a receber"
- [ ] período sem movimento devolve zero, não erro
- [ ] dado de outra clínica nunca entra
- [ ] mês a mês devolve 12 posições mesmo com meses vazios

---

### Task 8: Tela do Financeiro

**Requisitos**

- [ ] `GET /financeiro` — o item do menu deixa de ser "em breve".
- [ ] Seletor de período: mês (padrão, o corrente) e ano, com navegação.
- [ ] Os quatro números em cartões, com o rótulo dizendo o que cada um é.
- [ ] Lista de cobrança abaixo, **filtrada nos últimos 24 meses por padrão**, com
      o total histórico visível mas fora do caminho.
- [ ] Mês corrente vazio não é erro: a tela diz "nada registrado neste mês ainda"
      e oferece o ano anterior — é o estado real hoje.

**Testes**

- [ ] a tela abre, marca a aba, e mostra os quatro rótulos
- [ ] mês vazio mostra o aviso em vez de quatro zeros mudos
- [ ] a lista de cobrança respeita o corte de 24 meses
- [ ] sem sessão, redireciona para o login

---

### Task 9: Gráficos em SVG

**Requisitos**

- [ ] `app/static/graficos.js`: `barras()` e `pizza()`, sem biblioteca.
- [ ] O servidor manda os dados prontos em `/api/financeiro/...`; o JavaScript
      **não calcula dinheiro** — só desenha. Mesma regra do odontograma.
- [ ] Barras mensais com o ano anterior em cinza atrás.
- [ ] Barras diárias do mês.
- [ ] Duas pizzas: produção por categoria e por convênio, com legenda e
      percentual. Fatia menor que 3% cai em "outros".
- [ ] Acessível: cada gráfico tem `role="img"` e um `aria-label` que diz o número,
      além de uma tabela equivalente escondida — gráfico que só existe em pixel
      exclui quem usa leitor de tela e some quando o JS falha.
- [ ] Cores: os tokens do BDDente, sem paleta nova.

**Testes**

- [ ] contrato: `graficos.js` não contém formatação de moeda nem soma de valores
- [ ] o endpoint devolve 12 pontos com meses vazios em zero
- [ ] a tabela equivalente traz os mesmos números do gráfico

---

### Task 10: Registrar recebimento

**Requisitos**

- [ ] `POST /financeiro/recebimento`: valor, data, forma de pagamento,
      observação, paciente.
- [ ] Cria `parcela` já quitada (`numero` vazio, `vencimento` = data).
- [ ] Quitar parcela existente é a mesma tela, com valor pré-preenchido pelo
      saldo; pagar menos que o saldo é **pagamento parcial** e mantém o resto em
      aberto.
- [ ] Botão também na tela do paciente.
- [ ] Auditoria em toda escrita.

**Testes**

- [ ] recebimento novo entra quitado e aparece no "recebido" do mês
- [ ] pagamento parcial deixa saldo e mantém a parcela na cobrança
- [ ] valor zero ou negativo é recusado
- [ ] data no futuro é recusada (recebimento é fato, não promessa)
- [ ] auditoria registra quem recebeu

---

# Fase 4 — Fechamento

### Task 11: Desambiguar, documentar, carregar

**Requisitos**

- [ ] Renomear na lista de pacientes: **"Em aberto" → "A fazer"** (tratamento
      planejado). No financeiro, **"A receber"** (feito e não pago). O furo 5 da
      spec vira texto de tela.
- [ ] `AGENTS.md`: módulo `financeiro`, tabela `parcela`, e os furos do dado.
- [ ] `docs/MIGRACAO.md`: a etapa nova e os números da conferência.
- [ ] `docs/OPERACAO.md`: como carregar as parcelas em produção — migrar local,
      backup, `fly proxy`, restaurar, conferir contagem.
- [ ] Carregar em produção e conferir os números contra o extrato.

**Testes**

- [ ] a lista de pacientes não diz mais "Em aberto"
- [ ] suíte inteira verde e `ruff` limpo antes do deploy

---

## Perguntas que ficam para a Dra. Kátia

Não bloqueiam nada — o dado entra preservado de qualquer forma:

1. **Dívida de 1996 ainda é dívida?** São R$ 3,4 milhões em aberto acumulados em
   30 anos. Se ela considera perdido, cabe um "baixar como perdido" que marca sem
   apagar.
2. **Pagamento parcial** aparece no mês do último pagamento (o Dentalis não
   guardava as datas intermediárias). Serve para o gráfico mensal do histórico, ou
   o histórico antigo deve aparecer só por ano?
