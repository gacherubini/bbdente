# `migracao/` — trazendo o Dentalis para dentro

Leia primeiro o [`AGENTS.md`](../AGENTS.md) da raiz e o runbook em
[`docs/MIGRACAO.md`](../docs/MIGRACAO.md).

Este pacote roda **uma vez** e depois vira documentação viva de onde cada dado veio.
Nenhuma rota da aplicação importa dele.

## Antes de tocar em qualquer coisa aqui

Leia `dados_extraidos/DICIONARIO.md`. Ele traz a decodificação do `POSDENTE`, o mapa
índice→FDI e as provas de cada afirmação. Sem ele você vai adivinhar o significado dos
campos, e adivinhar aqui corrompe 30 anos de prontuário em silêncio.

## Os quatro princípios

1. **Nunca destruir.** Importa o dado como está. O que for suspeito entra marcado em
   `revisar_motivo`, não corrigido no chute nem descartado.
2. **Rastreabilidade.** Todo registro guarda `codigo_legado`.
3. **Idempotência.** Reexecutável quantas vezes for necessário a partir do extrato.
4. **Falha alto.** Se a conferência final não bater, aborta sem gravar.

## Como está organizado

| Arquivo | Papel |
|---|---|
| `__main__.py` | orquestra tudo numa transação só; `python -m migracao` |
| `extrato.py` | leitor somente-leitura do SQLite imutável |
| `texto.py` | `limpar()` e `data_legada()` — limpeza de texto e datas impossíveis |
| `posdente.py` | **o coração**: coordenada de tela do Dentalis → escopo + dente + região |
| `catalogo.py` | categorias, convênios, procedimentos, preços |
| `pacientes.py` | pacientes, telefones, endereços |
| `lancamentos.py` | os 44.812 lançamentos + as 29.350 regiões |
| `condicoes.py` | a camada azul (`ARQICONE`) |
| `anamnese.py` | perguntas, respostas e observações clínicas |
| `conferencia.py` | a conferência bloqueante |

Cada etapa expõe `migrar(sessao, extrato, clinica_id)` e devolve as contagens — um
dataclass de resultado, exceto `condicoes.py`, que devolve um `int`. `__main__.py`
chama as cinco em ordem e só então confere.

`posdente.py` e `texto.py` são **lógica pura, sem banco** — testáveis em milissegundos.
É de propósito: é onde mora o risco.

## `POSDENTE` não é um código de face

É a coordenada de um caractere na tela do terminal original, em dois campos de 2 chars
**alinhados à direita**:

```
POSDENTE = [ Y (chars 0-1) ][ X (chars 2-3) ]      ex.: "1467" -> Y=14, X=67
```

Duas armadilhas que já custaram caro:

- **Não faça `strip()` na string inteira.** `" 947"` é `Y=9, X=47`, não `945`. Fazer
  strip quebra 17.791 registros. Há um teste que existe só para impedir isso.
- **Mesial e distal dependem do quadrante.** A tela é espelhada na linha média.
  Nos quadrantes 1 e 4, andar para a direita aproxima da linha média (= mesial); nos
  quadrantes 2 e 3, é o contrário.

O algoritmo já foi validado contra os 44.812 registros reais: produz exatamente 29.350
lançamentos com escopo `REGIOES` e perde **1** registro (`"13-3"`, corrompido, já
conhecido).

## Ao mexer aqui

- Os números da conferência (`5.561`, `44.812`, `29.350`, `3.461.389,07`, `9.629`,
  `2.046`) vieram da contagem do extrato. **Nunca os relaxe para fazer um teste passar** —
  isso é escolher perder registro.
- Os testes contra dados reais se auto-marcam como `skipped` quando o extrato não
  existe. `skipped` não é `passed`: enquanto estiverem assim, a migração está escrita,
  não verificada.
- O índice sequencial 1–32 do Dentalis **só existe aqui dentro**. Ao sair deste pacote,
  o dente é FDI.
