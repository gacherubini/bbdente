# `app/` — a aplicação

Leia primeiro o [`AGENTS.md`](../AGENTS.md) da raiz. Isto aqui é o detalhe por módulo.

## A fronteira

Cada módulo é dono das suas tabelas e se apresenta ao resto do mundo por uma
`service.py`. Ninguém importa `models` de outro módulo; ninguém faz `JOIN` em tabela de
outro módulo.

```
shared/      db, tipos, dentes        — todo mundo pode usar
auth/        usuario, sessao, auditoria, identidade da clínica
pacientes/   depende de: catalogo.service (nome do convenio)
catalogo/    depende de: —
clinico/     depende de: pacientes.service, catalogo.service
financeiro/  depende de: pacientes.service (nome de quem pagou)
agenda/      depende de: pacientes.service (contatos), clinico.service
             (quem foi atendido no dia), auth.service (nome da clínica)
```

**A ponte entre agenda e prontuário é de mão única.** `agenda.service` importa
`clinico.service`; a volta — `agenda.service.vincular_paciente()`, chamada quando um
atendimento avulso é concluído — sai de `clinico/api.py`, **nunca** de
`clinico/service.py`, senão é ciclo de import de verdade.

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
| `financeiro/service.py` | `resumo()`, `a_receber()`, e o desfazer de recebimento |
| `agenda/service.py` | `grade()` monta semana e mês em 3 consultas; `marcar()` e `conflitos_de()` |
| `agenda/mensagem.py` | a allowlist de LGPD — leia antes de mexer em qualquer coisa de mensagem |
| `agenda/lembretes.py` | `reservar()` e `despachar()`, as duas fases; `rodar()` é a passada inteira |
| `agenda/relogio.py` | o laço que bate de 15 em 15 min para cada lembrete sair na hora dele |
| `agenda/whatsapp/` | o `Protocol` do provedor e o `fake` que roda nos testes |

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


## A agenda

`agendamento` responde uma pergunta só: **quem vem, e quando.** Não é prontuário — um
horário sem paciente (`paciente_id` nulo + `nome_avulso`) é a anotação de um telefonema,
o mesmo pedaço de papel que a clínica já usa. Não entra em PDF, não soma dinheiro e não
afirma nada sobre a saúde de ninguém. Por isso **marcar horário nunca exige cadastro**.

Três coisas que parecem detalhe e não são:

- **`fim` não é coluna.** É `inicio + duracao_min`, propriedade Python, como
  `Parcela.saldo`. E não vira o dia: 23:30 + 90min para em 23:59, senão o cartão
  apareceria no topo do dia, antes do próprio começo.
- **Desmarcar mora em `situacao`; `excluido_em` é só para engano.** O horário desmarcado
  continua na tela, riscado, para ninguém remarcar em cima achando que aquilo sempre
  esteve vazio.
- **Conflito avisa depois de gravar, nunca antes de deixar.** Encaixe, urgência e
  acompanhante acontecem de verdade, e sistema que proíbe é sistema contornado.

`dia` é `Date` e `inicio` é `Time`, ingênuos, relógio de parede da clínica — não
`timestamptz`. "Maria às 14h" quer dizer 14h no relógio da parede, hoje e daqui a três
anos; se o horário de verão voltar, um `timestamptz` deslocaria tudo que já está
marcado. E nenhuma função de `agenda/service.py` chama `date.today()`: o dia vem por
parâmetro, e é isso que torna o módulo testável sem congelar relógio.

## O lembrete de WhatsApp

Hoje o envio é **simulado**: quem roda é `whatsapp/fake.py`, e a chave geral
(`configuracao_clinica.lembrete_ativo`) nasce desligada. Nada sai para ninguém até
alguém ligar, com um provedor de verdade configurado.

O que não pode ser afrouxado sem pensar muito:

- **`UNIQUE (agendamento_id, tipo)` é a idempotência.** Não é um `if`, não é lock, não é
  disciplina: é o banco recusando a segunda linha. Se essa constraint sair, duas
  execuções concorrentes mandam a mesma mensagem duas vezes e ninguém percebe.
- **`ENVIANDO` nunca é retomado.** A mensagem saiu e o processo morreu antes do commit?
  Não sabemos se saiu — e na dúvida não manda. A garantia é **no máximo uma vez, nunca
  ao menos uma vez**: mandar duas vezes queima a paciente e é o padrão que a detecção do
  WhatsApp procura.
- **Quem NÃO recebe também vira linha**, `DESCARTADO` com motivo. Lembrete que
  simplesmente não é criado não aparece em tela nenhuma, e o que a clínica precisa é
  poder agir hoje, com a paciente na cadeira.
- **`paciente.aceita_whatsapp` nulo significa "nunca perguntamos", e não recebe.** Os
  5.559 cadastros migrados estão todos assim, sem backfill. Presumir autorização de
  5.559 pessoas cujo telefone foi coletado desde 1996 é o que a lei não deixa.
- **A régua do número é `pacientes/telefone.py::numero_para_whatsapp`**, a mesma da
  ficha e do telefone avulso. Ela não acrescenta o nono dígito, não chuta DDD e não
  corta número comprido — aqui o preço de inventar dígito é mandar mensagem de paciente
  para um estranho.

- **Cada lembrete tem a sua hora, e ela é recalculada do horário vivo.** O vencimento é
  `consulta − antecedência`, e `agenda/relogio.py` bate de 15 em 15 minutos até passar
  por ele. Nunca confie no `agendado_para` gravado: `remarcar()` muda dia e hora na
  mesma linha, e um vencimento velho manda a mensagem na hora do horário que não existe
  mais. Tem teste.
- **Hora que vem do banco passa por `lembretes.parede()`.** As colunas são `timestamptz`
  e o Postgres as devolve em UTC; a clínica vive em UTC−3. Comparar sem converter
  empurra tudo três horas para a frente, e o estrago é silencioso: um horário marcado
  com folga passa a parecer marcado depois do vencimento e a paciente não recebe nada —
  sem exceção, sem log, sem tela vermelha.
- **`marcado_em_cima` compara com `agendamento.criado_em`, não com o relógio de agora.**
  Se comparasse com o relógio, uma queda do app de duas horas descartaria quem marcou
  com folga, e a tela diria "marcou em cima da hora" — mentira sobre a paciente. Atraso
  nosso não vira culpa dela.
- **Não existe responder "PARAR".** Ninguém lê as respostas, e a Task 19 foi cancelada.
  O desligamento é o botão na ficha, à mão. Por isso a mensagem **nunca** pode oferecer
  "responda PARAR": prometer um canal que não existe é pior que não oferecer nenhum.

O relógio bate sozinho dentro do app. Além dele, `POST /tarefas/lembretes` é o gatilho
de emergência, autenticado por segredo em cabeçalho — token errado responde **404, nunca
401**, porque 401 confirmaria que o endereço existe. Os três caminhos (relógio, endpoint
e o botão "Enviar agora") passam por `lembretes.rodar()`, e há um teste de contrato que
falha se algum deles virar cópia.
