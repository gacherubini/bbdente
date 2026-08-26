# Migração do Dentalis

Traz os 30 anos de histórico clínico do Dentalis (FoxPro, 1996–2024) para o BDDente.

**Estado: o código está pronto e commitado; a migração ainda não foi executada.**
Ela nunca rodou porque exige o extrato com dado real de paciente, que não pode ser
versionado. Este documento é o que falta fazer.

## O que falta, em uma lista

1. Ter o extrato (`dados_extraidos/dentalis.sqlite`) na máquina
2. Rodar os 46 testes que hoje estão em `skipped` e vê-los passar
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
| `tests/migracao/test_migracao_pacientes.py` | 11 |
| `tests/migracao/test_migracao_lancamentos.py` | 14 |
| `tests/migracao/test_migracao_completa.py` | 8 |
| **Total** | **46** |

Enquanto eles estiverem em `skipped`, a migração **não está verificada** — só escrita.

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

Espere **85 passando, 0 skipped**. O mais importante é
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
| `paciente` | 5.561 |
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
-- 5561 | 44812 | 29350 | 3461389.07
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
| 2 pacientes duplicados (`1659/PT`, `4783/PT`) | importa os dois e marca `possivel_duplicata` |
| Telefone com vários números num campo | separa e formata, guardando `numero_original` |
| 247 lançamentos sem descrição de tratamento | cria `DESCONHECIDO (cód. X)` e marca |
| 39 registros com escopo boca mas dente preenchido | importa como `BOCA` e marca |
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
