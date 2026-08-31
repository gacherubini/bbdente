/* BDDente — painel de lancamento e de correcao, ao lado do odontograma.
 *
 * A tela SUGERE, nunca impede: o escopo e as regioes vem pre-marcados conforme o
 * habito da dentista (calculado do historico na migracao), e ela pode mudar tudo.
 * Qualquer tratamento pode ir em qualquer regiao — o historico real mostra o
 * mesmo tratamento em escopos diferentes.
 *
 * Desde 31/08/2026 este painel tambem CORRIGE. Quando o historico manda um
 * lancamento por `bddente:corrigir`, os mesmos campos abrem preenchidos com o que
 * esta gravado e o botao passa a mandar PATCH. E o painel, e nao um formulario na
 * linha da tabela, porque so aqui existem dente e faces para escolher — e porque
 * a mesma tela que monta um tratamento e a que sabe remonta-lo.
 */
(function () {
  "use strict";

  var estadoInicial = JSON.parse(document.getElementById("estado-inicial").textContent);
  var catalogo = JSON.parse(document.getElementById("catalogo").textContent);

  var porId = {};
  // De qual categoria e cada tratamento: a correcao abre com o tratamento ja
  // escolhido, e o <select> de tratamento so mostra os da categoria selecionada.
  var categoriaDe = {};
  catalogo.forEach(function (categoria) {
    categoria.procedimentos.forEach(function (p) {
      porId[p.id] = p;
      categoriaDe[p.id] = categoria.id;
    });
  });

  var el = function (id) { return document.getElementById(id); };
  var alvo = { dente: null, regiao: null };
  var repetindo = false;
  // O id do lancamento sendo corrigido, ou null quando o painel esta lancando.
  var corrigindo = null;
  // A dentista mexeu no VALOR com a propria mao: a sugestao para de escrever ali.
  var valorEditadoAMao = false;

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
      /* Clicar em outra face DO MESMO dente soma; clicar em outro dente
         recomeca. A selecao pertence a um dente — levar as faces do 36 para o
         37 lancaria tratamento em face que ninguem mandou. */
      var mesmoDente = alvo.dente !== null && alvo.dente === clique.dente;
      alvo = clique;
      mostrarAlvo();
      if (elEscopo() === "REGIOES") {
        if (mesmoDente) alternarRegiao(clique.regiao);
        else marcarSomente([clique.regiao]);
      }
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

  /* Liga ou desliga uma face sem mexer nas outras. Clicar de novo na mesma
     face desmarca — desfazer tem de ser o mesmo gesto que fazer. */
  function alternarRegiao(regiao) {
    document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
      if (caixa.value === regiao) caixa.checked = !caixa.checked;
    });
  }

  function marcarSomente(valores) {
    document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
      caixa.checked = valores.indexOf(caixa.value) !== -1;
    });
  }

  // --- valor sugerido pela tabela de preco ---------------------------------

  /* Quantas vezes o preco do tratamento conta.

     Restauracao de tres faces custa tres vezes a de uma. Em BOCA e DENTE nao ha
     face a contar: vale uma vez. */
  function quantasFaces() {
    if (elEscopo() !== "REGIOES") return 1;
    return Math.max(1, regioesMarcadas().length);
  }

  function formatarMoeda(numero) {
    return numero.toFixed(2).replace(".", ",");
  }

  /* Preenche VALOR com preco x faces.

     Nao sobrescreve o que a dentista digitou: quem da desconto e ela, e apagar
     um desconto porque ela marcou mais uma face seria trocar a decisao dela pela
     da tabela. O sinal de "digitou a mao" so se apaga quando ela troca de
     tratamento, que e quando o valor anterior deixa de fazer sentido. */
  function sugerirValor() {
    if (valorEditadoAMao) return;
    var procedimento = porId[el("painel-procedimento").value];
    // `preco` nulo e 'sem tabela de preco', que nao e o mesmo que de graca:
    // deixamos o campo vazio para ela digitar, em vez de mentir um R$ 0,00.
    if (!procedimento || !procedimento.preco) {
      el("painel-valor").value = "";
      return;
    }
    var unitario = Number(procedimento.preco);
    if (!isFinite(unitario)) return;
    el("painel-valor").value = formatarMoeda(unitario * quantasFaces());
  }

  function mostrarAlvo() {
    // Durante a correcao o alvo pode ser a boca toda, que nao tem dente: sem
    // isto o painel diria "clique num dente" no meio de uma correcao aberta.
    if (alvo.dente === null && corrigindo && elEscopo() === "BOCA") {
      el("painel-alvo").innerHTML = "Corrigindo · <b>boca toda</b>";
      return;
    }
    if (alvo.dente === null) {
      el("painel-alvo").textContent = "Clique num dente para começar";
      return;
    }
    var dente = estadoInicial.dentes[alvo.dente];
    var nomeOclusal = dente && dente.anterior ? "Incisal" : "Oclusal";
    el("rotulo-oclusal").textContent = nomeOclusal;
    el("painel-alvo").innerHTML =
      (corrigindo ? "Corrigindo · " : "") +
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
    // Repetir em varios dentes e o gesto de lancar em serie; no meio de uma
    // correcao ele so teria como significar "corrija este mesmo lancamento de
    // novo", que nao quer dizer nada.
    el("painel-repetir").disabled = Boolean(corrigindo) || !procedimento;
    el("painel-regioes").hidden = escopo !== "REGIOES";
    destacarNoDesenho();
    sugerirValor();
  }

  /* Devolve ao desenho o que o painel sabe estar selecionado.

     Fica aqui dentro de proposito: `atualizarBotoes` e o unico ponto por onde
     passam TODAS as mudancas de selecao — clique no dente, troca de escopo,
     caixa de regiao, tratamento sugerido. Chamar de fora, em cada um deles,
     era esquecer um. Antes disso o desenho nao respondia a nada: marcar
     "Vestibular" no painel nao acendia nada na boca. */
  function destacarNoDesenho() {
    if (!odontograma) return;
    var escopo = elEscopo();
    if (escopo === "BOCA" || alvo.dente === null) {
      odontograma.destacar(null);
      return;
    }
    odontograma.destacar(
      alvo.dente, escopo === "REGIOES" ? regioesMarcadas() : []
    );
  }

  // --- categoria filtra os tratamentos ---

  /* Deixa visiveis so os tratamentos da categoria. Vive fora do ouvinte porque a
     correcao tambem precisa dele: abrir um lancamento gravado e escolher a
     categoria dele e o tratamento dele, nessa ordem. */
  function filtrarPorCategoria(categoria) {
    var seletor = el("painel-procedimento");
    seletor.disabled = !categoria;
    Array.prototype.slice.call(seletor.options).forEach(function (opcao) {
      if (!opcao.value) return;
      opcao.hidden = opcao.getAttribute("data-categoria") !== categoria;
    });
  }

  el("painel-categoria").addEventListener("change", function () {
    filtrarPorCategoria(this.value);
    el("painel-procedimento").value = "";
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
      /* A sugestao do tratamento so vale enquanto ela nao montou a selecao.
         Marcou duas ou mais faces a mao e SO ENTAO escolheu o tratamento? O que
         ela montou vence — apagar isso seria perder o trabalho dela em silencio. */
      if (procedimento.escopo_sugerido === "REGIOES" && regioesMarcadas().length > 1) {
        // nao mexe: a selecao e dela
      } else if (procedimento.escopo_sugerido === "REGIOES") {
        var sugeridas = procedimento.regioes_sugeridas.slice();
        // a regiao que ela acabou de clicar tem prioridade sobre a sugestao
        if (alvo.regiao && sugeridas.indexOf(alvo.regiao) === -1) sugeridas = [alvo.regiao];
        marcarSomente(sugeridas);
      }
    }
    valorEditadoAMao = false;
    mostrarAlvo();
    atualizarBotoes();
  });

  // Digitou no VALOR: a sugestao cala a boca ate ela trocar de tratamento.
  el("painel-valor").addEventListener("input", function () {
    valorEditadoAMao = true;
  });

  document.querySelectorAll('input[name="escopo"]').forEach(function (radio) {
    radio.addEventListener("change", function () { mostrarAlvo(); atualizarBotoes(); });
  });
  document.querySelectorAll('input[name="regiao"]').forEach(function (caixa) {
    caixa.addEventListener("change", atualizarBotoes);
  });

  // --- aviso que passa sozinho ---

  /* Confirma o que foi lancado sem pedir clique.

     Uma caixa com OK custaria um clique em CADA lancamento, e marcar dente atras
     de dente e o caminho de todo dia. O texto diz o que foi gravado para o erro
     aparecer sozinho — "lancado" sem dizer o que nao ajuda ninguem. */
  var avisoAtual = null;

  function avisar(texto) {
    if (avisoAtual) avisoAtual.remove();
    var caixa = document.createElement("div");
    caixa.className = "aviso-flutuante";
    caixa.setAttribute("role", "status");
    caixa.textContent = texto;
    document.body.appendChild(caixa);
    avisoAtual = caixa;
    setTimeout(function () {
      caixa.classList.add("saindo");
      setTimeout(function () {
        caixa.remove();
        if (avisoAtual === caixa) avisoAtual = null;
      }, 300);
    }, 3500);
  }

  function descreverLancamento(corpo) {
    var procedimento = porId[corpo.procedimento_id];
    var nome = procedimento ? procedimento.nome : "tratamento";
    var onde = corpo.escopo === "BOCA" ? "boca toda" : "dente " + corpo.dente;
    var quanto = corpo.valor
      ? " · R$ " + formatarMoeda(Number(corpo.valor))
      : "";
    return nome + " — " + onde + quanto;
  }

  // --- enviar ---
  function mostrarErro(texto) {
    var caixa = el("painel-erro");
    caixa.textContent = texto;
    caixa.hidden = !texto;
  }

  function pedir(url, metodo, corpo, oQueFalhou) {
    return fetch(url, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo)
    })
      .then(function (resposta) {
        return resposta.json().then(function (dados) {
          if (!resposta.ok) throw new Error(dados.detail || oQueFalhou);
          return dados.estado;
        });
      });
  }

  function gravarNoServidor(corpo) {
    corpo.paciente_id = estadoInicial.paciente.id;
    corpo.numero_odontograma = estadoInicial.odontograma.numero;
    return pedir("/api/lancamento", "POST", corpo, "não foi possível lançar");
  }

  /* O corpo da correcao e o MESMO do lancamento, e e de proposito: e mandando o
     alvo inteiro que o servidor entende que ela quer trocar o alvo, e nao so o
     valor. Quem manda menos que isso — se um dia voltar a haver edicao curta —
     omite `escopo`, e o alvo fica como esta. */
  function corrigirNoServidor(corpo) {
    return pedir(
      "/api/lancamento/" + corrigindo, "PATCH", corpo, "não foi possível salvar"
    );
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

    // Guardado agora: `pararCorrecao()` limpa `corrigindo` antes de a resposta
    // terminar de ser tratada, e o aviso ainda precisa saber o que aconteceu.
    var corrigia = Boolean(corrigindo);
    var enviando = rascunho
      ? rascunho.adicionar(corpo)
      : (corrigia ? corrigirNoServidor(corpo) : gravarNoServidor(corpo));

    enviando
      .then(function (estado) {
        estadoInicial = estado;
        odontograma.atualizar(estado);
        avisar(
          (corrigia
            ? "Corrigido: "
            : rascunho ? "Adicionado ao atendimento: " : "Lançado: ") +
          descreverLancamento(corpo)
        );
        // O historico e a conta do dia mudaram; quem sabe redesenhar a tabela e
        // o historico.js. No rascunho nao ha historico — ainda nao ha paciente.
        if (!rascunho) document.dispatchEvent(new CustomEvent("bddente:mudou"));
        if (corrigia) {
          pararCorrecao();
        } else if (!repetindo) {
          alvo = { dente: null, regiao: null };
          valorEditadoAMao = false;
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
  function pararRepetir() {
    repetindo = false;
    el("painel-dica").hidden = true;
    el("painel").classList.remove("repetindo");
  }

  el("painel-repetir").addEventListener("click", function () {
    repetindo = true;
    el("painel-dica").hidden = false;
    el("painel").classList.add("repetindo");
  });
  el("painel-parar-repetir").addEventListener("click", function (evento) {
    evento.preventDefault();
    pararRepetir();
  });

  // --- corrigir um lancamento gravado ---

  var ROTULO_LANCAR = el("painel-lancar").textContent.trim();

  function foraDoCatalogo(dados) {
    var opcao = document.createElement("option");
    opcao.value = String(dados.procedimentoId);
    opcao.textContent = dados.procedimento + " (fora do catálogo)";
    opcao.setAttribute("data-fora-do-catalogo", "1");
    return opcao;
  }

  /* Abre no painel um lancamento que ja existe, com tudo o que esta gravado.

     Os campos sao preenchidos direto, sem disparar `change`: o ouvinte do
     tratamento pre-marca o habito da dentista, e aqui isso apagaria as faces
     REAIS do lancamento e as trocaria por uma sugestao. O que esta no prontuario
     vence a sugestao — sempre. */
  function iniciarCorrecao(dados) {
    corrigindo = dados.lancamento;
    pararRepetir();

    var categoria = categoriaDe[dados.procedimentoId];
    if (categoria === undefined) {
      /* Tratamento inativado sai do catalogo, mas nao sai do prontuario de quem
         o recebeu. Sem uma opcao para ele o <select> abriria vazio e o botao de
         salvar ficaria desligado — a correcao seria impossivel justamente na
         linha antiga, que e onde ela mais faz falta. */
      var seletor = el("painel-procedimento");
      seletor.appendChild(foraDoCatalogo(dados));
      seletor.disabled = false;
      el("painel-categoria").value = "";
    } else {
      el("painel-categoria").value = String(categoria);
      filtrarPorCategoria(String(categoria));
    }
    el("painel-procedimento").value = String(dados.procedimentoId);

    var escopo = document.querySelector(
      'input[name="escopo"][value="' + dados.escopo + '"]'
    );
    if (escopo) escopo.checked = true;
    marcarSomente(dados.regioes);
    alvo = { dente: dados.dente, regiao: dados.regioes[0] || null };

    var situacao = document.querySelector(
      'input[name="status"][value="' + dados.status + '"]'
    );
    if (situacao) situacao.checked = true;
    el("painel-data").value = dados.data;
    el("painel-valor").value = formatarMoeda(Number(dados.valor || 0));
    el("painel-observacao").value = dados.observacao;
    /* O valor gravado e uma decisao que ja foi tomada — desconto, convenio, o que
       for. A sugestao da tabela de preco nao pode reescrever o prontuario so
       porque o painel abriu. Se ela trocar de tratamento, a sugestao volta. */
    valorEditadoAMao = true;

    el("painel").classList.add("corrigindo");
    el("painel-corrigindo").hidden = false;
    el("painel-lancar").textContent = "Salvar correção";
    mostrarErro("");
    mostrarAlvo();
    atualizarBotoes();
  }

  /* Devolve o painel ao estado de lancar. Avisa a tabela para ela tirar o
     destaque da linha — o painel nao mexe em linha de tabela, e a tabela nao
     mexe no desenho. */
  function pararCorrecao() {
    corrigindo = null;
    document.querySelectorAll("[data-fora-do-catalogo]").forEach(function (opcao) {
      opcao.remove();
    });
    el("painel").classList.remove("corrigindo");
    el("painel-corrigindo").hidden = true;
    el("painel-lancar").textContent = ROTULO_LANCAR;
    alvo = { dente: null, regiao: null };
    valorEditadoAMao = false;
    el("painel-observacao").value = "";
    mostrarErro("");
    mostrarAlvo();
    atualizarBotoes();
    document.dispatchEvent(new CustomEvent("bddente:correcao-fim"));
  }

  document.addEventListener("bddente:corrigir", function (evento) {
    iniciarCorrecao(evento.detail);
  });
  el("painel-parar-correcao").addEventListener("click", function (evento) {
    evento.preventDefault();
    pararCorrecao();
  });

  // O rascunho pinta pelo servidor: entregamos a ele como redesenhar a boca.
  if (rascunho) {
    rascunho.conectar(function (estado) {
      estadoInicial = estado;
      odontograma.atualizar(estado);
    });
  }

  // Quem edita uma linha do historico avisa por aqui: quem sabe desenhar e este
  // arquivo, e duas maos no mesmo SVG e conflito esperando acontecer.
  document.addEventListener("bddente:estado", function (evento) {
    estadoInicial = evento.detail;
    odontograma.atualizar(evento.detail);
  });

  mostrarAlvo();
  atualizarBotoes();
})();
