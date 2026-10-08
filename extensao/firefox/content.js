// Roda dentro das abas do YouTube: detecta anúncio e clica em "Pular".
const api = globalThis.browser ?? chrome;

const SELETORES_PULAR = [
  ".ytp-skip-ad-button",
  ".ytp-ad-skip-button-modern",
  ".ytp-ad-skip-button",
  ".ytp-ad-skip-button-slot button",
  ".ytp-ad-skip-button-container button",
  "button[id^='skip-button']",
  ".videoAdUiSkipButton",
];

function player() {
  return document.querySelector("#movie_player, .html5-video-player");
}

function temAnuncio() {
  const p = player();
  return !!p && (p.classList.contains("ad-showing") || p.classList.contains("ad-interrupting"));
}

function visivel(el) {
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden" && s.opacity !== "0";
}

function botaoPular() {
  for (const sel of SELETORES_PULAR) {
    for (const el of document.querySelectorAll(sel)) {
      if (visivel(el)) return el;
    }
  }
  return null;
}

// O YouTube ignora cliques gerados por script. Por isso a extensão só deixa o botão
// focado e o agente aperta Enter de verdade no teclado do sistema.
let alvo = null;

function preparar() {
  const anuncio = temAnuncio();
  alvo = null;
  if (document.hidden) return { pronto: false, anuncio, motivo: "aba escondida" };
  const botao = botaoPular();
  if (!botao) return { pronto: false, anuncio };
  if (!botao.hasAttribute("tabindex") && botao.tagName !== "BUTTON") botao.tabIndex = 0;
  botao.focus({ preventScroll: true });
  alvo = botao;
  return { pronto: document.activeElement === botao, anuncio, titulo: document.title };
}

// Pulou quando o anúncio acabou ou o botão sumiu (o próximo anúncio da fila tem botão novo)
function conferir() {
  if (!alvo) return { pulou: false, anuncio: temAnuncio() };
  const pulou = !temAnuncio() || !alvo.isConnected || !visivel(alvo);
  return { pulou, anuncio: temAnuncio() };
}

api.runtime.onMessage.addListener((msg, _sender, responder) => {
  if (msg?.cmd === "preparar") responder(preparar());
  else if (msg?.cmd === "conferir") responder(conferir());
});

// Avisa o agente quando um anúncio começa/termina (o celular mostra isso)
// e quando o botão "Pular" aparece (para o modo "pular sozinho")
let ultimo = null;
let ultimoPedido = 0;
function verificar() {
  const agora = temAnuncio();
  if (agora !== ultimo) {
    ultimo = agora;
    api.runtime.sendMessage({ tipo: "estado", anuncio: agora }).catch?.(() => {});
  }
  if (agora && !document.hidden && botaoPular() && Date.now() - ultimoPedido > 3000) {
    ultimoPedido = Date.now();
    api.runtime.sendMessage({ tipo: "pode_pular" }).catch?.(() => {});
  }
}
setInterval(verificar, 500);
verificar();
