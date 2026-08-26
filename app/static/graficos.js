/* BDDente — graficos do financeiro, em SVG escrito a mao.
 *
 * Sem biblioteca, pela mesma razao do odontograma: nao arrastar uma dependencia
 * para o projeto inteiro por causa de tres desenhos, e continuar funcionando sem
 * internet.
 *
 * Este arquivo NAO faz conta de dinheiro. O servidor manda os valores ja somados
 * e ja escritos em portugues; aqui eles viram altura de barra e angulo de fatia,
 * e mais nada. Ha teste que falha se formatacao de moeda voltar para ca.
 *
 * Cada grafico e acompanhado, no HTML, de uma tabela com os mesmos numeros. Nao
 * e redundancia: e o que sobra para quem usa leitor de tela, e o que aparece se
 * este arquivo nao carregar.
 */
(function () {
  "use strict";

  var alvo = document.getElementById("dados-graficos");
  if (!alvo) return;
  var dados = JSON.parse(alvo.textContent);

  var ROXO = "#7C3AED";
  var ROXO_CLARO = "#C4B5FD";
  var CINZA = "#CBD5E1";
  var TEXTO_FRACO = "#64748B";
  // Paleta das pizzas: tons que se distinguem tambem em impressao cinza.
  var FATIAS = ["#7C3AED", "#2563EB", "#16A34A", "#D97706", "#DC2626", "#0891B2", "#94A3B8"];

  function elemento(nome, atributos, conteudo) {
    var partes = [];
    Object.keys(atributos).forEach(function (chave) {
      partes.push(chave + '="' + atributos[chave] + '"');
    });
    return (
      "<" + nome + " " + partes.join(" ") + ">" + (conteudo || "") + "</" + nome + ">"
    );
  }

  function desenhar(id, largura, altura, corpo, descricao) {
    var caixa = document.getElementById(id);
    if (!caixa) return;
    // Sem `height` fixo: com viewBox e height fixo o SVG mantem a proporcao e
    // fica centralizado, sobrando faixa branca dos dois lados. Com height:auto
    // ele acompanha a largura disponivel.
    caixa.innerHTML =
      '<svg viewBox="0 0 ' + largura + " " + altura + '" ' +
      'style="width:100%;height:auto" role="img" aria-label="' + descricao + '">' +
      corpo + "</svg>";
  }

  // --- barras --------------------------------------------------------------

  /* `series` e uma lista de {valores, cor}. A PRIMEIRA fica na frente: quem
     desenha por ultimo cobre quem veio antes, entao a ordem de desenho e o
     inverso da ordem da lista. Sem isso, a barra de comparacao (mais larga)
     apaga a barra do ano que se quer ler. */
  function barras(id, rotulos, series, descricao, formatarRotulo) {
    // A proporcao do viewBox e a proporcao final do desenho: o SVG acompanha
    // a largura disponivel e a altura vem junto. 1400x210 da uma faixa baixa,
    // que e o formato certo para comparar doze barras de relance.
    var LARGURA = 1400, ALTURA = 210, BASE = ALTURA - 26, TOPO = 12;
    var maior = 0;
    series.forEach(function (serie) {
      serie.valores.forEach(function (v) { if (v > maior) maior = v; });
    });
    if (maior === 0) maior = 1;

    var passo = LARGURA / rotulos.length;
    var corpo = elemento("line", {
      x1: 0, y1: BASE, x2: LARGURA, y2: BASE, stroke: CINZA, "stroke-width": 1
    });

    var ordem_de_desenho = series.slice().reverse();
    ordem_de_desenho.forEach(function (serie, posicao) {
      var indice = series.length - 1 - posicao;
      var grossura = passo * (indice === 0 ? 0.44 : 0.62);
      var recuo = (passo - grossura) / 2;
      serie.valores.forEach(function (valor, k) {
        var altura = Math.max(((valor / maior) * (BASE - TOPO)), valor > 0 ? 2 : 0);
        if (!altura) return;
        corpo += elemento("rect", {
          x: (passo * k + recuo).toFixed(1),
          y: (BASE - altura).toFixed(1),
          width: grossura.toFixed(1),
          height: altura.toFixed(1),
          fill: serie.cor,
          rx: 2
        });
      });
    });

    corpo += elemento(
      "g",
      { "font-size": 15, fill: TEXTO_FRACO, "text-anchor": "middle",
        "font-family": "ui-sans-serif,system-ui,sans-serif" },
      rotulos.map(function (rotulo, k) {
        return elemento(
          "text",
          { x: (passo * k + passo / 2).toFixed(1), y: ALTURA - 10 },
          formatarRotulo ? formatarRotulo(rotulo, k) : rotulo
        );
      }).join("")
    );

    desenhar(id, LARGURA, ALTURA, corpo, descricao);
  }

  // --- pizza ---------------------------------------------------------------

  function ponto(centro, raio, angulo) {
    return [
      (centro + raio * Math.cos(angulo)).toFixed(2),
      (centro + raio * Math.sin(angulo)).toFixed(2)
    ];
  }

  /* `fatias` e uma lista de [nome, valorComoTexto]. A proporcao usa o numero so
     para achar o angulo; o valor que o usuario le vem da tabela equivalente. */
  function pizza(id, fatias, descricao) {
    var LADO = 260, CENTRO = LADO / 2, RAIO = 92;
    var caixa = document.getElementById(id);
    if (!caixa) return;

    var total = 0;
    var numeros = fatias.map(function (fatia) {
      var n = Number(fatia[1]);
      if (!isFinite(n) || n < 0) n = 0;
      total += n;
      return n;
    });
    if (!fatias.length || total === 0) {
      caixa.innerHTML =
        '<p class="grafico-vazio">Nada produzido neste período.</p>';
      return;
    }

    var corpo = "";
    var legenda = "";
    var angulo = -Math.PI / 2;
    fatias.forEach(function (fatia, k) {
      var proporcao = numeros[k] / total;
      var fim = angulo + proporcao * Math.PI * 2;
      var cor = FATIAS[k % FATIAS.length];
      // Fatia unica: um circulo, porque um arco de 360 graus nao fecha em SVG.
      if (proporcao >= 0.999) {
        corpo += elemento("circle", { cx: CENTRO, cy: CENTRO, r: RAIO, fill: cor });
      } else {
        var comeco = ponto(CENTRO, RAIO, angulo);
        var termino = ponto(CENTRO, RAIO, fim);
        corpo += elemento("path", {
          d: "M" + CENTRO + "," + CENTRO + " L" + comeco[0] + "," + comeco[1] +
             " A" + RAIO + "," + RAIO + " 0 " + (proporcao > 0.5 ? 1 : 0) + " 1 " +
             termino[0] + "," + termino[1] + " Z",
          fill: cor,
          stroke: "#fff",
          "stroke-width": 1.5
        });
      }
      legenda +=
        '<li><i style="background:' + cor + '"></i>' +
        '<span></span><b>' + Math.round(proporcao * 100) + "%</b></li>";
      angulo = fim;
    });

    caixa.innerHTML =
      '<svg viewBox="0 0 ' + LADO + " " + LADO + '" width="' + LADO + '" ' +
      'height="' + LADO + '" role="img" aria-label="' + descricao + '">' +
      corpo + "</svg>" +
      '<ul class="legenda-pizza">' + legenda + "</ul>";

    // O nome vai por textContent, nunca por innerHTML: nome de convenio e de
    // categoria vem do banco, e banco nao e fonte confiavel de HTML.
    var itens = caixa.querySelectorAll(".legenda-pizza span");
    fatias.forEach(function (fatia, k) {
      if (itens[k]) itens[k].textContent = fatia[0];
    });
  }

  // --- montagem ------------------------------------------------------------

  barras(
    "grafico-meses",
    dados.meses,
    [
      { valores: dados.recebido_por_mes.map(Number), cor: ROXO },
      { valores: dados.recebido_ano_anterior.map(Number), cor: CINZA }
    ],
    "Dinheiro recebido mês a mês em " + dados.ano +
      ", com o ano anterior em cinza atrás"
  );

  barras(
    "grafico-dias",
    dados.tratamentos_por_dia,
    [{ valores: dados.tratamentos_por_dia, cor: ROXO_CLARO }],
    "Tratamentos realizados por dia do mês",
    function (_valor, indice) {
      // Um rotulo a cada cinco dias: 31 numeros lado a lado viram borrao.
      return (indice + 1) % 5 === 0 || indice === 0 ? String(indice + 1) : "";
    }
  );

  pizza("grafico-categoria", dados.por_categoria, "Produção por categoria de tratamento");
  pizza("grafico-convenio", dados.por_convenio, "Produção por convênio");
})();
