/* BDDente — a pergunta que troca a linha antes de excluir um tratamento.
 *
 * Duas telas excluem tratamento: a do dia (`atendimentos.js`) e o historico do
 * odontograma (`historico.js`). A confirmacao mora aqui, e nao em cada uma, para
 * a pergunta ser a mesma nos dois lugares — escrita duas vezes ela vira duas,
 * e um dia uma delas para de dizer o que vai sumir.
 *
 * Nada de confirm() nativo: ele trava o navegador, nao cabe o nome do tratamento
 * e destoa do resto do app. A exclusao e logica no servidor (`excluido_em`);
 * daqui e so um DELETE.
 */
window.Confirmar = (function () {
  "use strict";

  var perguntando = null;

  function fechar() {
    if (!perguntando) return;
    perguntando.pergunta.parentNode.removeChild(perguntando.pergunta);
    perguntando.linha.hidden = false;
    perguntando = null;
  }

  function botao(texto, classe) {
    var elemento = document.createElement("button");
    elemento.type = "button";
    elemento.className = classe;
    elemento.textContent = texto;
    return elemento;
  }

  /* O que vai sumir, em palavras. "Excluir tratamento?" nao deixa ninguem
     perceber que clicou na linha errada — o nome e o dente deixam. */
  function alvo(linha) {
    var dados = linha.dataset;
    var onde = dados.dente ? "do dente " + dados.dente : "da boca toda";
    return (dados.procedimento || "tratamento") + " " + onde;
  }

  /* `colunas` e quantas colunas a tabela tem: a pergunta ocupa a linha inteira,
     e uma tabela de 6 colunas com colspan 4 abre um buraco no meio. */
  function excluirLancamento(linha, opcoes) {
    fechar();
    var colunas = opcoes.colunas;
    var aoConcluir = opcoes.aoConcluir;

    var pergunta = document.createElement("tr");
    pergunta.className = "linha-editando";

    var celula = document.createElement("td");
    celula.colSpan = colunas;

    var texto = document.createElement("span");
    texto.textContent = "Excluir " + alvo(linha) + "?";

    var acoes = document.createElement("div");
    acoes.className = "acoes-linha";
    var excluir = botao("Excluir", "primario");
    var cancelar = botao("cancelar", "ligacao");
    acoes.appendChild(excluir);
    acoes.appendChild(cancelar);

    celula.appendChild(texto);
    celula.appendChild(acoes);
    pergunta.appendChild(celula);

    linha.hidden = true;
    linha.parentNode.insertBefore(pergunta, linha.nextSibling);
    perguntando = { linha: linha, pergunta: pergunta };
    excluir.focus();

    cancelar.addEventListener("click", fechar);

    excluir.addEventListener("click", function () {
      excluir.disabled = true;
      fetch("/api/lancamento/" + linha.dataset.lancamento, { method: "DELETE" })
        .then(function (resposta) {
          if (!resposta.ok) {
            return resposta.json().then(function (corpo) {
              throw new Error(corpo.detail || "não foi possível excluir");
            });
          }
          perguntando = null;
          // O corpo vai junto: o DELETE devolve o desenho sem o tratamento, e
          // quem tem odontograma na tela precisa dele para repintar.
          return resposta.json().then(aoConcluir);
        })
        .catch(function (falha) {
          texto.textContent = falha.message;
          excluir.disabled = false;
        });
    });
  }

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") fechar();
  });

  return { excluirLancamento: excluirLancamento, fechar: fechar };
})();
