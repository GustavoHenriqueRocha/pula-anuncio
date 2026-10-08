#!/usr/bin/env bash
# Gera o APK do controle sem Gradle: aapt2 + javac + d8 + apksigner.
#
#   android/compilar-apk.sh [saída.apk]      (padrão: ~/Downloads/pula-anuncio.apk)
#
# Precisa do JDK 17 e do Android SDK (build-tools 35 + platform 35). Caminhos:
#   ANDROID_BUILD=~/.local/share/android-build  (com jdk/ e sdk/ dentro)
# A chave de assinatura fica fora do repositório, em ~/.local/share/pula-anuncio/apk.jks;
# usar sempre a mesma permite atualizar o app no celular sem desinstalar.
set -euo pipefail

aqui="$(cd "$(dirname "$0")" && pwd)"
saida="${1:-$HOME/Downloads/pula-anuncio.apk}"
base="${ANDROID_BUILD:-$HOME/.local/share/android-build}"
export JAVA_HOME="$base/jdk"
export PATH="$JAVA_HOME/bin:$PATH"  # d8 e apksigner chamam "java" direto
java="$JAVA_HOME/bin"
bt="$base/sdk/build-tools/35.0.0"
plataforma="$base/sdk/platforms/android-35/android.jar"
chave="$HOME/.local/share/pula-anuncio/apk.jks"
senha_arq="$HOME/.local/share/pula-anuncio/apk.senha"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/res/mipmap-xxxhdpi" "$tmp/assets" "$tmp/classes" "$tmp/compilado"

# ícone (a partir do mesmo SVG da página) e a página em si
rsvg-convert -w 192 -h 192 "$aqui/../agente/web/icone.svg" -o "$tmp/res/mipmap-xxxhdpi/icone.png"
cp -r "$aqui/../agente/web" "$tmp/assets/web"

"$bt/aapt2" compile --dir "$tmp/res" -o "$tmp/res.zip"
"$bt/aapt2" link -o "$tmp/base.apk" -I "$plataforma" --manifest "$aqui/AndroidManifest.xml" \
    -A "$tmp/assets" "$tmp/res.zip"

"$java/javac" -source 8 -target 8 -Xlint:-options -bootclasspath "$plataforma" -classpath "$plataforma" \
    -d "$tmp/classes" $(find "$aqui/src" -name '*.java')
"$bt/d8" --min-api 24 --lib "$plataforma" --output "$tmp/compilado" $(find "$tmp/classes" -name '*.class')
(cd "$tmp/compilado" && zip -q "$tmp/base.apk" classes.dex)

"$bt/zipalign" -f -p 4 "$tmp/base.apk" "$tmp/alinhado.apk"

if [ ! -f "$chave" ]; then
    mkdir -p "$(dirname "$chave")"
    head -c 18 /dev/urandom | base64 > "$senha_arq"; chmod 600 "$senha_arq"
    "$java/keytool" -genkeypair -keystore "$chave" -alias pula -keyalg RSA -keysize 2048 -validity 36500 \
        -storepass "$(cat "$senha_arq")" -keypass "$(cat "$senha_arq")" -dname "CN=Pula Anuncio" >/dev/null
fi
"$bt/apksigner" sign --ks "$chave" --ks-pass "file:$senha_arq" --out "$saida" "$tmp/alinhado.apk"
echo "APK: $saida ($(du -h "$saida" | cut -f1))"
