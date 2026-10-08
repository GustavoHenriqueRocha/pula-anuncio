#!/bin/sh
# O código-fonte fica em chromium/; o Firefox não segue links simbólicos, então copia.
cd "$(dirname "$0")" && cp chromium/background.js chromium/content.js firefox/
