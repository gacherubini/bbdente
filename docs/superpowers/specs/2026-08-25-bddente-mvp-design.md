# BDDente — Design do MVP

**Data:** 2026-08-25
**Status:** aprovado para virar plano de implementação
**Origem:** substituição do Dentalis (FoxPro, 1996–2024) do consultório da Dra. Kátia

---

## 1. Objetivo

Substituir o Dentalis — sistema em FoxPro que rodava num Windows antigo e hoje é inutilizável —
por uma aplicação web, preservando integralmente os 30 anos de histórico clínico.

O MVP entrega **login, cadastro de pacientes, odontograma com lançamento de tratamento,
catálogo de tratamentos e anamnese**, com todo o histórico migrado. Financeiro, agenda e demais
módulos vêm depois, sobre a mesma base.

### Contexto de uso

Uma dentista, um consultório, ~500 pacientes ativos (5.561 no cadastro histórico), média de
2,3 lançamentos por consulta. Uso em produção real desde o primeiro dia.

---

## 2. Decisões

| Decisão | Escolha | Consequência |
|---|---|---|
| Uso | Produção real | Migração é escopo do MVP; LGPD e backup são requisito, não fase 2 |
| Hospedagem | Nuvem, web puro | Sem modo offline no MVP; acesso por navegador de qualquer lugar |
| Tenancy | Uma clínica, `clinica_id` desde o dia 1 | Custo quase zero agora; evita reescrever o schema se virar produto |
| Usuários | Um só (a dentista) | Sem perfis nem permissões; auditoria mesmo assim |
| Dentição | Só permanente (32 dentes) | Cobre 95% dos pacientes; decíduo fica para v2 |
| Modularidade | Monolito modular | Um deploy e um banco, com fronteira de módulo no código |
| Alvo do tratamento | N:N livre | Qualquer tratamento em qualquer região; a tela sugere, não impõe |

---

## 3. Arquitetura

### Stack

Mesma do Revy, que o time já opera:

- **FastAPI** + **Uvicorn** · **Jinja2** para as telas
- **SQLAlchemy 2** + **psycopg 3** + **Alembic** · **PostgreSQL**
- **argon2-cffi** (senha) · **itsdangerous** (sessão assinada)
- **pytest** · **Docker** · **Fly.io**

O odontograma é a única parte interativa de verdade: uma **ilha de SVG + JavaScript sem
framework**, conversando com endpoints JSON. O resto das telas é Jinja2 renderizado no servidor.
Isso evita arrastar um framework de front para o projeto inteiro por causa de uma tela.

### Módulos

```
app/
  auth/       usuário, sessão, auditoria
  pacientes/  cadastro, telefones, endereços
  catalogo/   categorias, tratamentos, convênios, tabelas de preço
  clinico/    odontograma, lançamentos, condições, anamnese, observações
  shared/     db, clinica_id, tipos comuns
```

**Regra de fronteira:** um módulo só acessa outro pela `service.py` dele. Nunca importa modelo,
nunca faz `JOIN` em tabela de outro módulo. Quando o módulo financeiro chegar, ele chama
`clinico.service.lancamentos_do_paciente()` — não consulta a tabela `lancamento` direto.

Cada módulo é dono das suas tabelas. Migrations ficam centralizadas (um banco só), mas cada
migration declara a que módulo pertence.

---

## 4. Modelo de domínio

### Numeração dos dentes

Canônica é a **FDI**: `11`–`18`, `21`–`28`, `31`–`38`, `41`–`48`. O índice sequencial 1–32 do
Dentalis vira `codigo_legado`. O mapa de conversão está provado e documentado em
[`dados_extraidos/DICIONARIO.md`](../../../dados_extraidos/DICIONARIO.md).

### Onde o tratamento acontece

Um lançamento tem **escopo** explícito, e o escopo `REGIOES` aponta para uma ou mais regiões:

```
escopo  = BOCA | DENTE | REGIOES

regiao  = MESIAL | DISTAL | VESTIBULAR | LINGUAL | OCLUSAL      (coroa — 79% dos casos)
        | CANAL_MESIAL | CANAL_CENTRAL | CANAL_DISTAL           (raiz  — 21%)
```

- `BOCA` — consulta, limpeza, prótese removível. Sem dente. *(era `POSDENTE=8888`)*
- `DENTE` — extração, coroa, radiografia. Dente inteiro. *(era `9999`)*
- `REGIOES` — restauração, canal. Uma ou mais regiões marcadas.

`OCLUSAL` é gravado sempre com esse nome, mas a tela exibe **"Incisal"** nos dentes anteriores
(11–13, 21–23, 31–33, 41–43), que é o correto clinicamente. É rótulo derivado, não dado duplicado.

**Não há validação de compatibilidade** entre tratamento e região. O histórico real mostra que
9 dos 51 tratamentos mais usados aparecem legitimamente em escopos diferentes (“Consertos em
geral” aparece em dente inteiro, boca toda e parede). Travar rejeitaria dados reais e criaria
uma barreira que o sistema antigo nunca teve.

### Duas camadas sobre o dente

1. **`lancamento`** — o que ela faz e cobra. Tem status, data e valor. É o vermelho (planejado) e
   o verde (realizado) da legenda.
2. **`condicao`** — o azul "já existente". Estado pré-existente do dente (ausente, restauração
   antiga, coroa de outro profissional). Sem preço, sem status.

### Tabelas

**auth**
```
clinica          id, nome, criado_em
usuario          id, clinica_id, email, senha_hash, nome, ativo, criado_em
auditoria        id, clinica_id, usuario_id, acao, entidade, entidade_id,
                 dados_antes jsonb, dados_depois jsonb, ip, criado_em
```

**pacientes**
```
paciente         id, clinica_id, codigo_legado, nome, nascimento, cpf, ci, email,
                 profissao, estado_civil, indicacao, pai, mae, convenio_id,
                 cadastrado_em, ultimo_atendimento,
                 revisar_motivo text[],        -- marcações de dado suspeito
                 excluido_em
paciente_telefone  id, paciente_id, numero, numero_original, principal
paciente_endereco  id, paciente_id, tipo(RESIDENCIAL|COMERCIAL),
                   logradouro, bairro, cidade, uf, cep
```

**catalogo**
```
categoria        id, clinica_id, codigo, nome, ordem
convenio         id, clinica_id, codigo, nome
procedimento     id, clinica_id, codigo, nome, categoria_id, ativo,
                 escopo_sugerido, regioes_sugeridas regiao[], duracao_min
preco            id, procedimento_id, convenio_id, valor, vigente_desde
```

`escopo_sugerido` e `regioes_sugeridas` são **calculados a partir do histórico** na migração:
para cada um dos 183 tratamentos, o escopo dominante nas 44.812 ocorrências vira a sugestão.
O palpite inicial da tela é literalmente o hábito dela.

**clinico**
```
odontograma       id, paciente_id, numero, criado_em
lancamento        id, clinica_id, odontograma_id, dente smallint NULL, escopo,
                  procedimento_id, status(PLANEJADO|REALIZADO),
                  data_planejada, data_realizada, valor numeric(12,2),
                  observacao, codigo_legado, criado_por, criado_em, excluido_em
lancamento_regiao lancamento_id, regiao          -- N:N, PK composta
condicao          id, odontograma_id, dente smallint, tipo, regioes regiao[],
                  icone_legado, criado_em, excluido_em
                  -- tipo: AUSENTE | RESTAURACAO_ANTERIOR | COROA | IMPLANTE | OUTRO
                  -- os 309 códigos legados caem em OUTRO até serem traduzidos (§10)
pergunta_anamnese id, clinica_id, codigo, texto, tipo_resposta, ordem, ativa
resposta_anamnese id, paciente_id, pergunta_id, resposta, respondido_em
observacao_clinica id, paciente_id, texto, criado_por, criado_em
```

`dente` é `NULL` quando `escopo = BOCA`.

**Exclusão é sempre lógica** (`excluido_em`). Ver §7.

---

## 5. Telas do MVP

Navegação lateral fixa: **Pacientes · Odontograma · Tratamentos**, com **Financeiro** visível
e marcado como "em breve".

Identidade: fundo branco, **"BDDente" em branco** sobre a lateral roxa, roxo nos detalhes e
nos estados ativos. Não é uma interface roxa — é uma interface branca com roxo.

### 5.1 Login
Email e senha. Sessão assinada em cookie. Sem cadastro público.

### 5.2 Pacientes
Busca no centro da tela — é o que ela faz o dia inteiro. Digitar e apertar Enter abre o
odontograma do primeiro resultado. Busca por nome, telefone ou código.

Filtros: Ativos · Com pendência · Em aberto no financeiro · Todos.

Colunas: paciente (nome + código), idade, telefone, último atendimento, convênio, tratamentos
pendentes, valor em aberto.

**Dados suspeitos aparecem marcados**, não escondidos nem corrigidos: telefone incompleto,
paciente sem data de nascimento, data de atendimento impossível. Ela corrige quando quiser.

### 5.3 Odontograma
Layout linear espaçoso: duas fileiras de 16 dentes, separação visível entre quadrantes, dentes
grandes o suficiente para acertar a região no clique. Numeração FDI entre as fileiras.

Cada dente é desenhado como **quadrado com miolo** (visão de cima: miolo = oclusal, 4 bordas =
as demais faces) mais **1 a 3 hastes** representando os canais da raiz. Todas as 8 regiões são
clicáveis.

Cores: vermelho = planejado · verde = realizado · azul = condição existente.

**Painel de lançamento à direita**, sempre visível junto do odontograma. Fluxo:

1. Clica no dente (ou numa região específica)
2. O painel mostra as categorias; escolhe o tratamento
3. O escopo e as regiões já vêm **pré-marcados** conforme o hábito dela — e pode alterar
4. **Lançar** grava; **Repetir em outro dente** mantém o tratamento carregado para os próximos
   cliques

O passo 4 existe porque 46% das consultas com mais de um lançamento repetem o mesmo tratamento
em vários dentes.

Abaixo do odontograma: histórico do paciente, ordenado por data.

### 5.4 Tratamentos
Catálogo agrupado pelas 12 categorias. Permite criar e editar tratamento, definir categoria,
escopo sugerido e preço por convênio.

### 5.5 Anamnese
Questionário por paciente, com as perguntas do catálogo. Respostas Sim/Não e texto livre.

---

## 6. Migração

### O que entra

| Origem | Volume | Destino |
|---|---|---|
| `ARQCLIEN` | 5.561 | `paciente` + telefones + endereços |
| `ARQDENTE` | 44.812 | `lancamento` + `lancamento_regiao` |
| `ARQICONE` | 9.629 | `condicao` |
| `ARQSE001`…`051` | 612 pares | `procedimento` + `preco` |
| `ARQESPE` | 12 | `categoria` |
| `TABELAS` | 7 | `convenio` |
| `ARQUEST` + `ARQSINAO`/`ARQSIQUA` | 37 + 2.046 | anamnese |
| `OBSERCLI` | 80 com texto | `observacao_clinica` |

**Fica para depois:** `ARQFAT` (28.244 lançamentos financeiros). O extrato está preservado e
conferido; migra junto com o módulo financeiro.

### Fonte

A migração lê o **extrato imutável** em `dados_extraidos/` (SQLite + CSV), não os `.DBF`
originais. O extrato já foi verificado: 100% dos registros lidos, encoding CP1252 confirmado,
zero registros deletados, zero referências órfãs.

### Princípios

1. **Nunca destruir.** Importa o dado como está; marca o que é suspeito em `revisar_motivo`.
2. **Rastreabilidade.** Todo registro guarda `codigo_legado`.
3. **Idempotente.** Reexecutável quantas vezes for necessário a partir do extrato.
4. **Falha alto.** Se a conferência final não bater, aborta sem gravar.

### Tratamento de problemas conhecidos

| Problema | Ação |
|---|---|
| Datas impossíveis (1194, 2080, 9200) — ~15 registros | Importa, marca `data_suspeita` |
| 2 pacientes duplicados (`1659/PT`, `4783/PT`) | Importa ambos, marca `possivel_duplicata` |
| Telefone com múltiplos números num campo | Separa e formata; guarda `numero_original` |
| Espaços à esquerda em campos texto | Remove (seguro) |
| 247 lançamentos sem descrição de tratamento | Cria tratamento `DESCONHECIDO (cód. X)` e marca |
| 39 registros com escopo boca mas dente preenchido | Importa como `BOCA`, marca |
| 1 registro com `POSDENTE` inválido | Importa como `DENTE`, marca |

### Conferência (bloqueante)

Ao final, a migração recontabiliza e compara com o extrato. Aborta se divergir:

- `paciente` = 5.561
- `lancamento` = 44.812
- `SUM(lancamento.valor)` = R$ 3.461.389,07
- `lancamento_regiao` = 29.350 linhas (cada `POSDENTE` é uma única célula da grade,
  portanto exatamente uma região por lançamento migrado)
- `condicao` = 9.629
- `resposta_anamnese` = 2.046
- Zero lançamento apontando para paciente inexistente
- Toda `dente` não-nula é FDI válida

---

## 7. Segurança e LGPD

Prontuário odontológico tem **guarda mínima de 10 anos** após o último atendimento; se o
paciente era menor, o prazo começa quando ele completa 18 anos. A recomendação profissional é
guardar indefinidamente.

→ **O sistema não apaga nada fisicamente.** Toda exclusão é lógica (`excluido_em`) e some da
tela, mas o registro permanece. Não há `DELETE` no código de aplicação.

Dado de saúde é **dado pessoal sensível** pela LGPD, a categoria de maior proteção. Requisitos
do MVP:

- Senha com **argon2**; sessão em cookie assinado, expiração e renovação
- **Log de auditoria** de toda escrita: quem, o quê, quando, antes e depois
- **Backup diário automático** e **teste de restauração** rodando periodicamente — backup nunca
  restaurado não conta como backup
- **HTTPS** obrigatório; banco gerenciado com criptografia em repouso
- **Exportar prontuário do paciente em PDF** — atende o direito de acesso e serve para
  encaminhamento

---

## 8. Fora de escopo do MVP

Agenda de consultas · módulo financeiro (parcelas, recibos, boletos) · dentição decídua ·
múltiplos usuários e permissões · ortodontia e endodontia como fichas dedicadas · estoque e
fornecedores · modo offline · multi-clínica ativa.

Nenhum deles é impedido pelo modelo. Todos entram como módulo novo sobre a mesma base.

---

## 9. Testes

- **Unitário** (pytest): conversão FDI, derivação oclusal/incisal, parser de telefone,
  regras de escopo e região.
- **Migração**: roda contra o extrato real de 44.812 registros e valida a conferência do §6.
  É o teste mais importante do projeto.
- **Integração**: fluxo de lançar tratamento ponta a ponta; busca de paciente; login.
- **Auditoria**: toda escrita gera linha em `auditoria`.

---

## 10. Riscos e questões abertas

| Item | Situação |
|---|---|
| **309 códigos de ícone da camada de condição** (`OICO14`, `d01RX`, `d08i2`…) | Sabemos o dente e a frequência, mas não o significado. Os 3 mais usados cobrem metade dos 9.629 registros. **Precisa perguntar para a Dra. Kátia** — cerca de 10 códigos cobrem quase tudo. Até lá, migram com `icone_legado` preservado e tipo genérico. |
| **Rótulos das flags `STATUS1..12`** do cadastro antigo | Viviam na interface do Dentalis, não no banco. Perdidos. Não migram. |
| **Mesial × distal depende do quadrante** | Regra conhecida e documentada, mas é fonte fácil de erro de espelhamento. Precisa de teste unitário cobrindo os quatro quadrantes. |
| **Fotos e radiografias** | Não existem no backup. Se a Dra. Kátia tiver imagens em outro lugar, é escopo novo. |
| **Validação do odontograma com a usuária real** | O layout foi aprovado pelo desenvolvedor, não pela dentista. Vale uma sessão com ela antes de congelar a tela. |

---

## Referências

- [`dados_extraidos/DICIONARIO.md`](../../../dados_extraidos/DICIONARIO.md) — dicionário de dados
  do Dentalis, decodificação do `POSDENTE`, mapa índice→FDI e as provas.
- [`dados_extraidos/dentalis.sqlite`](../../../dados_extraidos/) — extrato completo e imutável.
- Mockups aprovados: `.superpowers/brainstorm/2468-1787700305/content/`
