# `app/` — a aplicação

Leia primeiro o [`AGENTS.md`](../AGENTS.md) da raiz. Isto aqui é o detalhe por módulo.

## A fronteira

Cada módulo é dono das suas tabelas e se apresenta ao resto do mundo por uma
`service.py`. Ninguém importa `models` de outro módulo; ninguém faz `JOIN` em tabela de
outro módulo.

```
shared/      db, tipos, dentes        — todo mundo pode usar
auth/        usuario, sessao, auditoria
pacientes/   depende de: catalogo.service (nome do convenio)
catalogo/    depende de: —
clinico/     depende de: pacientes.service, catalogo.service
```

`clinico` depende de `pacientes` (um lançamento pertence a um paciente) e importa
`pacientes.service` no topo do arquivo. A volta existe só para os contadores da lista de
pacientes, e por isso `pacientes.service` importa `clinico.service` **dentro da função**:
importar nos dois sentidos no topo trava o Python com import circular. Isso está
comentado no código; não "arrume".

`app/shared/modelos.py` é o **único** arquivo onde modelos de módulos diferentes se
encontram, e existe só para o Alembic enxergar o metadata completo.

## Módulo a módulo

| Módulo | Onde olhar primeiro |
|---|---|
| `shared/tipos.py` | `Escopo`, `Regiao`, `StatusLancamento`, `TipoCondicao` — o vocabulário |
| `shared/dentes.py` | FDI, quadrantes, raízes, e a geometria de tela do dente |
| `auth/` | `sessao.py` (cookie assinado), `auditoria.py` (toda escrita passa aqui) |
| `pacientes/service.py` | `buscar()` — busca por nome, telefone ou código, com os filtros |
| `catalogo/service.py` | `arvore()` alimenta o painel de lançamento e a tela de tratamentos |
| `clinico/service.py` | `estado_do_odontograma()` e `lancar()` — o miolo do sistema |
| `clinico/api.py` | os endpoints JSON que o odontograma consome |

## O odontograma

`static/odontograma.js` **não sabe anatomia**. Ele recebe `paredes` e `canais_tela`
prontos do servidor e desenha. Qual parede é mesial, quantos canais o dente tem e em que
ordem aparecem são decididos em `shared/dentes.py`, que tem teste. Há um teste que falha
se essa lógica voltar a existir no JS — dois lugares decidindo a mesma coisa, e um deles
sem teste, é como se grava histórico no dente errado.

`static/painel.js` é o painel de lançamento: escolhe o tratamento, pré-marca o escopo e
as regiões conforme o hábito real da dentista (calculado na migração a partir das 44.812
ocorrências) e permite repetir o mesmo tratamento em vários dentes.

**A tela sugere, não impõe.** Não há validação de compatibilidade entre tratamento e
região: o histórico real mostra o mesmo tratamento em escopos diferentes, e travar
rejeitaria dado verdadeiro. Há um teste que impede as caixas de região de serem
desabilitadas.

## Duas camadas sobre o dente

- **`lancamento`** — o que ela faz e cobra. Tem status, data e valor. É o vermelho
  (planejado) e o verde (realizado).
- **`condicao`** — o azul "já existente". Estado pré-existente, sem preço e sem status.
  Hoje é **somente leitura**: os registros históricos são desenhados, mas não há tela
  para criar condição nova.

Regra de pintura: **o que está por fazer nunca some atrás do que já foi feito.**
Planejado vence realizado na mesma região.

## Telas

Jinja2 renderizado no servidor, com `templates/base.html` fornecendo os blocos
`titulo`/`conteudo`/`scripts` e a variável `aba` para marcar a navegação.

Identidade: **fundo branco, roxo nos detalhes** — não é uma interface roxa, é uma
interface branca com roxo. `"BDDente"` em branco sobre a lateral roxa. Os tokens estão
no `:root` de `static/bddente.css` e há teste que falha se algum sumir.

O autoescape do Jinja2 está ligado: um nome como `Sant'Ana` sai como `Sant&#39;Ana` no
HTML. Se um teste procura o literal cru, o teste está errado — não o template.
