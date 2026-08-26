/* BDDente — corrigir um lancamento direto na linha do historico.
 *
 * Corrige situacao, data, valor e observacao. Dente, regiao e procedimento nao
 * entram: trocar o alvo nao e correcao, e outro tratamento.
 *
 * Quando o servidor devolve o desenho novo, este arquivo avisa a pagina por um
 * evento em vez de mexer no odontograma direto — quem sabe desenhar e o
 * painel.js, e duas mãos no mesmo SVG e conflito esperando acontecer.
 */
(function () {
  "use strict";

  var tabela = document.querySelector(".titulo-historico + table");
  if (!tabela) return;

  var editando = null;

  function moeda(bruto) {
    var numero = Number(bruto);
    if (!isFinite(numero)) return bruto;
    return numero.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/, ".");
  }

  function fechar() {
    if (!editando) return;
    editando.linha.parentNode.removeChild(editando.formulario);
    editando.linha.hidden = false;
    editando = null;
  }

  function celula(conteudo, alinhar) {
    var td = document.createElement("td");
    if (alinhar) td.style.textAlign = alinhar;
    td.appendChild(conteudo);
    return td;
  }

  function campo(tipo, valor, extras) {
    var entrada = document.createElement("input");
    entrada.type = tipo;
    entrada.value = valor || "";
    Object.keys(extras || {}).forEach(function (chave) {
      entrada.setAttribute(chave, extras[chave]);
    });
    return entrada;
  }

  function abrir(linha) {
    fechar();

    var dados = linha.dataset;
    var formulario = document.createElement("tr");
    formulario.className = "linha-editando";

    var data = campo("date", dados.data);
    var situacao = document.createElement("select");
    [["PLANEJADO", "Planejado"], ["REALIZADO", "Realizado"]].forEach(function (par) {
      var opcao = document.createElement("option");
      opcao.value = par[0];
      opcao.textContent = par[1];
      if (par[0] === dados.status) opcao.selected = true;
      situacao.appendChild(opcao);
    });
    var valor = campo("text", moeda(dados.valor), { inputmode: "decimal" });
    var observacao = campo("text", dados.observacao, { placeholder: "observação" });

    var acoes = document.createElement("div");
    acoes.className = "acoes-linha";
    var salvar = document.createElement("button");
    salvar.type = "button";
    salvar.className = "primario";
    salvar.textContent = "Salvar";
    var cancelar = document.createElement("button");
    cancelar.type = "button";
    cancelar.className = "ligacao";
    cancelar.textContent = "cancelar";
    acoes.appendChild(salvar);
    acoes.appendChild(cancelar);

    formulario.appendChild(celula(data));
    formulario.appendChild(celula(observacao));
    var vazia = document.createElement("td");
    formulario.appendChild(vazia);
    formulario.appendChild(celula(situacao));
    formulario.appendChild(celula(valor, "right"));
    formulario.appendChild(celula(acoes, "right"));

    var erro = document.createElement("tr");
    erro.className = "linha-erro";
    erro.hidden = true;
    var celulaErro = document.createElement("td");
    celulaErro.colSpan = 6;
    erro.appendChild(celulaErro);

    linha.hidden = true;
    linha.parentNode.insertBefore(formulario, linha.nextSibling);
    linha.parentNode.insertBefore(erro, formulario.nextSibling);
    editando = { linha: linha, formulario: formulario };
    data.focus();

    cancelar.addEventListener("click", function () {
      erro.parentNode.removeChild(erro);
      fechar();
    });

    salvar.addEventListener("click", function () {
      salvar.disabled = true;
      celulaErro.textContent = "";
      erro.hidden = true;

      var limpo = valor.value.trim().replace(/\./g, "").replace(",", ".");
      fetch("/api/lancamento/" + linha.dataset.lancamento, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: situacao.value,
          data: data.value || null,
          valor: limpo || "0",
          observacao: observacao.value.trim() || null
        })
      })
        .then(function (resposta) {
          return resposta.json().then(function (corpo) {
            if (!resposta.ok) throw new Error(corpo.detail || "não foi possível salvar");
            return corpo;
          });
        })
        .then(function (corpo) {
          document.dispatchEvent(
            new CustomEvent("bddente:estado", { detail: corpo.estado })
          );
          // A linha da tabela e reescrita a partir do que foi salvo; recarregar a
          // pagina inteira perderia a rolagem no meio do historico.
          linha.dataset.status = situacao.value;
          linha.dataset.valor = limpo || "0";
          linha.dataset.data = data.value || "";
          linha.dataset.observacao = observacao.value.trim();
          linha.querySelector(".col-data").textContent = data.value
            ? data.value.split("-").reverse().join("/")
            : "—";
          linha.querySelector(".col-situacao").textContent =
            situacao.value === "REALIZADO" ? "Realizado" : "Planejado";
          linha.querySelector(".col-valor").textContent = "R$ " + moeda(limpo || "0");
          erro.parentNode.removeChild(erro);
          fechar();
        })
        .catch(function (falha) {
          celulaErro.textContent = falha.message;
          erro.hidden = false;
          salvar.disabled = false;
        });
    });
  }

  tabela.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".editar-lancamento");
    if (!botao) return;
    abrir(botao.closest("tr"));
  });
})();
