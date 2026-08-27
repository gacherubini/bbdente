/* O campo "Quem vem" da agenda.

   O campo de busca E o campo de nome. Escolher da lista grava `paciente_id`;
   digitar qualquer coisa e seguir grava `nome_avulso` com o que foi digitado.
   Uma pergunta, duas saidas — sem "esta paciente ja existe? [sim] [nao]" antes
   de a pessoa poder escrever.

   Sem este arquivo o formulario continua funcionando: o campo vira texto livre
   e grava avulso. Nada aqui decide regra — quem decide e a service. */
(function () {
  "use strict";

  var campo = document.getElementById("agenda-nome");
  var escondido = document.getElementById("agenda-paciente-id");
  var lista = document.getElementById("agenda-achados");
  var ajuda = document.getElementById("agenda-quem-ajuda");
  var telefone = document.getElementById("agenda-telefone");
  if (!campo || !escondido || !lista) return;

  var achados = {};
  var pedido = null;

  function limparEscolha() {
    escondido.value = "";
    if (ajuda) {
      ajuda.textContent =
        "Se não achar na lista, escreva assim mesmo — o horário é marcado sem cadastro.";
    }
  }

  function escolher(paciente) {
    escondido.value = String(paciente.id);
    campo.value = paciente.nome;
    if (telefone && !telefone.value && paciente.telefone) {
      telefone.value = paciente.telefone;
    }
    if (ajuda) {
      ajuda.textContent = "Da lista de pacientes — o horário fica na ficha dela.";
    }
  }

  function desenhar(pacientes) {
    achados = {};
    lista.innerHTML = "";
    pacientes.forEach(function (paciente) {
      achados[paciente.nome] = paciente;
      var opcao = document.createElement("option");
      opcao.value = paciente.nome;
      /* O codigo antigo ajuda a distinguir duas MARIA SILVA. */
      opcao.label = paciente.codigo_legado || "";
      lista.appendChild(opcao);
    });
  }

  function procurar() {
    var termo = campo.value.trim();
    /* Um nome pela metade nao e busca: e o comeco do que ela esta digitando. */
    if (termo.length < 3) {
      desenhar([]);
      return;
    }
    if (pedido) pedido.abort();
    pedido = new AbortController();
    fetch("/api/pacientes?q=" + encodeURIComponent(termo), {
      signal: pedido.signal,
      headers: { Accept: "application/json" }
    })
      .then(function (r) {
        return r.ok ? r.json() : { pacientes: [] };
      })
      .then(function (dados) {
        desenhar(dados.pacientes || []);
      })
      .catch(function () {
        /* Busca que falha nao pode travar a marcacao: o campo continua sendo
           texto livre, e o horario e gravado avulso. */
        desenhar([]);
      });
  }

  campo.addEventListener("input", function () {
    var escolhida = achados[campo.value];
    if (escolhida) {
      escolher(escolhida);
      return;
    }
    limparEscolha();
    procurar();
  });
})();
