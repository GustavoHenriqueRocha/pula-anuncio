// Mantém a conexão com o agente local e repassa os comandos para as abas do YouTube.
const api = globalThis.browser ?? chrome;
const AGENTE = "ws://127.0.0.1:8765/ws";

let ws = null;
let espera = 1000;
let ping = null;

function nomeNavegador() {
  const ua = navigator.userAgent;
  if (ua.includes("OPR/")) return "Opera";
  if (ua.includes("Edg/")) return "Edge";
  if (ua.includes("Firefox/")) return "Firefox";
  return "Chrome/Chromium";
}

function enviar(obj) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function conectar() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(AGENTE);
  } catch {
    return agendarReconexao();
  }
  ws.onopen = () => {
    espera = 1000;
    enviar({ tipo: "ola", navegador: nomeNavegador() });
    // Atividade a cada 20 s impede o Chrome de suspender o service worker
    clearInterval(ping);
    ping = setInterval(() => enviar({ tipo: "ping" }), 20000);
  };
  ws.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.cmd === "preparar" || msg.cmd === "conferir") {
      const abas = await repassarParaAbas(msg.cmd);
      enviar({ tipo: "resultado", id: msg.id, navegador: nomeNavegador(), abas });
    }
  };
  ws.onclose = () => {
    clearInterval(ping);
    agendarReconexao();
  };
  ws.onerror = () => {};
}

function agendarReconexao() {
  setTimeout(conectar, espera);
  espera = Math.min(espera * 2, 15000);
}

async function repassarParaAbas(cmd) {
  const abas = await api.tabs.query({ url: ["*://*.youtube.com/*"] });
  const respostas = await Promise.all(
    abas.map((aba) => api.tabs.sendMessage(aba.id, { cmd }).catch(() => null))
  );
  return respostas.filter(Boolean);
}

// Abas do YouTube avisam quando um anúncio começa/termina; isso também acorda o worker
api.runtime.onMessage.addListener((msg) => {
  conectar();
  if (msg?.tipo === "estado") enviar({ tipo: "estado", anuncio: msg.anuncio });
  if (msg?.tipo === "pode_pular") enviar({ tipo: "pode_pular" });
});

api.runtime.onStartup.addListener(conectar);
api.runtime.onInstalled.addListener(conectar);
api.alarms?.create("manter-conexao", { periodInMinutes: 0.5 });
api.alarms?.onAlarm.addListener(conectar);
conectar();
