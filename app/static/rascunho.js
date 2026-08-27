/* BDDente — atendimento sem paciente ainda.
 *
 * Guarda os tratamentos marcados na boca em branco e so no fim, quando se sabe
 * de quem e, manda tudo de uma vez para /api/atendimento.
 *
 * Duas regras que este arquivo NAO decide, de proposito:
 *  - qual cor vence quando dois tratamentos caem na mesma regiao: quem pinta e
 *    /api/odontograma/previa, no servidor, onde ha teste;
 *  - anatomia do dente: vem pronta do servidor, como em odontograma.js.
 *
 * Enquanto o atendimento nao e concluido, ele vive so aqui e no armazenamento
 * local DESTE navegador. Nenhuma linha vai para o banco antes do fim.
 */
(function () {
  "use strict";

  var CHAVE = "bddente:atendimento";

  var el = function (id) { return document.getElementById(id); };
  var catalogo = JSON.parse(document.getElementById("catalogo").textContent);
  var nomeDoProcedimento = {};
  catalogo.forEach(function (categoria) {
    categoria.procedimentos.forEach(function (p) {
      nomeDoProcedimento[p.id] = p.nome;
    });
  });

  var itens = [];
  var repintar = function () {};

  // --- memoria deste navegador -------------------------------------------------

  function guardar() {
    try {
      window.localStorage.setItem(CHAVE, JSON.stringify(itens));
    } catch (erro) {
      // Navegador sem armazenamento (janela anonima, cota cheia) nao pode
      // derrubar o atendimento: ele continua valendo na memoria da pagina.
    }
  }

  function recuperar() {
    try {
      var bruto = window.localStorage.getItem(CHAVE);
      return bruto ? JSON.parse(bruto) : [];
    } catch (erro) {
      return [];
    }
  }

  function esquecer() {
    try {
      window.localStorage.removeItem(CHAVE);
    } catch (erro) {
      /* idem */
    }
  }

  // --- previa: o servidor pinta ------------------------------------------------

  function pedirJson(url, corpo, metodo) {
    return fetch(url, {
      method: metodo || "POST",
      headers: { "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo)
    }).then(function (resposta) {
      return resposta.json().then(function (dados) {
        if (!resposta.ok) throw new Error(dados.detail || "não foi possível continuar");
        return { status: resposta.status, dados: dados };
      });
    });
  }

  function previa() {
    return pedirJson("/api/odontograma/previa", { itens: itens }).then(function (r) {
      return r.dados;
    });
  }

  // --- lista do atendimento ----------------------------------------------------

  function descrever(item) {
    var onde =
      item.escopo === "BOCA"
        ? "boca toda"
        : item.escopo === "DENTE"
          ? "dente " + item.dente
          : "dente " + item.dente + " · " + item.regioes.join(", ").toLowerCase();
    var situacao = item.status === "REALIZADO" ? "realizado" : "planejado";
    return (nomeDoProcedimento[item.procedimento_id] || "tratamento") +
      " — " + onde + " (" + situacao + ")";
  }

  function desenharLista() {
    var lista = el("atendimento-itens");
    lista.innerHTML = "";
    itens.forEach(function (item, indice) {
      var linha = document.createElement("li");
      var texto = document.createElement("span");
      texto.textContent = descrever(item);
      var tirar = document.createElement("button");
      tirar.type = "button";
      tirar.className = "atendimento-tirar";
      tirar.setAttribute("aria-label", "tirar do atendimento");
      tirar.textContent = "×";
      tirar.addEventListener("click", function () { remover(indice); });
      linha.appendChild(texto);
      linha.appendChild(tirar);
      lista.appendChild(linha);
    });
    el("atendimento-vazio").hidden = itens.length > 0;
    el("atendimento-concluir").disabled = itens.length === 0;
    el("atendimento-concluir").textContent =
      itens.length === 0
        ? "Concluir atendimento"
        : "Concluir atendimento (" + itens.length + ")";
    el("janela-quantos").textContent = String(itens.length);
    el("janela-palavra").textContent =
      itens.length === 1 ? "tratamento vai" : "tratamentos vão";
  }

  function remover(indice) {
    var guardados = itens.slice();
    itens.splice(indice, 1);
    guardar();
    desenharLista();
    previa()
      .then(repintar)
      .catch(function () {
        // Se o servidor recusar o que sobrou, devolve a lista como estava: melhor
        // manter o atendimento inteiro do que perder um item sem aviso.
        itens = guardados;
        guardar();
        desenharLista();
      });
  }

  function adicionar(corpo) {
    itens.push(corpo);
    guardar();
    return previa().then(function (estado) {
      desenharLista();
      return estado;
    }).catch(function (erro) {
      itens.pop();
      guardar();
      desenharLista();
      throw erro;
    });
  }

  // --- janela de conclusao -----------------------------------------------------

  function mostrarErro(texto) {
    var caixa = el("janela-erro");
    caixa.textContent = texto || "";
    caixa.hidden = !texto;
  }

  function abrirJanela() {
    el("janela-concluir").hidden = false;
    el("janela-busca").focus();
  }

  function fecharJanela() {
    el("janela-concluir").hidden = true;
    mostrarErro("");
  }

  function agendamentoDaTela() {
    /* De qual horario da agenda veio este atendimento, quando veio de um.
       Vazio e o caso normal — a boca em branco tambem se abre sozinha. */
    var janela = el("janela-concluir");
    var bruto = janela && janela.dataset ? janela.dataset.agendamento : "";
    return bruto ? Number(bruto) : null;
  }

  function concluir(corpo) {
    corpo.agendamento_id = agendamentoDaTela();
    return pedirJson("/api/atendimento", corpo).then(function (r) {
      // 200 com 'parecidos' significa: nao gravei, decide voce.
      if (r.status === 200 && r.dados.parecidos) {
        mostrarParecidos(r.dados.parecidos);
        return;
      }
      esquecer();
      window.location.href = "/odontograma/" + r.dados.paciente_id;
    }).catch(function (erro) {
      mostrarErro(erro.message);
    });
  }

  function mostrarParecidos(parecidos) {
    var caixa = el("janela-parecidos");
    var lista = el("janela-parecidos-lista");
    lista.innerHTML = "";
    parecidos.forEach(function (p) {
      var linha = document.createElement("li");
      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "nome-botao";
      botao.textContent = p.nome + (p.codigo_legado ? " · " + p.codigo_legado : "");
      botao.addEventListener("click", function () {
        concluir({ paciente_id: p.id, itens: itens });
      });
      linha.appendChild(botao);
      lista.appendChild(linha);
    });
    caixa.hidden = false;
    el("janela-cadastrar").textContent = "Cadastrar mesmo assim";
    el("janela-cadastrar").dataset.confirmar = "1";
  }

  // --- busca de paciente na janela ---------------------------------------------

  var buscaPendente = null;

  function buscar(termo) {
    return pedirJson("/api/pacientes?q=" + encodeURIComponent(termo), undefined, "GET")
      .then(function (r) { return r.dados.pacientes; });
  }

  function desenharAchados(pacientes) {
    var lista = el("janela-achados");
    lista.innerHTML = "";
    pacientes.forEach(function (p) {
      var linha = document.createElement("li");
      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "nome-botao";
      botao.innerHTML =
        "<b></b><span class='codigo'></span><span class='janela-data'></span>";
      botao.querySelector("b").textContent = p.nome;
      botao.querySelector(".codigo").textContent = p.codigo_legado || "sem código";
      botao.querySelector(".janela-data").textContent = p.telefone || "";
      botao.addEventListener("click", function () {
        concluir({ paciente_id: p.id, itens: itens });
      });
      linha.appendChild(botao);
      lista.appendChild(linha);
    });
  }

  function ligarBusca() {
    el("janela-busca").addEventListener("input", function () {
      var termo = this.value.trim();
      window.clearTimeout(buscaPendente);
      if (!termo) {
        el("janela-achados").innerHTML = "";
        el("janela-vazio").hidden = true;
        return;
      }
      buscaPendente = window.setTimeout(function () {
        buscar(termo)
          .then(function (pacientes) {
            desenharAchados(pacientes);
            el("janela-vazio").hidden = pacientes.length > 0;
            // O nome digitado na busca ja serve de nome do cadastro novo.
            if (!el("janela-nome").value.trim()) el("janela-nome").value = termo;
          })
          .catch(function (erro) { mostrarErro(erro.message); });
      }, 250);
    });
  }

  function ligarCadastro() {
    el("janela-cadastrar").addEventListener("click", function () {
      var nome = el("janela-nome").value.trim();
      if (!nome) {
        mostrarErro("Digite o nome do paciente.");
        return;
      }
      mostrarErro("");
      var convenio = el("janela-convenio").value;
      concluir({
        novo: {
          nome: nome,
          telefone: el("janela-telefone").value.trim() || null,
          nascimento: el("janela-nascimento").value || null,
          convenio_id: convenio ? parseInt(convenio, 10) : null
        },
        confirmar: this.dataset.confirmar === "1",
        itens: itens
      });
    });
  }

  // --- ligacao com o painel ----------------------------------------------------

  window.Rascunho = {
    /* painel.js entrega aqui como repintar o desenho. */
    conectar: function (aoRepintar) {
      repintar = aoRepintar;
      itens = recuperar();
      desenharLista();
      if (itens.length) {
        previa().then(repintar).catch(function () {
          // Rascunho velho que o servidor nao aceita mais (tratamento apagado do
          // catalogo, por exemplo): comeca limpo em vez de travar a tela.
          itens = [];
          esquecer();
          desenharLista();
        });
      }
    },
    adicionar: adicionar
  };

  el("atendimento-concluir").addEventListener("click", abrirJanela);
  el("janela-voltar").addEventListener("click", fecharJanela);
  ligarBusca();
  ligarCadastro();
  desenharLista();
})();
