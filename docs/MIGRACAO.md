# Migração do Dentalis

Traz os 30 anos de histórico clínico do Dentalis (FoxPro, 1996–2024) para o BDDente.

**Estado: executada.** O histórico clínico entrou em produção e o financeiro foi
acrescentado em 26/08/2026 (ver *Levar só uma etapa nova para produção*, em
[`OPERACAO.md`](OPERACAO.md)). Este documento continua sendo **o procedimento**: para
refazer a migração numa máquina nova, para acrescentar uma etapa, ou para entender o que
cada regra de conversão decidiu.

Repetir é seguro: cada etapa é idempotente e nada é gravado se a conferência reprovar.

## Para rodar de novo, em uma lista

1. Ter o extrato (`dados_extraidos/dentalis.sqlite`) na máquina
2. Rodar os 67 testes que sem ele ficam em `skipped` e vê-los passar
3. Rodar `python -m migracao` e obter **conferência aprovada**
4. Conferir os números no banco
5. Fazer um backup e uma restauração de teste ([`OPERACAO.md`](OPERACAO.md))

## Por que ela não rodou ainda

A migração lê o **extrato imutável** em `dados_extraidos/` — um SQLite já verificado
(100% dos registros lidos, encoding CP1252 confirmado, zero registros deletados, zero
referências órfãs), e não os `.DBF` originais.

Esse diretório é prontuário: nome, telefone, endereço e histórico clínico de 5.561
pessoas. Está no `.gitignore` e o repositório remoto é **público**. Ele viaja por fora
do git — pen drive, disco externo, o que for — nunca por commit, nunca por anexo em
serviço de terceiros.

Sem o arquivo, os testes de migração se marcam sozinhos como `skipped`:

| Arquivo | Testes |
|---|---|
| `tests/migracao/test_posdente_dados_reais.py` | 4 |
| `tests/migracao/test_migracao_catalogo.py` | 9 |
| `tests/migracao/test_migracao_pacientes.py` | 12 |
| `tests/migracao/test_migracao_lancamentos.py` | 15 |
| `tests/migracao/test_migracao_financeiro.py` | 18 |
| `tests/migracao/test_migracao_completa.py` | 9 |
| **Total** | **67** |

Numa máquina sem o extrato eles ficam em `skipped`, e ali a migração **não está
verificada** — só escrita. Numa máquina com o extrato, é aqui que se descobre se uma
regra de conversão quebrou.

## Rodando

### 1. Coloque o extrato no lugar

```bash
ls dados_extraidos/dentalis.sqlite
```

Se ele estiver em outro caminho, aponte com `EXTRATO_SQLITE` no `.env` — não copie o
arquivo para dentro do repositório se puder evitar.

### 2. Rode os testes primeiro

Eles são mais baratos que a migração e pegam quase tudo antes de você escrever no banco:

```bash
.venv/bin/pytest tests/migracao -v
```

Espere **106 passando, 0 skipped** (39 deles não dependem do extrato e já passam sem
ele). O mais importante é
`test_posdente_dados_reais.py`: ele roda o decodificador contra os 44.812 registros e
confere que produz exatamente 29.350 lançamentos com escopo `REGIOES`, 7.638 de boca,
7.824 de dente inteiro, e **1 único** registro corrompido (`POSDENTE = "13-3"`, já
conhecido).

Se as proporções entre mesial e distal saírem desequilibradas, **pare**: é sinal de
espelhamento invertido em algum quadrante. Esse teste existe exatamente para isso.

### 3. Suba o schema e migre

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m migracao
```

A migração inteira roda numa transação só. Se a conferência final reprovar, ela dá
`rollback` e **nada é gravado**. Rodar de novo é seguro: cada etapa é idempotente.

Os lançamentos levam alguns minutos — são 44.812 registros.

### 4. Confira

A saída tem que terminar com:

```
conferencia aprovada. migracao gravada.
```

A conferência é bloqueante e checa:

| O quê | Esperado |
|---|---|
| `paciente` | 5.559 (5.561 linhas, 2 códigos repetidos viram um cadastro só) |
| `lancamento` | 44.812 |
| `lancamento_regiao` | 29.350 |
| `SUM(lancamento.valor)` | R$ 3.461.389,07 |
| `condicao` | 9.629 |
| `resposta_anamnese` | 2.046 |
| Lançamento apontando para paciente inexistente | 0 |
| Dente fora da notação FDI | 0 |
| Lançamento de boca com dente preenchido | 0 |
| Região em lançamento sem escopo `REGIOES` | 0 |

Confirmando direto no banco:

```sql
SELECT (SELECT count(*) FROM paciente)          AS pacientes,
       (SELECT count(*) FROM lancamento)        AS lancamentos,
       (SELECT count(*) FROM lancamento_regiao) AS regioes,
       (SELECT sum(valor) FROM lancamento)      AS soma;
-- 5559 | 44812 | 29350 | 3461389.07
```

### 5. Se a conferência reprovar

Ela imprime cada divergência com o rótulo, o encontrado e o esperado. Nada foi gravado,
então você pode investigar com calma e rodar de novo. Não relaxe o número esperado para
fazer passar — ele veio da contagem do extrato, e mudá-lo é escolher perder registro.

## O que a migração faz com dado ruim

O princípio é **preservar e marcar**, nunca corrigir no chute nem descartar. O que for
suspeito entra no banco com uma etiqueta em `revisar_motivo`, aparece marcado na tela de
pacientes, e a dentista corrige quando quiser.

| Problema | O que acontece |
|---|---|
| Datas impossíveis (1194, 2080, 9200) — ~15 registros | importa e marca `data_suspeita` |
| 2 códigos duplicados (`1659/PT`, `4783/PT`) — a mesma pessoa em duas linhas | vira um cadastro só, com os telefones das duas linhas, marcado `possivel_duplicata` |
| Telefone com vários números num campo | separa e formata, guardando `numero_original` |
| 247 lançamentos sem descrição de tratamento | cria `DESCONHECIDO (cód. X)` e marca |
| 39 registros com escopo boca mas dente preenchido | importa como `BOCA` e marca |
| 33 lançamentos e 9 condições com `CODICLIE` vazio (R$ 7.296,41, de 2001 a 2023) | vão para o cadastro `SEM-CODIGO`, marcado `sem_paciente_no_legado` |
| 22 respostas de anamnese de `1104/OR`, que só existe no arquivo de orçamento | cria o cadastro dela, marcado `cadastro_so_no_orcamento` — juntar dado de saúde de gente diferente seria pior |
| 5.522 ícones de boca inteira (`NUMDENTE` 81–88) | entram como condição sem dente; o código do ícone fica guardado |
| Telefone que ficou grande demais depois de separar (2 números colados por hífen) | grava assim mesmo e marca `telefone_suspeito` |
| 1 registro com `POSDENTE` inválido (`"13-3"`) | importa como `DENTE` e marca |

## O que fica de fora

**`ARQFAT` — 28.244 lançamentos financeiros.** O extrato está preservado e conferido,
mas migra junto com o módulo financeiro, que não é escopo do MVP.

**Os rótulos das flags `STATUS1..12`** do cadastro antigo viviam na interface do
Dentalis, não no banco. Estão perdidos e não migram.

## Pendente de gente, não de código

| Item | Quem resolve |
|---|---|
| Traduzir os 309 códigos de ícone (`OICO14`, `d01RX`, `d08i2`…). Sabemos o dente e a frequência, não o significado — e 3 códigos cobrem metade dos 9.629 registros. Até lá migram com `icone_legado` preservado e tipo genérico `OUTRO`. | **Dra. Kátia**, ~15 minutos de conversa |
| Confirmar o espelhamento mesial/distal olhando um caso real que ela lembre. O teste cruzado garante que o desenho e o Dentalis concordam entre si, **não** que a convenção do Dentalis fosse a correta. | **Dra. Kátia** |
| Nomes dos convênios 003 a 006, que não existem no banco antigo — hoje entram como "Convenio 004" etc., visivelmente provisórios | **Dra. Kátia** |
| Validar o odontograma com quem vai usar, antes de congelar a tela | **Dra. Kátia** |
| Fotos e radiografias: não existem no backup. Se houver em outro lugar, é escopo novo. | **Dra. Kátia** |

## Referências

- `dados_extraidos/DICIONARIO.md` — dicionário dos dados do Dentalis, decodificação do
  `POSDENTE`, mapa índice→FDI e as provas. **Leitura obrigatória** antes de mexer em
  qualquer coisa dentro de `migracao/`.
- [`../migracao/AGENTS.md`](../migracao/AGENTS.md) — como o pacote é organizado
- [`superpowers/specs/2026-08-25-bddente-mvp-design.md`](superpowers/specs/2026-08-25-bddente-mvp-design.md) — §6 descreve a migração


## Financeiro: as 28.244 parcelas do `ARQFAT`

Etapa acrescentada em 26/08/2026. É o livro-caixa do consultório — o MVP tinha
migrado o prontuário e deixado o dinheiro para trás.

| Conferência | Esperado |
|---|---|
| Parcelas | 28.244 |
| Soma cobrada (`ORIGINAL`) | R$ 5.808.797,26 |
| Soma paga (`VALORPAG`) | R$ 2.378.315,73 |
| Parcelas sem pagamento | 7.546 |
| Pacientes distintos | 5.340 (zero órfãos) |
| Marcadas para revisar | 5 (ano 0200, 0202, 0203, 9200) |
| Substituídas por outra do mesmo carnê | 5.163 |

**Por que confiar no `VALORPAG`:** a soma dele bate com a dos lançamentos
realizados já migrados (R$ 2.374.762,13) — R$ 3.553,60 de diferença em 30 anos,
vindo de duas fontes independentes.

**O carnê.** O Dentalis regravava o saldo restante a cada pagamento, com o mesmo
vencimento. Somar todas as linhas inflava a dívida em R$ 1.392.888,31 (41%). As
linhas superadas entram com o valor como veio, marcadas em `parcela.substituida`,
e ficam fora da soma da dívida — nunca fora da soma do dinheiro recebido. Detalhe
em [`AGENTS.md`](../AGENTS.md) e na spec do financeiro.

**O que NÃO foi migrado, e por quê:** `ARQPAG` (31 linhas de contas a pagar a
fornecedor) e `ARQPRO` (laboratório de prótese). São outro assunto, e o volume não
justifica agora.
