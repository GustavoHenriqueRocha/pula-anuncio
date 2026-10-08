# Pula Anúncio

Controle remoto pelo celular para os PCs da casa: **touchpad**, **teclado** e **pular anúncio do
YouTube sozinho** — tudo numa página web, sem instalar app no celular.

```
celular (página web) ──WebSocket──▶ agente (porta 8765, em cada PC) ──▶ mouse e teclado do sistema
                                         ▲
                                         └──WebSocket── extensão do navegador (vê o YouTube)
```

- Funciona em **Linux com Hyprland** (Wayland) e **Windows**.
- Navegadores: **Firefox**, **Chrome**, **Chromium**, **Edge** e **Opera GX**.
- O agente é Python puro (só biblioteca padrão), sem dependências.

Detalhes de funcionamento e do protocolo: [docs/arquitetura.md](docs/arquitetura.md).

## O que tem no celular

A página é vertical, de cima para baixo:

| Parte | Como usa |
|---|---|
| **Máquinas** | Chips no topo para escolher o PC. Bolinha verde = online, amarela = anúncio na tela, vermelha = sem resposta. |
| **Touchpad** | 1 dedo move o mouse · toque = clique esquerdo · toque com 2 dedos = clique direito · arrastar com 2 dedos = rolar. |
| **Esquerdo / Direito** | Toque = clique. **Segurar 2 s trava** o botão apertado (fica azul) para arrastar coisas; tocar de novo solta. |
| **Teclado** | O campo de texto digita no PC (acentos e corretor do celular funcionam). Teclas: Esc, Tab, setas, ⌫, Enter, Tela (F11), Início, Fim, play/pause e volume. |
| **Pular anúncio sozinho** | Interruptor por máquina. Quando o botão "Pular" do YouTube aparece, o agente clica nele. |

O zoom por toque duplo fica bloqueado para não atrapalhar o touchpad.

## Estrutura

```
agente/
  agente.py              servidor HTTP + WebSocket; pulo de anúncio
  entrada.py             mouse e teclado virtuais (Wayland/Hyprland e Windows)
  web/                   página do celular (servida pelo agente)
  pula-anuncio.service   serviço systemd do usuário (Linux)
  iniciar-windows.bat    inicia o agente sem janela (Windows)
extensao/
  chromium/              extensão para Chrome, Chromium, Edge e Opera GX (código-fonte)
  firefox/               mesma extensão com manifesto do Firefox
  sincronizar.sh         copia os .js de chromium/ para firefox/
docs/
  arquitetura.md         como funciona por dentro e mensagens trocadas
```

## Instalação

Em **cada PC** que vai ser controlado: agente + extensão.

### 1. Agente

**Linux (Hyprland)** — precisa de `python3` e `wtype` (`sudo pacman -S wtype`):

```bash
git clone <este repositório> ~/Projetos/pula-anuncio
cp ~/Projetos/pula-anuncio/agente/pula-anuncio.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pula-anuncio
sudo ufw allow 8765/tcp          # se usar ufw: libera o acesso do celular
```

O serviço sobe sozinho a cada login. Log: `journalctl --user -u pula-anuncio -f`.

**Windows**:

1. Instale o Python em https://python.org (marque **Add python.exe to PATH**).
2. Copie a pasta `agente` para o PC e dê dois cliques em `iniciar-windows.bat`.
3. Para iniciar junto com o Windows: `Win+R` → `shell:startup` → cole ali um atalho do `.bat`.
4. Libere a porta (PowerShell como administrador):
   ```powershell
   New-NetFirewallRule -DisplayName "Pula Anuncio" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
   ```

A porta pode ser trocada com a variável de ambiente `PULA_PORTA`.

### 2. Extensão do navegador

Só é necessária para o **pular anúncio**; o mouse e o teclado funcionam sem ela.

**Chrome / Chromium / Edge / Opera GX**

1. Abra `chrome://extensions` (no Opera: `opera://extensions`; no Edge: `edge://extensions`).
2. Ligue o **Modo do desenvolvedor**.
3. **Carregar sem compactação** → escolha a pasta `extensao/chromium`.

Ela continua instalada depois de fechar o navegador. No Opera GX, se o bloqueador de anúncios
embutido estiver ligado, nem aparece anúncio para pular.

**Firefox**

- Teste rápido: `about:debugging#/runtime/this-firefox` → **Carregar extensão temporária** →
  `extensao/firefox/manifest.json`. Some ao fechar o Firefox.
- Permanente: o Firefox só instala extensão assinada. Crie as chaves (grátis) em
  https://addons.mozilla.org/developers/addon/api/key/ e rode dentro de `extensao/firefox`:
  ```bash
  WEB_EXT_API_KEY=user:xxxx WEB_EXT_API_SECRET=yyyy npx web-ext sign --channel unlisted
  ```
  O `.xpi` sai em `web-ext-artifacts/`; arraste-o para o Firefox. "Unlisted" não publica na loja.

### 3. Celular

1. No mesmo Wi-Fi, abra `http://IP-DO-PC:8765/` (o IP aparece no log do agente).
2. Use **Adicionar à tela inicial** no navegador do celular.
3. Em **Máquinas cadastradas**, adicione os outros PCs por nome e IP. A lista fica salva no celular.

## Desenvolvimento

- O código da extensão fica em `extensao/chromium/`. Depois de editar, rode
  `extensao/sincronizar.sh` (o Firefox não segue links simbólicos, então os arquivos são copiados).
- Validar a extensão do Firefox: `cd extensao/firefox && npx web-ext lint`.
- Rodar o agente em primeiro plano: `python3 agente/agente.py` (ou `PULA_PORTA=8799 ...` para não
  conflitar com o serviço).
- Depois de mudar o agente: `systemctl --user restart pula-anuncio`. Depois de mudar a extensão:
  recarregue-a na página de extensões do navegador e recarregue a aba do YouTube.

## Limitações

- **Sem senha**: qualquer aparelho da rede local que acesse a porta 8765 controla o mouse e o
  teclado do PC. Use só em rede de casa confiável.
- **Pular anúncio** só funciona quando o botão "Pular" já apareceu, com a aba do YouTube visível
  (não minimizada nem atrás de outra aba). Anúncios sem botão não são pulados.
- Para clicar no botão, o agente traz o navegador para a frente por um instante e devolve o foco
  depois; se você estiver digitando em outra janela nesse momento, uma tecla pode cair no navegador.
- No Linux, o mouse exige um compositor com `zwlr_virtual_pointer_v1` (Hyprland, Sway e outros
  baseados em wlroots) e o pulo de anúncio usa `hyprctl`, então é específico do Hyprland.
  X11, GNOME e KDE não são suportados.
