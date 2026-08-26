/* BDDente — odontograma.
 *
 * Este arquivo NAO sabe anatomia. Qual parede e mesial, quantos canais o dente
 * tem e em que ordem eles aparecem vem prontos do servidor, em `paredes` e
 * `canais_tela`. A regra de espelhamento mesial/distal vive em
 * app/shared/dentes.py, onde ha teste. Nao a reimplemente aqui.
 */
(function () {
  "use strict";

  var COR = {
    PLANEJADO: "#DC2626",
    REALIZADO: "#16A34A",
    EXISTENTE: "#2563EB"
  };
  var VAZIO = "#FFFFFF";
  var TRACO = "#94A3B8";

  var LADO = 42;      // aresta do quadrado do dente
  var VAO = 8;        // espaco entre dentes vizinhos
  var VAO_LINHA_MEDIA = 22;
  var RAIZ = LADO * 0.42;
  var MIOLO = LADO * 0.30;   // espessura das paredes
  var FAIXA_NUMEROS = 26;

  var estado = null;
  var aoClicar = null;

  function pintar(dente, regiao) {
    var valor = dente.regioes[regiao];
    return valor ? COR[valor] : VAZIO;
  }

  function caminho(pontos, preenchimento, fdi, regiao) {
    return (
      '<path d="' + pontos + '" fill="' + preenchimento + '" stroke="' + TRACO +
      '" stroke-width="1" class="regiao" data-dente="' + fdi +
      '" data-regiao="' + regiao + '"><title>' + regiao + "</title></path>"
    );
  }

  function desenharDente(fdi, dente, raizParaCima) {
    var a = 0, b = LADO, i = MIOLO, j = LADO - MIOLO;
    var partes = "";

    // --- raizes: uma haste por canal, na ordem que o servidor mandou ---
    var canais = dente.canais_tela;
    var passo = LADO / (canais.length + 1);
    for (var k = 0; k < canais.length; k++) {
      var x = passo * (k + 1);
      var base = raizParaCima ? 0 : LADO;
      var ponta = raizParaCima ? -RAIZ : LADO + RAIZ;
      partes += caminho(
        "M" + (x - LADO * 0.07) + "," + base +
        " L" + x + "," + ponta +
        " L" + (x + LADO * 0.07) + "," + base + "Z",
        pintar(dente, canais[k]), fdi, canais[k]
      );
    }

    // --- as 4 paredes: trapezios entre o quadrado externo e o miolo ---
    var p = dente.paredes;
    partes += caminho("M" + a + "," + a + " L" + b + "," + a + " L" + j + "," + i + " L" + i + "," + i + "Z",
      pintar(dente, p.CIMA), fdi, p.CIMA);
    partes += caminho("M" + b + "," + a + " L" + b + "," + b + " L" + j + "," + j + " L" + j + "," + i + "Z",
      pintar(dente, p.DIREITA), fdi, p.DIREITA);
    partes += caminho("M" + b + "," + b + " L" + a + "," + b + " L" + i + "," + j + " L" + j + "," + j + "Z",
      pintar(dente, p.BAIXO), fdi, p.BAIXO);
    partes += caminho("M" + a + "," + b + " L" + a + "," + a + " L" + i + "," + i + " L" + i + "," + j + "Z",
      pintar(dente, p.ESQUERDA), fdi, p.ESQUERDA);

    // --- miolo: onde mastiga (oclusal, ou incisal nos dentes da frente) ---
    partes +=
      '<rect x="' + i + '" y="' + i + '" width="' + (j - i) + '" height="' + (j - i) +
      '" fill="' + pintar(dente, "OCLUSAL") + '" stroke="' + TRACO +
      '" stroke-width="1" class="regiao" data-dente="' + fdi +
      '" data-regiao="OCLUSAL"><title>' +
      (dente.anterior ? "Incisal" : "Oclusal") + "</title></rect>";

    // --- moldura do dente inteiro: escopo DENTE pinta a borda, nao as paredes ---
    if (dente.dente_inteiro) {
      partes +=
        '<rect x="-2" y="-2" width="' + (LADO + 4) + '" height="' + (LADO + 4) +
        '" fill="none" stroke="' + COR[dente.dente_inteiro] +
        '" stroke-width="2.5" rx="3" pointer-events="none"/>';
    }
    // --- marca de condicao existente sem regiao definida ---
    if (dente.condicoes.length && !dente.dente_inteiro) {
      partes +=
        '<circle cx="' + (LADO - 4) + '" cy="4" r="3.5" fill="' + COR.EXISTENTE +
        '" pointer-events="none"><title>' + dente.condicoes.join(", ") + "</title></circle>";
    }
    return partes;
  }

  function desenharFileira(ordem, raizParaCima) {
    var partes = "", marcas = [], x = 0;
    for (var k = 0; k < ordem.length; k++) {
      // o indice 8 e a linha media: respiro entre as duas metades da arcada
      if (k === 8) x += VAO_LINHA_MEDIA;
      var fdi = ordem[k];
      partes +=
        '<g transform="translate(' + x + ',0)" class="dente" data-dente="' + fdi + '">' +
        desenharDente(fdi, estado.dentes[fdi], raizParaCima) + "</g>";
      marcas.push({ x: x + LADO / 2, fdi: fdi });
      x += LADO + VAO;
    }
    return { svg: partes, largura: x - VAO, marcas: marcas };
  }

  var SUPERIOR = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
  var INFERIOR = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];

  function desenhar(alvo) {
    var cima = desenharFileira(SUPERIOR, true);
    var baixo = desenharFileira(INFERIOR, false);
    var largura = Math.max(cima.largura, baixo.largura);
    var yCima = RAIZ + 6;
    var yBaixo = yCima + LADO + FAIXA_NUMEROS + 16;
    var altura = yBaixo + LADO + RAIZ + 10;

    var svg =
      '<svg width="' + (largura + 24) + '" height="' + altura +
      '" viewBox="-12 0 ' + (largura + 24) + " " + altura +
      '" role="img" aria-label="Odontograma">';
    svg += '<g transform="translate(0,' + yCima + ')">' + cima.svg + "</g>";
    svg +=
      '<g font-size="12" font-family="ui-monospace,monospace" fill="#475569" text-anchor="middle">';
    cima.marcas.forEach(function (m) {
      svg += '<text x="' + m.x + '" y="' + (yCima + LADO + 16) + '">' + m.fdi + "</text>";
    });
    baixo.marcas.forEach(function (m) {
      svg += '<text x="' + m.x + '" y="' + (yBaixo - 8) + '">' + m.fdi + "</text>";
    });
    svg += "</g>";
    svg +=
      '<line x1="-8" y1="' + (yCima + LADO + 23) + '" x2="' + (largura + 8) +
      '" y2="' + (yCima + LADO + 23) + '" stroke="#CBD5E1"/>';
    svg += '<g transform="translate(0,' + yBaixo + ')">' + baixo.svg + "</g>";
    svg += "</svg>";
    alvo.innerHTML = svg;
  }

  function montar(opcoes) {
    var alvo = document.getElementById(opcoes.alvo);
    estado = opcoes.estado;
    aoClicar = opcoes.aoClicar || function () {};

    desenhar(alvo);

    alvo.addEventListener("click", function (evento) {
      var parte = evento.target.closest(".regiao");
      if (!parte) return;
      aoClicar({
        dente: parseInt(parte.getAttribute("data-dente"), 10),
        regiao: parte.getAttribute("data-regiao")
      });
    });

    return {
      atualizar: function (novoEstado) {
        estado = novoEstado;
        desenhar(alvo);
      },
      estado: function () {
        return estado;
      }
    };
  }

  window.Odontograma = { montar: montar };
})();
