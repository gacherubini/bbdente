/* BDDente — excluir um tratamento direto na linha da tela do dia.
 *
 * A exclusao e logica no servidor (`excluido_em`); daqui ela e so um DELETE. O
 * que este arquivo cuida e de nao deixar isso acontecer por engano: o clique no
 * "x" nao exclui nada, troca a linha por uma pergunta que DIZ o que vai sumir.
 *
 * Nada de confirm() nativo: ele trava o navegador, nao cabe o nome do
 * tratamento e destoa do resto do app — a edicao na linha do historico
 * (historico.js) ja resolve confirmacao assim.
 *
 * Depois de excluir, a pagina recarrega. Os tres cartoes do topo e o subtotal de
 * cada paciente sao somados no servidor; refazer essa conta aqui seria a mesma
 * regra escrita em dois lugares, e um dia elas discordam.
 */
(function () {
  "use strict";

  var COLUNAS = 4;
  var perguntando = null;

  function alvo(linha) {
    var dados = linha.dataset;
    var onde = dados.dente ? "do dente " + dados.dente : "da boca toda";
    return dados.procedimento + " " + onde;
  }

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

  function perguntar(linha) {
    fechar();

    var pergunta = document.createElement("tr");
    pergunta.className = "linha-editando";

    var celula = document.createElement("td");
    celula.colSpan = COLUNAS;

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
          window.location.reload();
        })
        .catch(function (falha) {
          texto.textContent = falha.message;
          excluir.disabled = false;
        });
    });
  }

  document.addEventListener("click", function (evento) {
    var acionado = evento.target.closest(".excluir-lancamento");
    if (!acionado) return;
    perguntar(acionado.closest("tr"));
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") fechar();
  });
})();
