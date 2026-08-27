// O QR na tela de Configuracoes.
//
// "Renova sozinho" nao e nenhuma engenharia: o QR do WhatsApp expira em poucos
// segundos, entao renovar e pedir de novo. Este arquivo pede, mostra, e para de
// pedir quando a leitura acontece.
//
// Ele nao decide nada. Nao sabe o que e estar conectado, nao monta URL de
// provedor, nao guarda credencial — pede a uma rota do proprio BDDente e desenha
// o que vier. A regra mora no servidor, como no `odontograma.js`.

(function () {
  const botao = document.getElementById("botao-qr");
  const area = document.getElementById("qr-area");
  const imagem = document.getElementById("qr-imagem");
  const recado = document.getElementById("qr-recado");
  if (!botao || !area || !imagem || !recado) return;

  // 20 s: o QR do WhatsApp vive uns 60, e pedir mais rapido que isso e bater na
  // Evolution a toa. Quem esta com o celular na mao tem tempo de sobra.
  const INTERVALO_MS = 20000;
  let relogio = null;

  function parar() {
    if (relogio) {
      clearInterval(relogio);
      relogio = null;
    }
  }

  async function pedir() {
    try {
      const resposta = await fetch("/configuracoes/whatsapp/qr");
      if (!resposta.ok) throw new Error(resposta.status);
      const dados = await resposta.json();

      if (dados.conectado) {
        // Leu. Recarregar e o certo em vez de remendar a tela por JavaScript:
        // o estado conectado muda o cartao inteiro, e quem sabe montar isso e o
        // servidor.
        parar();
        recado.textContent = "Conectado! Atualizando a tela…";
        imagem.hidden = true;
        window.location.reload();
        return;
      }

      if (dados.imagem) {
        imagem.src = dados.imagem;
        imagem.hidden = false;
        recado.textContent = "Leia o código com o celular:";
        return;
      }

      imagem.hidden = true;
      recado.textContent =
        dados.erro || "Não consegui pedir o código. Tente de novo.";
    } catch (erro) {
      // Rede caindo nao para o relogio: a proxima batida tenta de novo, e a
      // pessoa continua olhando a tela. Parar aqui exigiria clicar no botao
      // outra vez sem saber por que.
      imagem.hidden = true;
      recado.textContent = "Não consegui falar com o servidor. Tentando de novo…";
    }
  }

  botao.addEventListener("click", function () {
    area.hidden = false;
    recado.textContent = "Pedindo o código…";
    parar();
    pedir();
    relogio = setInterval(pedir, INTERVALO_MS);
  });

  // Sair da tela para de pedir. Sem isto, uma aba esquecida aberta bate na
  // Evolution a cada 20 s pelo resto do dia.
  window.addEventListener("pagehide", parar);
})();
