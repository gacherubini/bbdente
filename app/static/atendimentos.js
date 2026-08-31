/* BDDente — as acoes de cada linha da tela do dia.
 *
 * Excluir usa a confirmacao compartilhada (`confirmar.js`), a mesma do historico
 * do odontograma: sao a mesma exclusao vista de duas telas.
 *
 * Editar nao acontece aqui. Corrigir dente, faces ou tratamento pede o desenho ao
 * lado, e esta tela nao tem odontograma — por isso o "editar" e um link para
 * `/odontograma/{paciente}?editar={lancamento}`, onde o painel abre ja preenchido.
 *
 * Depois de excluir, a pagina recarrega. Os tres cartoes do topo e o subtotal de
 * cada paciente sao somados no servidor; refazer essa conta aqui seria a mesma
 * regra escrita em dois lugares, e um dia elas discordam.
 */
(function () {
  "use strict";

  var COLUNAS = 4;

  document.addEventListener("click", function (evento) {
    var acionado = evento.target.closest(".excluir-lancamento");
    if (!acionado) return;
    window.Confirmar.excluirLancamento(acionado.closest("tr"), {
      colunas: COLUNAS,
      aoConcluir: function () { window.location.reload(); }
    });
  });
})();
