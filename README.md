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
| **Esquerdo / Direito** | Toque = clique. **Segurar 1 s trava** o botão apertado (fica azul) para arrastar coisas; tocar de novo solta. |
| **Teclado** | O campo de texto digita no PC (acentos e corretor do celular funcionam). Teclas: Esc, Tab, setas, ⌫, Enter, Tela (F11), Início, Fim, play/pause e volume. |
| **Pular anúncio** | Não fica no celular: o agente de cada PC pula sozinho, sempre ligado. Quando o botão "Pular" do YouTube aparece, ele clica. |

O zoom por toque duplo fica bloqueado para não atrapalhar o touchpad.

## Estrutura

```
agente/
  agente.py              servidor HTTP + WebSocket; pulo de anúncio
  entrada.py             mouse e teclado virtuais (Wayland/Hyprland e Windows)
  web/                   página do celular (servida pelo agente)
  pula-anuncio.service   serviço systemd do usuário (Linux)
  instalar-windows.bat   instala no Windows: tarefa agendada escondida + firewall
  desinstalar-windows.bat  remove do Windows (os .ps1 ao lado fazem o trabalho)
android/
  compilar-apk.sh        gera o APK do controle (WebView com agente/web embutida)
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

**Windows** — roda escondido, sobe sozinho quando você entra no Windows e volta se cair
(igual ao serviço do Linux):

1. Instale o Python em https://python.org (marque **Add python.exe to PATH**).
2. Copie a pasta `agente` para o PC (por exemplo `C:\PulaAnuncio\agente`).
3. Dê dois cliques em **`instalar-windows.bat`** e aceite o pedido de administrador. Ele:
   - cria a tarefa agendada **Pula Anuncio** (ao entrar no Windows, sem janela, reinicia se cair);
   - libera a porta 8765 no firewall só para a rede local;
   - liga o agente na hora e mostra o IP para cadastrar no celular.
4. Para remover: **`desinstalar-windows.bat`**.

O agente precisa da sessão do usuário para mexer no mouse, por isso é tarefa agendada e não
serviço do Windows. Para ele ligar sem digitar senha quando o PC liga, ative o login automático
(`Win+R` → `netplwiz`). Se mudar a pasta de lugar, rode o instalador de novo.

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

**App Android** (recomendado): instale o `mouse.apk` (app "Mouse") (gerado por `android/compilar-apk.sh`,
sai em `~/Downloads`). É a mesma página, embutida num app: abre em tela cheia, não apaga a tela
e não precisa de um PC ligado para abrir. Cadastre as máquinas em **Máquinas cadastradas**.

**Pelo navegador**: no mesmo Wi-Fi, abra `http://IP-DO-PC:8765/` (o IP aparece no log do agente)
e use **Adicionar à tela inicial**.

A lista de máquinas fica salva no celular (no app e no navegador ficam listas separadas).

**IP mudou?** Cada máquina guarda o nome do PC. Se ela parar de responder, a página varre a rede
(254 endereços, alguns segundos) atrás do agente com esse nome e atualiza o IP sozinha. O botão
**🔎 Procurar PCs na rede** acha e cadastra todos os PCs com o agente. No app Android a busca
inclui a rede em que o celular está; no navegador, só as redes dos IPs já cadastrados (ou a que
você digitar no campo de IP).

**iPhone / pelo nome:** em vez do IP, use o nome do PC com `.local` (ex.: `arch-gustavo.local`).
O iPhone resolve `.local` sozinho (Bonjour), então o endereço não muda quando troca o IP ou o
Wi-Fi. No Linux precisa do `avahi-daemon` ligado; Windows 10/11 costuma responder ao nome também.
Abra `http://NOME.local:8765/` no Safari e use **Compartilhar → Adicionar à Tela de Início**.

## Desenvolvimento

- O código da extensão fica em `extensao/chromium/`. Depois de editar, rode
  `extensao/sincronizar.sh` (o Firefox não segue links simbólicos, então os arquivos são copiados).
- APK: `android/compilar-apk.sh [saída.apk]` monta sem Gradle (aapt2, javac, d8, apksigner). Precisa
  do JDK 17 e do Android SDK (build-tools e platform 35) em `~/.local/share/android-build/{jdk,sdk}`.
  A chave de assinatura fica em `~/.local/share/pula-anuncio/apk.jks`; sem ela, o celular não
  aceita atualizar o app por cima (tem que desinstalar antes).
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
