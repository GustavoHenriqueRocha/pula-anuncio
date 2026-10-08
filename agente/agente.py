#!/usr/bin/env python3
"""Agente do Pula Anúncio.

Roda em cada PC que toca YouTube. Faz três coisas:
  - serve a página do celular em  http://<ip>:8765/
  - recebe o comando do celular   POST /skip
  - repassa o comando para as extensões dos navegadores via WebSocket em /ws

O YouTube ignora cliques gerados por script. Então a extensão deixa o botão
"Pular" focado e o agente aperta Enter no teclado do sistema (clique real).

Só usa a biblioteca padrão do Python (3.8+).
"""

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import entrada as modulo_entrada

PORTA = int(os.environ.get("PULA_PORTA", "8765"))
PASTA_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
ESPERA_RESPOSTA = 2.0  # segundos esperando as extensões responderem
entrada = modulo_entrada.criar()
pulando = threading.Lock()  # um pulo de cada vez

clientes = {}  # id -> Cliente
clientes_lock = threading.Lock()
pendentes = {}  # id do comando -> {"evento": Event, "respostas": [...]}
pendentes_lock = threading.Lock()
proximo_id = 0


class Cliente:
    """Uma extensão de navegador conectada."""

    def __init__(self, sock, navegador):
        self.sock = sock
        self.navegador = navegador
        self.anuncio = False
        self.envio_lock = threading.Lock()

    def enviar(self, obj):
        dados = json.dumps(obj).encode()
        cabecalho = bytearray([0x81])  # FIN + texto
        n = len(dados)
        if n < 126:
            cabecalho.append(n)
        elif n < 65536:
            cabecalho.append(126)
            cabecalho += struct.pack(">H", n)
        else:
            cabecalho.append(127)
            cabecalho += struct.pack(">Q", n)
        with self.envio_lock:
            self.sock.sendall(bytes(cabecalho) + dados)


def ler_exato(sock, n):
    buf = b""
    while len(buf) < n:
        parte = sock.recv(n - len(buf))
        if not parte:
            raise ConnectionError("conexão fechada")
        buf += parte
    return buf


def ler_frame(sock):
    """Lê um frame WebSocket do cliente. Retorna (opcode, payload)."""
    b1, b2 = ler_exato(sock, 2)
    opcode = b1 & 0x0F
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", ler_exato(sock, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", ler_exato(sock, 8))[0]
    mascara = ler_exato(sock, 4) if b2 & 0x80 else b"\0\0\0\0"
    dados = bytearray(ler_exato(sock, n))
    for i in range(n):
        dados[i] ^= mascara[i % 4]
    return opcode, bytes(dados)


def enviar_comando(cmd):
    """Manda um comando para todas as extensões e espera as respostas."""
    global proximo_id
    with pendentes_lock:
        proximo_id += 1
        cid = proximo_id
        pendentes[cid] = {"evento": threading.Event(), "respostas": []}
    with clientes_lock:
        alvo = list(clientes.values())
    for c in alvo:
        try:
            c.enviar({"cmd": cmd, "id": cid})
        except OSError:
            pass

    # Espera todos responderem ou estourar o tempo
    limite = time.time() + ESPERA_RESPOSTA
    while time.time() < limite:
        with pendentes_lock:
            if len(pendentes[cid]["respostas"]) >= len(alvo):
                break
        pendentes[cid]["evento"].wait(0.05)
        pendentes[cid]["evento"].clear()
    with pendentes_lock:
        respostas = pendentes.pop(cid)["respostas"]
    return {"navegadores": len(alvo), "respostas": respostas}


def abas(resposta):
    """Lista (navegador, aba) de todas as respostas das extensões."""
    return [(r.get("navegador", "?"), a) for r in resposta["respostas"] for a in r.get("abas", [])]


def rodar(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout


def enter_hyprland(titulo):
    janelas = json.loads(rodar("hyprctl", "clients", "-j") or "[]")
    janela = next((j for j in janelas if titulo in j.get("title", "")), None)
    if not janela:
        return "janela do navegador não encontrada"
    anterior = json.loads(rodar("hyprctl", "activewindow", "-j") or "{}").get("address")
    if anterior != janela["address"]:
        rodar("hyprctl", "dispatch", "focuswindow", f"address:{janela['address']}")
        time.sleep(0.15)
    rodar("wtype", "-k", "Return")
    if anterior and anterior != janela["address"]:
        time.sleep(0.1)
        rodar("hyprctl", "dispatch", "focuswindow", f"address:{anterior}")
    return None


def enter_windows(titulo):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    achada = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if titulo in buf.value:
                achada.append(hwnd)
                return False
        return True

    user32.EnumWindows(cada, 0)
    if not achada:
        return "janela do navegador não encontrada"
    hwnd = achada[0]
    tecla = lambda vk, solta=False: user32.keybd_event(vk, 0, 2 if solta else 0, 0)
    anterior = user32.GetForegroundWindow()
    if anterior != hwnd:
        # Uma tecla inofensiva (F24) dá ao agente o direito de trocar a janela em foco
        tecla(0x87); tecla(0x87, True)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    tecla(0x0D); tecla(0x0D, True)  # Enter
    if anterior and anterior != hwnd:
        time.sleep(0.1)
        user32.SetForegroundWindow(anterior)
    return None


def apertar_enter(titulo):
    """Foca a janela cujo título contém `titulo` e aperta Enter. Retorna o erro ou None."""
    try:
        if sys.platform == "win32":
            return enter_windows(titulo)
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return enter_hyprland(titulo)
        return "sistema não suportado (só Hyprland e Windows)"
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return f"erro ao apertar Enter: {e}"


def pular_sozinho():
    """Chamado quando uma extensão avisa que o botão "Pular" apareceu. Sempre ligado."""
    if not pulando.acquire(blocking=False):
        return
    try:
        r = pular()
        print(f"[auto] clicou={r['clicou']} {r.get('motivo', '')}")
        time.sleep(1.5)  # deixa o YouTube trocar de anúncio antes do próximo pulo
    finally:
        pulando.release()


def pular():
    preparo = enviar_comando("preparar")
    lista = abas(preparo)
    anuncio = any(a.get("anuncio") for _, a in lista)
    base = {"conectados": preparo["navegadores"], "anuncio": anuncio, "clicou": False}
    prontas = [a for _, a in lista if a.get("pronto") and a.get("titulo")]
    if not prontas:
        return base
    erro = apertar_enter(prontas[0]["titulo"])
    if erro:
        return {**base, "motivo": erro}
    time.sleep(0.5)
    clicou = any(a.get("pulou") for _, a in abas(enviar_comando("conferir")))
    return {**base, "clicou": clicou, "motivo": "" if clicou else "Enter enviado, mas o anúncio continuou"}


def status():
    with clientes_lock:
        lista = [{"navegador": c.navegador, "anuncio": c.anuncio} for c in clientes.values()]
    return {
        "maquina": socket.gethostname(),
        "navegadores": lista,
        "anuncio": any(c["anuncio"] for c in lista),
    }


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # exigido pelo handshake WebSocket

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PASTA_WEB, **kwargs)

    def log_message(self, fmt, *args):
        pass  # silencioso; os eventos importantes são impressos à mão

    def end_headers(self):
        # O celular pode abrir a página de um PC e comandar outro
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def responder_json(self, obj, codigo=200):
        corpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/ws":
            return self.websocket()
        if self.path == "/controle":
            return self.controle()
        if self.path == "/status":
            return self.responder_json(status())
        return super().do_GET()

    def do_POST(self):
        if self.path == "/skip":
            r = pular()
            print(f"[skip] conectados={r['conectados']} anuncio={r['anuncio']} "
                  f"clicou={r['clicou']} {r.get('motivo', '')}")
            return self.responder_json({"maquina": socket.gethostname(), **r})
        self.responder_json({"erro": "rota desconhecida"}, 404)

    def aceitar_websocket(self):
        chave = self.headers.get("Sec-WebSocket-Key")
        if not chave or self.headers.get("Upgrade", "").lower() != "websocket":
            self.responder_json({"erro": "esperado WebSocket"}, 400)
            return False
        aceite = base64.b64encode(hashlib.sha1((chave + WS_GUID).encode()).digest()).decode()
        self.send_response_only(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", aceite)
        SimpleHTTPRequestHandler.end_headers(self)  # sem os cabeçalhos CORS
        self.wfile.flush()
        self.close_connection = True
        return True

    def controle(self):
        """Mouse e teclado vindos do celular."""
        if not self.aceitar_websocket():
            return
        sock = self.connection
        sock.settimeout(None)
        print(f"[+] celular conectado: {self.client_address[0]}")
        try:
            while True:
                opcode, dados = ler_frame(sock)
                if opcode == 0x8:
                    break
                if opcode != 0x1:
                    continue
                m = json.loads(dados)
                t = m.get("t")
                if t == "m":
                    entrada.mover(float(m["dx"]), float(m["dy"]))
                elif t == "s":
                    entrada.rolar(float(m.get("dx", 0)), float(m.get("dy", 0)))
                elif t == "b" and m.get("b") in ("left", "right", "middle"):
                    entrada.botao(m["b"], bool(m.get("down")))
                elif t == "c" and m.get("b") in ("left", "right", "middle"):
                    entrada.botao(m["b"], True)
                    entrada.botao(m["b"], False)
                elif t == "txt" and m.get("v"):
                    entrada.texto(str(m["v"])[:500])
                elif t == "k" and m.get("v") in modulo_entrada.TECLAS:
                    entrada.tecla(m["v"])
        except (OSError, ConnectionError, ValueError, KeyError, subprocess.SubprocessError):
            pass
        finally:
            print(f"[-] celular desconectado: {self.client_address[0]}")

    def websocket(self):
        if not self.aceitar_websocket():
            return
        sock = self.connection
        sock.settimeout(90)  # a extensão manda ping a cada 20 s
        cliente = Cliente(sock, "?")
        with clientes_lock:
            clientes[id(cliente)] = cliente
        try:
            while True:
                opcode, dados = ler_frame(sock)
                if opcode == 0x8:  # close
                    break
                if opcode == 0x9:  # ping de protocolo -> pong
                    with cliente.envio_lock:
                        sock.sendall(bytes([0x8A, len(dados)]) + dados)
                    continue
                if opcode != 0x1:
                    continue
                msg = json.loads(dados)
                tipo = msg.get("tipo")
                if tipo == "ola":
                    cliente.navegador = msg.get("navegador", "?")
                    print(f"[+] extensão conectada: {cliente.navegador}")
                elif tipo == "estado":
                    cliente.anuncio = bool(msg.get("anuncio"))
                elif tipo == "pode_pular":
                    # Roda em outra thread: pular() espera respostas que chegam por esta conexão
                    threading.Thread(target=pular_sozinho, daemon=True).start()
                elif tipo == "resultado":
                    with pendentes_lock:
                        p = pendentes.get(msg.get("id"))
                        if p:
                            p["respostas"].append(msg)
                            p["evento"].set()
        except (OSError, ConnectionError, ValueError):
            pass
        finally:
            with clientes_lock:
                clientes.pop(id(cliente), None)
            print(f"[-] extensão desconectada: {cliente.navegador}")


def ips_locais():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # O celular fecha conexões sem avisar; isso não é erro de verdade
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def main():
    servidor = Servidor(("0.0.0.0", PORTA), Handler)
    print(f"Pula Anúncio — agente rodando na porta {PORTA}")
    for ip in ips_locais():
        print(f"  No celular, abra: http://{ip}:{PORTA}/   (IP desta máquina: {ip})")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
