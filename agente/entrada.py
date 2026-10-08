"""Mouse e teclado virtuais controlados pelo celular.

Linux (Wayland/Hyprland): o mouse fala direto com o compositor pelo protocolo
zwlr_virtual_pointer_v1 (sem sudo e sem instalar nada); o teclado usa o wtype.
Windows: usa a API do Windows (SendInput) via ctypes.
"""

import os
import socket
import struct
import subprocess
import sys
import threading
import time

# Teclas especiais que o celular pode mandar -> (nome no wtype, código virtual no Windows)
TECLAS = {
    "Enter": ("Return", 0x0D),
    "Backspace": ("BackSpace", 0x08),
    "Tab": ("Tab", 0x09),
    "Escape": ("Escape", 0x1B),
    "Delete": ("Delete", 0x2E),
    "ArrowUp": ("Up", 0x26),
    "ArrowDown": ("Down", 0x28),
    "ArrowLeft": ("Left", 0x25),
    "ArrowRight": ("Right", 0x27),
    "Home": ("Home", 0x24),
    "End": ("End", 0x23),
    "F11": ("F11", 0x7A),
    "VolumeDown": ("XF86AudioLowerVolume", 0xAE),
    "VolumeUp": ("XF86AudioRaiseVolume", 0xAF),
    "VolumeMute": ("XF86AudioMute", 0xAD),
    "PlayPause": ("XF86AudioPlay", 0xB3),
}


def _agora_ms():
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


class PonteiroWayland:
    """Cliente Wayland mínimo que só cria um zwlr_virtual_pointer_v1."""

    BOTOES = {"left": 0x110, "right": 0x111, "middle": 0x112}  # BTN_* do Linux

    def __init__(self):
        caminho = os.path.join(os.environ["XDG_RUNTIME_DIR"], os.environ.get("WAYLAND_DISPLAY", "wayland-0"))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(caminho)
        self.proximo = 2  # o id 1 é o wl_display
        registro = self._novo()
        self._pedir(1, 1, struct.pack("<I", registro))  # wl_display.get_registry
        fim = self._novo()
        self._pedir(1, 0, struct.pack("<I", fim))  # wl_display.sync

        globais = {}
        for obj, op, corpo in self._eventos_ate(fim):
            if obj == registro and op == 0:  # wl_registry.global
                nome, n = struct.unpack_from("<II", corpo)
                interface = corpo[8:8 + n - 1].decode()
                versao = struct.unpack_from("<I", corpo, 8 + ((n + 3) & ~3))[0]
                globais[interface] = (nome, versao)

        if "zwlr_virtual_pointer_manager_v1" not in globais:
            raise OSError("o compositor não suporta ponteiro virtual")
        nome, versao = globais["zwlr_virtual_pointer_manager_v1"]
        self.versao = min(versao, 2)
        gerente = self._novo()
        self._pedir(registro, 0, struct.pack("<I", nome) + self._texto("zwlr_virtual_pointer_manager_v1")
                    + struct.pack("<II", self.versao, gerente))  # wl_registry.bind
        self.ponteiro = self._novo()
        self._pedir(gerente, 0, struct.pack("<II", 0, self.ponteiro))  # create_virtual_pointer(seat=null)
        self.sock.setblocking(False)

    def _novo(self):
        self.proximo += 1
        return self.proximo - 1

    @staticmethod
    def _texto(s):
        b = s.encode() + b"\0"
        return struct.pack("<I", len(b)) + b + b"\0" * (-len(b) % 4)

    @staticmethod
    def _fixo(v):
        return struct.pack("<i", int(round(v * 256)))

    def _pedir(self, obj, opcode, corpo=b""):
        self.sock.sendall(struct.pack("<II", obj, ((8 + len(corpo)) << 16) | opcode) + corpo)

    def _eventos_ate(self, callback):
        buf = b""
        while True:
            while len(buf) < 8:
                buf += self.sock.recv(4096)
            obj, tam_op = struct.unpack_from("<II", buf)
            tam = tam_op >> 16
            while len(buf) < tam:
                buf += self.sock.recv(4096)
            corpo, buf = buf[8:tam], buf[tam:]
            if obj == callback:
                return
            if obj == 1 and (tam_op & 0xFFFF) == 0:
                raise OSError("erro do compositor Wayland")
            yield obj, tam_op & 0xFFFF, corpo

    def _descartar_eventos(self):
        try:
            while self.sock.recv(4096):
                pass
        except BlockingIOError:
            pass

    def _quadro(self):
        self._pedir(self.ponteiro, 4)  # frame
        self._descartar_eventos()

    def mover(self, dx, dy):
        self._pedir(self.ponteiro, 0, struct.pack("<I", _agora_ms()) + self._fixo(dx) + self._fixo(dy))
        self._quadro()

    def botao(self, nome, apertado):
        self._pedir(self.ponteiro, 2, struct.pack("<III", _agora_ms(), self.BOTOES[nome], 1 if apertado else 0))
        self._quadro()

    def rolar(self, dx, dy):
        t = _agora_ms()
        if self.versao >= 2:
            self._pedir(self.ponteiro, 5, struct.pack("<I", 1))  # axis_source = finger (rolagem suave)
        if dy:
            self._pedir(self.ponteiro, 3, struct.pack("<II", t, 0) + self._fixo(dy))
        if dx:
            self._pedir(self.ponteiro, 3, struct.pack("<II", t, 1) + self._fixo(dx))
        self._quadro()


class EntradaLinux:
    def __init__(self):
        self.ponteiro = None
        self.lock = threading.Lock()

    def _com_ponteiro(self, fn):
        with self.lock:
            for _ in range(2):  # reconecta uma vez se o Hyprland reiniciou
                try:
                    if self.ponteiro is None:
                        self.ponteiro = PonteiroWayland()
                    return fn(self.ponteiro)
                except OSError:
                    self.ponteiro = None

    def mover(self, dx, dy):
        self._com_ponteiro(lambda p: p.mover(dx, dy))

    def botao(self, nome, apertado):
        self._com_ponteiro(lambda p: p.botao(nome, apertado))

    def rolar(self, dx, dy):
        self._com_ponteiro(lambda p: p.rolar(dx, dy))

    def texto(self, s):
        subprocess.run(["wtype", "--", s], timeout=5)

    def tecla(self, nome):
        subprocess.run(["wtype", "-k", TECLAS[nome][0]], timeout=5)


class EntradaWindows:
    MOVE, ESQ_D, ESQ_S, DIR_D, DIR_S, MEIO_D, MEIO_S = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
    RODA, RODA_H = 0x800, 0x1000
    BOTOES = {"left": (ESQ_D, ESQ_S), "right": (DIR_D, DIR_S), "middle": (MEIO_D, MEIO_S)}

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _UNIAO(ctypes.Union):
            # MOUSEINPUT é o maior membro da união; o tamanho precisa bater com o do Windows
            _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _UNIAO)]

        self.INPUT, self.KEYBDINPUT = INPUT, KEYBDINPUT
        self.resto = [0.0, 0.0]  # frações de pixel acumuladas

    def mover(self, dx, dy):
        self.resto[0] += dx
        self.resto[1] += dy
        ix, iy = int(self.resto[0]), int(self.resto[1])
        self.resto[0] -= ix
        self.resto[1] -= iy
        if ix or iy:
            self.user32.mouse_event(self.MOVE, ix, iy, 0, 0)

    def botao(self, nome, apertado):
        desce, sobe = self.BOTOES[nome]
        self.user32.mouse_event(desce if apertado else sobe, 0, 0, 0, 0)

    def rolar(self, dx, dy):
        # No Windows, 120 = um "dente" da roda; para cima é positivo
        if dy:
            self.user32.mouse_event(self.RODA, 0, 0, int(-dy * 8), 0)
        if dx:
            self.user32.mouse_event(self.RODA_H, 0, 0, int(dx * 8), 0)

    def _teclas(self, eventos):
        arr = (self.INPUT * len(eventos))()
        for i, (vk, scan, flags) in enumerate(eventos):
            arr[i].type = 1  # INPUT_KEYBOARD
            arr[i].u.ki = self.KEYBDINPUT(vk, scan, flags, 0, 0)
        self.user32.SendInput(len(eventos), arr, self.ctypes.sizeof(self.INPUT))

    def texto(self, s):
        UNICODE, SOLTA = 0x4, 0x2
        eventos = []
        for unidade in struct.unpack(f"<{len(s.encode('utf-16-le')) // 2}H", s.encode("utf-16-le")):
            eventos += [(0, unidade, UNICODE), (0, unidade, UNICODE | SOLTA)]
        if eventos:
            self._teclas(eventos)

    def tecla(self, nome):
        vk = TECLAS[nome][1]
        self._teclas([(vk, 0, 0), (vk, 0, 0x2)])


def criar():
    if sys.platform == "win32":
        return EntradaWindows()
    return EntradaLinux()
