/* BDDente — painel de lancamento, ao lado do odontograma.
 *
 * A tela SUGERE, nunca impede: o escopo e as regioes vem pre-marcados conforme o
 * habito da dentista (calculado do historico na migracao), e ela pode mudar tudo.
 * Qualquer tratamento pode ir em qualquer regiao — o historico real mostra o
 * mesmo tratamento em escopos diferentes.
 */
(function () {
  "use strict";

  var estadoInicial = JSON.parse(document.getElementById("estado-inicial").textContent);
  var catalogo = JSON.parse(document.getElementById("catalogo").textContent);

  var porId = {};
  catalogo.forEach(function (categoria) {
    categoria.procedimentos.forEach(function (p) { porId[p.id] = p; });
  });

  var el = function (id) { return document.getElementById(id); };
  var alvo = { dente: null, regiao: null };
  var repetindo = false;

  // Na boca em branco (menu Odontograma) ainda nao ha paciente: quem recebe o
  // tratamento e o rascunho, que so grava no fim. Com paciente, vai direto.
  var rascunho = window.Rascunho || null;

  var odontograma = window.Odontograma.montar({
    alvo: "odontograma",
    estado: estadoInicial,
    aoClicar: function (clique) {
      if (repetindo) {
        alvo = clique;
        enviar();
        return;
      }
      alvo = clique;
      mostrarAlvo();
      if (elEscopo() === "REGIOES") marcarSomente([clique.regiao]);
      atualizarBotoes();
    }
  });

  function elEscopo() {
    var escolhido = document.querySelector('input[name="escopo"]:checked');
    return escolhido ? escolhido.value : "REGIOES";
  }

  function regioesMarcadas() {
    return Array.prototype.slice
      .call(document.querySelectorAll('input[name="regiao"]:checked'))
      .map(function (c) { return c.value; });
  }

  function marcarSomente(valores) {
    document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
      caixa.checked = valores.indexOf(caixa.value) !== -1;
    });
  }

  function mostrarAlvo() {
    if (alvo.dente === null) {
      el("painel-alvo").textContent = "Clique num dente para começar";
      return;
    }
    var dente = estadoInicial.dentes[alvo.dente];
    var nomeOclusal = dente && dente.anterior ? "Incisal" : "Oclusal";
    el("rotulo-oclusal").textContent = nomeOclusal;
    el("painel-alvo").innerHTML =
      "Dente <b>" + alvo.dente + "</b>" +
      (elEscopo() === "REGIOES" && alvo.regiao
        ? " · " + (alvo.regiao === "OCLUSAL" ? nomeOclusal : alvo.regiao.toLowerCase())
        : "");
  }

  function atualizarBotoes() {
    var procedimento = el("painel-procedimento").value;
    var escopo = elEscopo();
    var temAlvo = escopo === "BOCA" || alvo.dente !== null;
    var temRegiao = escopo !== "REGIOES" || regioesMarcadas().length > 0;
    var pronto = Boolean(procedimento) && temAlvo && temRegiao;
    el("painel-lancar").disabled = !pronto;
    el("painel-repetir").disabled = !Boolean(procedimento);
    el("painel-regioes").hidden = escopo !== "REGIOES";
  }

  // --- categoria filtra os tratamentos ---
  el("painel-categoria").addEventListener("change", function () {
    var categoria = this.value;
    var seletor = el("painel-procedimento");
    seletor.disabled = !categoria;
    seletor.value = "";
    Array.prototype.slice.call(seletor.options).forEach(function (opcao) {
      if (!opcao.value) return;
      opcao.hidden = opcao.getAttribute("data-categoria") !== categoria;
    });
    atualizarBotoes();
  });

  // --- escolher o tratamento pre-marca o habito dela ---
  el("painel-procedimento").addEventListener("change", function () {
    var procedimento = porId[this.value];
    if (procedimento) {
      var radio = document.querySelector(
        'input[name="escopo"][value="' + procedimento.escopo_sugerido + '"]'
      );
      if (radio) radio.checked = true;
      if (procedimento.escopo_sugerido === "REGIOES") {
        var sugeridas = procedimento.regioes_sugeridas.slice();
        // a regiao que ela acabou de clicar tem prioridade sobre a sugestao
        if (alvo.regiao && sugeridas.indexOf(alvo.regiao) === -1) sugeridas = [alvo.regiao];
        marcarSomente(sugeridas);
      }
    }
    mostrarAlvo();
    atualizarBotoes();
  });

  document.querySelectorAll('input[name="escopo"]').forEach(function (radio) {
    radio.addEventListener("change", function () { mostrarAlvo(); atualizarBotoes(); });
  });
  document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
    caixa.addEventListener("change", atualizarBotoes);
  });

  // --- enviar ---
  function mostrarErro(texto) {
    var caixa = el("painel-erro");
    caixa.textContent = texto;
    caixa.hidden = !texto;
  }

  function gravarNoServidor(corpo) {
    corpo.paciente_id = estadoInicial.paciente.id;
    corpo.numero_odontograma = estadoInicial.odontograma.numero;
    return fetch("/api/lancamento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo)
    })
      .then(function (resposta) {
        return resposta.json().then(function (dados) {
          if (!resposta.ok) throw new Error(dados.detail || "não foi possível lançar");
          return dados.estado;
        });
      });
  }

  function enviar() {
    var escopo = elEscopo();
    var valorBruto = el("painel-valor").value.trim().replace(/\./g, "").replace(",", ".");
    var corpo = {
      procedimento_id: parseInt(el("painel-procedimento").value, 10),
      escopo: escopo,
      dente: escopo === "BOCA" ? null : alvo.dente,
      regioes: escopo === "REGIOES" ? regioesMarcadas() : [],
      status: document.querySelector('input[name="status"]:checked').value,
      data: el("painel-data").value || null,
      valor: valorBruto || null,
      observacao: el("painel-observacao").value.trim() || null
    };

    el("painel-lancar").disabled = true;
    mostrarErro("");

    (rascunho ? rascunho.adicionar(corpo) : gravarNoServidor(corpo))
      .then(function (estado) {
        estadoInicial = estado;
        odontograma.atualizar(estado);
        if (!repetindo) {
          alvo = { dente: null, regiao: null };
          mostrarAlvo();
        }
        atualizarBotoes();
      })
      .catch(function (erro) {
        mostrarErro(erro.message);
        atualizarBotoes();
      });
  }

  el("painel-lancar").addEventListener("click", enviar);

  // --- repetir em outro dente ---
  el("painel-repetir").addEventListener("click", function () {
    repetindo = true;
    el("painel-dica").hidden = false;
    el("painel").classList.add("repetindo");
  });
  el("painel-parar-repetir").addEventListener("click", function (evento) {
    evento.preventDefault();
    repetindo = false;
    el("painel-dica").hidden = true;
    el("painel").classList.remove("repetindo");
  });

  // O rascunho pinta pelo servidor: entregamos a ele como redesenhar a boca.
  if (rascunho) {
    rascunho.conectar(function (estado) {
      estadoInicial = estado;
      odontograma.atualizar(estado);
    });
  }

  mostrarAlvo();
  atualizarBotoes();
})();
