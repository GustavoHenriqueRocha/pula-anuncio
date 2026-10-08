# Arquitetura

Três peças, todas na rede local:

| Peça | Onde roda | Papel |
|---|---|---|
| **Página do celular** (`agente/web/`) | navegador do celular | touchpad e teclado; guarda a lista de máquinas no `localStorage` |
| **Agente** (`agente/agente.py`, `agente/entrada.py`) | cada PC, porta 8765 | serve a página, injeta mouse/teclado no sistema e coordena o pulo de anúncio |
| **Extensão** (`extensao/`) | navegador de cada PC | enxerga o YouTube: detecta anúncio e foca o botão "Pular" |

A página pode ser aberta a partir de qualquer agente e comandar qualquer outro: as rotas HTTP
respondem com CORS liberado e o WebSocket não tem restrição de origem.

## Rotas do agente

| Rota | Quem usa | O que faz |
|---|---|---|
| `GET /` | celular | página do controle (arquivos de `agente/web/`) |
| `GET /status` | celular | `{maquina, navegadores: [{navegador, anuncio}], anuncio}` |
| `POST /skip` | qualquer um | pula o anúncio agora; responde `{conectados, anuncio, clicou, motivo}` |
| `WS /controle` | celular | mouse e teclado (mensagens abaixo) |
| `WS /ws` | extensão | comandos e avisos do YouTube (mensagens abaixo) |

O WebSocket é implementado à mão no agente (handshake + frames de texto), para não depender de
bibliotecas externas.

## Mouse e teclado (`WS /controle`)

Mensagens JSON do celular para o agente:

| Mensagem | Efeito |
|---|---|
| `{"t":"m","dx":3.5,"dy":-1}` | move o mouse (relativo, em pixels) |
| `{"t":"s","dx":0,"dy":12}` | rola (rolagem suave, como touchpad) |
| `{"t":"c","b":"left"}` | clique (`left`, `right` ou `middle`) |
| `{"t":"b","b":"left","down":true}` | aperta/solta um botão (usado para segurar e arrastar) |
| `{"t":"txt","v":"olá"}` | digita texto |
| `{"t":"k","v":"Enter"}` | tecla especial (lista em `TECLAS` em `entrada.py`) |

O celular junta os movimentos de cada quadro de animação numa mensagem só, aplica aceleração
(`acelerar()` em `index.html`) e manda.

### Como o agente gera a entrada

- **Linux / Wayland**: `entrada.py` abre uma conexão própria com o compositor (o socket em
  `$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY`) e fala o protocolo `zwlr_virtual_pointer_v1` direto em
  bytes: `motion`, `button`, `axis` e `frame`. Não precisa de root nem de `/dev/uinput`.
  O teclado usa o `wtype`, que entende qualquer caractere Unicode, independente do layout.
- **Windows**: `mouse_event` para o mouse e `SendInput` com `KEYEVENTF_UNICODE` para o texto.

### Botão travado

O celular manda `down:true` ao encostar no botão Esquerdo/Direito. Se o dedo sair antes de 2 s,
manda `down:false` (clique normal). Se passar de 2 s, não manda nada ao soltar — o botão fica
apertado no PC — e o próximo toque nele (ou no touchpad) manda `down:false`. Ao trocar de máquina
ou sair da página, os botões travados são soltos.

### Teclado do celular

O campo de texto funciona como espelho: a cada evento `input`, a página compara o texto novo com
o anterior, manda `Backspace` para o que sumiu e `txt` para o que entrou. Assim funciona com
corretor e autocompletar, que reescrevem a palavra inteira.

## Pular anúncio

O YouTube ignora cliques gerados por script (`isTrusted = false`), então a extensão não clica:

1. `content.js` olha a página a cada 0,5 s. Com anúncio na tela (`#movie_player.ad-showing`) e o
   botão "Pular" visível, avisa o background, que manda `{"tipo":"pode_pular"}` ao agente.
2. O agente (sempre ligado) manda `{"cmd":"preparar"}` para as extensões.
   Cada aba visível do YouTube foca o botão "Pular" e responde `{pronto, anuncio, titulo}`.
3. O agente procura a janela do navegador pelo título da aba, traz para a frente
   (`hyprctl dispatch focuswindow` ou `SetForegroundWindow`), aperta **Enter de verdade**
   (`wtype -k Return` ou `SendInput`) e devolve o foco para a janela anterior.
4. Depois de 0,5 s manda `{"cmd":"conferir"}`; a aba responde `{pulou}` (o anúncio acabou ou o
   botão sumiu).

Um pulo de cada vez (`pulando` em `agente.py`), com 1,5 s de pausa para o YouTube trocar de anúncio.

### Mensagens da extensão (`WS /ws`)

| Direção | Mensagem |
|---|---|
| extensão → agente | `{"tipo":"ola","navegador":"Firefox"}` ao conectar |
| extensão → agente | `{"tipo":"ping"}` a cada 20 s (mantém vivo o service worker do Chrome) |
| extensão → agente | `{"tipo":"estado","anuncio":true}` quando um anúncio começa/termina |
| extensão → agente | `{"tipo":"pode_pular"}` quando o botão "Pular" aparece |
| agente → extensão | `{"cmd":"preparar","id":7}` / `{"cmd":"conferir","id":8}` |
| extensão → agente | `{"tipo":"resultado","id":7,"navegador":"...","abas":[...]}` |

### Por que dois manifestos

- **Chromium (MV3)**: background é um *service worker*, que o Chrome suspende quando fica ocioso.
  O ping de 20 s, um alarme a cada 30 s e as mensagens das abas mantêm a conexão viva.
- **Firefox (MV2)**: usa página de background persistente, mais simples e estável no Firefox.

O código (`background.js`, `content.js`) é o mesmo; usa `browser ?? chrome` para funcionar nos dois.
