# BDDente — Financeiro, preços e edição

**Data:** 2026-08-26
**Status:** spec para virar plano de implementação
**Origem:** pedido do Guilherme — preço por tratamento, módulo financeiro com
relatórios e gráficos (inclusive dos meses antigos), edição de paciente e edição
de tratamento.

---

## 1. O que este documento resolve

Quatro pedidos que se cruzam num ponto só: **dinheiro**.

1. **Preço de cada tratamento** na tela de Tratamentos.
2. **Módulo financeiro** com relatórios mês a mês e gráficos — barras, linhas e
   pizza — cobrindo também o histórico antigo.
3. **Edição de paciente** (hoje o MVP só lê e busca).
4. **Edição de tratamento**, incluindo o valor.

---

## 2. O que já existe, e o que eu descobri no extrato

Antes de decidir qualquer coisa eu fui olhar o dado. Três achados mudam o
desenho:

### 2.1 O preço já está no banco — a tela é que não mostra

A tabela `preco` (`procedimento_id` × `convenio_id` × `valor` × `vigente_desde`)
existe desde o MVP e tem **606 linhas migradas** dos 51 arquivos `ARQSE###` do
Dentalis, um por convênio. A tela de Tratamentos tem até um campo de valor no
formulário de cadastro — mas a **tabela ao lado não exibe preço nenhum**.

Ou seja: não é migração, é tela. Trabalho pequeno, valor imediato.

### 2.2 Existe um livro-caixa de 30 anos que a migração não trouxe

`ARQFAT` — **28.244 parcelas**, uma linha por parcela de contas a receber.
Nenhuma delas foi migrada. É o registro real de dinheiro do consultório:

| Campo do Dentalis | O que é |
|---|---|
| `CODICLIE` | o paciente — **0 órfãos**, 5.340 pacientes distintos |
| `DTVENCTO` | vencimento |
| `ORIGINAL` | quanto foi cobrado — soma **R$ 5.808.797,26** |
| `DTPAGTO` | quando pagou (vazio = nunca pagou: 7.546 linhas) |
| `VALORPAG` | quanto entrou de fato — soma **R$ 2.378.315,73** |
| `VALORREC` | valor devido corrigido |
| `PARCIAL` | `'S'` quando o pagamento foi parcial |
| `JUROS`, `MULTA`, `DESCONTO` | ajustes aplicados |
| `PARCELA` | `01/01`, `01/03`… |

**A prova de que `VALORPAG` é o dinheiro de verdade:** a soma dele
(R$ 2.378.315,73) bate com a soma dos lançamentos já migrados marcados como
realizados (R$ 2.374.762,13) — diferença de R$ 3.553,60 em 30 anos. São duas
fontes independentes contando a mesma coisa.

### 2.3 "Em aberto" é maior do que parece — e maior do que o app diz hoje

Ingênuo seria somar as parcelas sem data de pagamento: R$ 1.299.587,61. Mas
**7.849 parcelas foram pagas pela metade** (`PARCIAL = 'S'`): a linha tem data de
pagamento, e mesmo assim sobrou saldo.

```
Cobrado           R$ 5.808.797,26
Recebido          R$ 2.378.315,73
Em aberto de fato R$ 3.430.481,53   ← e não R$ 1.299.587,61
```

E atenção a uma armadilha de vocabulário: a coluna **"Em aberto" que a lista de
pacientes já mostra hoje não é isto**. Ela soma o *valor dos tratamentos
planejados* — serviço que ainda nem foi feito. Dívida de tratamento feito é outra
coisa. Depois desta migração passam a existir dois números diferentes, e eles
**precisam de nomes diferentes na tela**, senão a Dra. Kátia lê um pelo outro.

---

## 3. Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Migrar `ARQFAT`? | **Sim** | Sem ele, "quanto entrou" só existe do zero. Com ele, 30 anos de caixa real. 0 órfãos e conferência possível ao centavo. |
| Uma tabela ou duas? | **Uma: `parcela`** | Recebimento é parcela com `pago_em` preenchido. Duas tabelas duplicariam a mesma verdade. |
| Parcela liga em lançamento? | **Não** | O Dentalis nunca ligou (`ARQDENTE.DTPAGTO` está vazio nas 44.812 linhas). Inventar o vínculo seria fabricar dado clínico-financeiro. |
| Biblioteca de gráfico? | **Nenhuma. SVG na mão** | Mesma escolha do odontograma. Zero dependência nova, funciona sem internet, e são barras, linhas e pizza — não é D3. |
| Preço muda como? | **Linha nova em `preco`** | `vigente_desde` já existe. Editar preço não apaga o preço antigo: relatório de 2019 continua lendo o preço de 2019. |
| Data suspeita | **Entra marcada** | 21 linhas com data impossível (ano 0200, 9200). Preservar e marcar, como no resto da migração. |
| Escopo do gráfico | **Desde 1995** | Antes disso é Cruzeiro/URV: somar com Real dá número sem sentido. |

---

## 4. Arquitetura

### 4.1 Módulo novo: `app/financeiro/`

```
app/financeiro/
  models.py    parcela
  service.py   fronteira publica: agregacoes e registro de recebimento
  rotas.py     telas
  api.py       JSON dos graficos
```

Fronteira de módulo continua valendo: `financeiro` fala com `pacientes` e
`clinico` pelas `service.py` deles, nunca por `JOIN` em tabela alheia. O
`clinico/service.py` já anuncia isso no topo do arquivo desde o MVP:

> *"Quando o modulo financeiro chegar, ele chama funcoes daqui — nunca consulta a
> tabela lancamento direto."*

### 4.2 Tabela `parcela`

```python
class Parcela(Base):
    id, clinica_id, paciente_id
    numero: str            # '01/03' como veio; '' quando o Dentalis nao dizia
    vencimento: date
    valor_cobrado: Numeric(12, 2)      # ORIGINAL
    valor_corrigido: Numeric(12, 2)    # VALORREC
    pago_em: date | None               # DTPAGTO
    valor_pago: Numeric(12, 2)         # VALORPAG, 0 quando nada entrou
    juros, multa, desconto: Numeric(12, 2)
    forma_pagamento: str | None        # CODTPAG -> ARQTPAG
    observacao: str | None
    codigo_legado: str | None          # CODICLIE + PARCELA + DTVENCTO
    revisar_motivo: list[str]
    excluido_em: datetime | None       # exclusao logica, como todo o resto
```

**Saldo é derivado, nunca guardado:** `valor_cobrado - valor_pago`. Guardar saldo
é guardar a mesma verdade em dois lugares — e um dos dois envelhece errado.

### 4.3 Migração `migracao/financeiro.py`

Segue o padrão do resto: conferência que **aborta sem gravar** se os números não
baterem.

| Conferência | Esperado |
|---|---|
| Linhas | 28.244 |
| Soma de `valor_cobrado` | R$ 5.808.797,26 |
| Soma de `valor_pago` | R$ 2.378.315,73 |
| Parcelas sem pagamento | 7.546 |
| Pacientes distintos | 5.340 |
| Linhas marcadas para revisar | 21 (datas impossíveis) |

---

## 5. As telas

### 5.1 Financeiro (menu, hoje "em breve")

Um seletor de período no topo — **mês** (padrão: o mês corrente) com navegação
para trás, e um modo **ano**. Abaixo, quatro números e três gráficos.

**Os quatro números do período:**

| Número | O que soma |
|---|---|
| Recebido | `valor_pago` das parcelas com `pago_em` no período |
| Produzido | `valor` dos lançamentos com `data_realizada` no período |
| A receber | `valor_cobrado - valor_pago` de tudo que já venceu |
| Tratamentos | quantos lançamentos foram realizados no período |

Os nomes são os do furo 5: **a fazer** é tratamento planejado, **a receber** é
tratamento feito e não pago.

**Recebido** e **Produzido** são coisas diferentes de propósito: um tratamento
pode ser feito em março e pago em julho. Mostrar os dois lado a lado é o que
deixa isso visível em vez de escondido numa média.

**Gráficos:**

1. **Barras — dinheiro recebido mês a mês**, 12 meses do ano escolhido, com o ano
   anterior em cinza atrás para comparar.
2. **Barras — tratamentos realizados por dia** do mês escolhido. Responde
   "quantos tratamentos foram feitos no dia tal", que foi o pedido literal.
3. **Pizza — produção por categoria de tratamento** no período (Dentística,
   Prótese, Endodontia…), por valor. Segunda pizza, na mesma linha: **por
   convênio**.

**Tabela abaixo:** parcelas vencidas e não quitadas, da mais velha para a mais
nova, com paciente, vencimento, cobrado, pago e saldo. É a lista de cobrança.

### 5.2 Registrar recebimento

Botão na tela do paciente e no financeiro. Formulário curto: valor, data, forma
de pagamento, observação. Cria uma `parcela` já quitada (`numero` vazio,
vencimento = data). Marcar uma parcela antiga como paga é a mesma tela, com o
valor pré-preenchido pelo saldo.

### 5.3 Tratamentos — preço e edição

- Coluna **Preço** na tabela, mostrando o valor particular (convênio `001`), com
  um "+2 convênios" que expande os demais.
- Cada linha vira clicável: abre edição de nome, categoria, onde costuma ser,
  ativo/inativo e **preço por convênio**.
- Trocar preço grava linha nova em `preco` com `vigente_desde = hoje`.

### 5.4 Edição de paciente

Tela de edição com nome, telefones, nascimento e convênio. Duas regras:

- **Auditoria com antes e depois**, como toda escrita.
- **Corrigir tira a marca**: se o cadastro estava marcado com
  `telefone_incompleto` e o telefone foi corrigido, a marca sai — é assim que a
  lista de "revisar" encolhe com o trabalho da recepção.

### 5.5 Edição de lançamento

No histórico do odontograma, cada linha vira editável: **valor**, situação
(planejado/realizado), data e observação. Não muda dente nem região — mudar o
alvo é apagar e lançar de novo, que já existe e é exclusão lógica.

---

## 6. Os furos, ditos na cara

Nenhum destes é esquecimento. São limites do dado que existe:

1. **Forma de pagamento não existe no histórico.** 28.234 das 28.244 parcelas têm
   `CODTPAG = '00'` (vazio). Gráfico de "recebido por forma de pagamento" só
   passa a fazer sentido para o que for registrado daqui para frente. Não vou
   desenhar um gráfico que seria 100% "não informado".

2. **Pagamento parcial perde a data das parcelas intermediárias.** O Dentalis
   guardava só a data do último pagamento. Quem pagou R$ 50 em março e R$ 50 em
   agosto aparece com R$ 100 em agosto. O total do ano fecha; o mês a mês tem
   esse viés, e ele vai escrito na tela.

3. **R$ 3,4 milhões "em aberto" é história, não cobrança.** É dívida acumulada
   desde 1996, boa parte de gente que não volta há vinte anos. Por isso a lista
   de cobrança abre filtrada nos últimos 24 meses, com o total histórico
   disponível mas fora do caminho.

4. **Parcela não sabe qual tratamento pagou.** O Dentalis não ligava os dois.
   Então "quanto rendeu a Endodontia" é respondido pela produção (lançamentos), e
   "quanto entrou" pelo caixa (parcelas) — nunca cruzando os dois como se fossem
   a mesma pergunta.

5. **Dois "em aberto" diferentes vão coexistir.** O da lista de pacientes
   (tratamento planejado, não feito) e o do financeiro (feito, não pago). Vão ser
   renomeados: **"a fazer"** e **"a receber"**.

6. **Não vou migrar `ARQPAG`** (contas a pagar a fornecedores, 31 linhas) nem
   `ARQPRO` (laboratório de prótese). São outro assunto e o volume não justifica
   agora.

---

## 7. O que precisa de aval da Dra. Kátia

Não bloqueia a implementação — o dado entra preservado de qualquer jeito — mas
muda o que a tela deve *dizer*:

- **Dívida antiga é dívida?** R$ 3,4 milhões em aberto desde 1996. Se ela
  considera prescrito, cabe um botão de "baixar como perdido" que marca sem
  apagar.
- **Pagamento parcial com data única** (furo 2) é aceitável para o gráfico mensal
  do histórico, ou o histórico só deve aparecer por ano?

---

## 8. Ordem de implementação

Cada fase entrega algo usável sozinha, e as primeiras não dependem da migração:

1. **Preço na tela de Tratamentos** — dado já existe, só falta mostrar.
2. **Edição de tratamento e de preço.**
3. **Edição de paciente.**
4. **Edição de lançamento** (valor, situação, data).
5. **Tabela `parcela` + migração do `ARQFAT`** com conferência ao centavo.
6. **Módulo financeiro**: números do período, tabela de cobrança.
7. **Gráficos** em SVG: barras mensais, barras diárias, duas pizzas.
8. **Registrar recebimento.**
