/* BDDente — a tabela do historico do paciente.
 *
 * Ela faz duas coisas e nao faz uma terceira:
 *
 * 1. **Se mantem atualizada.** Depois de lancar, corrigir ou excluir, pede as
 *    linhas de volta ao servidor (`/odontograma/{id}/historico`) e troca o
 *    `<tbody>`. Ate 31/08/2026 nao fazia isso: a linha nova so aparecia depois de
 *    um F5, e o cabecalho do dia continuava contando o que havia antes. Quem
 *    soma continua sendo o servidor — refazer a conta aqui seria a mesma regra em
 *    dois lugares, e um dia elas discordam.
 *
 * 2. **Manda corrigir.** O clique em "editar" nao abre formulario nenhum aqui:
 *    entrega o lancamento ao painel da direita, que ja sabe montar tratamento,
 *    dente e faces. Antes havia um formulario na propria linha, e ele so
 *    alcancava situacao, data, valor e observacao — corrigir o dente errado
 *    exigia excluir e lancar de novo.
 *
 * O que ela NAO faz e desenhar: o odontograma e do `painel.js`, e duas maos no
 * mesmo SVG e conflito esperando acontecer.
 */
(function () {
  "use strict";

  var tabela = document.querySelector(".titulo-historico + table");
  var linhas = document.getElementById("historico-linhas");
  if (!tabela || !linhas) return;

  var COLUNAS = 6;
  var estado = JSON.parse(document.getElementById("estado-inicial").textContent);
  var paciente = estado.paciente.id;
  var emCorrecao = null;

  function destacar(linha) {
    if (emCorrecao) emCorrecao.classList.remove("linha-editando");
    emCorrecao = linha;
    if (linha) linha.classList.add("linha-editando");
  }

  function recarregar() {
    return fetch("/odontograma/" + paciente + "/historico")
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("não foi possível recarregar o histórico");
        return resposta.text();
      })
      .then(function (html) {
        // A troca e do conteudo, nunca do <tbody>: os cliques sao ouvidos na
        // tabela, e trocar o elemento levaria os ouvintes junto.
        linhas.innerHTML = html;
        emCorrecao = null;
      })
      .catch(function () {
        /* Recarregar o historico e conforto; o lancamento ja esta gravado. Um
           erro aqui nao pode virar um alarme que faz duvidar do que foi salvo —
           a linha aparece no proximo carregamento da tela. */
      });
  }

  /* Entrega o lancamento ao painel. Os data-* trazem tudo: nao ha segunda ida
     ao servidor so para saber o que ja esta escrito na propria linha. */
  function corrigir(linha) {
    var dados = linha.dataset;
    destacar(linha);
    document.dispatchEvent(
      new CustomEvent("bddente:corrigir", {
        detail: {
          lancamento: dados.lancamento,
          procedimentoId: Number(dados.procedimentoId),
          procedimento: dados.procedimento || "tratamento",
          escopo: dados.escopo,
          dente: dados.dente ? Number(dados.dente) : null,
          regioes: dados.regioes ? dados.regioes.split(",") : [],
          status: dados.status,
          data: dados.data || "",
          valor: dados.valor,
          observacao: dados.observacao || ""
        }
      })
    );
  }

  tabela.addEventListener("click", function (evento) {
    var editar = evento.target.closest(".editar-lancamento");
    if (editar) {
      corrigir(editar.closest("tr"));
      return;
    }
    var excluir = evento.target.closest(".excluir-lancamento");
    if (excluir) {
      window.Confirmar.excluirLancamento(excluir.closest("tr"), {
        colunas: COLUNAS,
        aoConcluir: function (resposta) {
          // Excluir tira a cor do dente e muda a conta do dia: as duas coisas
          // precisam acontecer, e cada uma tem seu dono. O desenho e do painel.
          if (resposta && resposta.estado) {
            document.dispatchEvent(
              new CustomEvent("bddente:estado", { detail: resposta.estado })
            );
          }
          recarregar();
        }
      });
    }
  });

  // O painel avisa quando gravou (lancamento novo ou correcao) e quando a
  // correcao acabou. A tabela responde ao primeiro; ao segundo, so apaga o
  // destaque da linha.
  document.addEventListener("bddente:mudou", recarregar);
  document.addEventListener("bddente:correcao-fim", function () {
    destacar(null);
  });

  /* `?editar=123` vem do "editar" da tela do dia, que nao tem odontograma ao
     lado para corrigir dente e tratamento. Chegar aqui e abrir a correcao ja
     aberta naquele lancamento. Id que nao esta na tela nao e erro — pode ser de
     um dia que o limite do historico nao alcanca — entao a tela abre normal. */
  var pedido = new URLSearchParams(window.location.search).get("editar");
  if (pedido) {
    var linha = linhas.querySelector('tr[data-lancamento="' + pedido + '"]');
    if (linha) {
      corrigir(linha);
      linha.scrollIntoView({ block: "center" });
    }
  }
})();
