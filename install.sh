#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — bootstrap del proyecto en una máquina nueva.
#
# Crea .venv/ y instala blinkpy + aiohttp + certifi.
# Idempotente: si ya hay venv, lo reusa.
#
# Tras este script, ejecuta:
#   ./run.sh setup            (auth interactiva con email + password + 2FA)
#   ./run.sh targets "..."    (qué sync modules controlar)
#   ./install-launchagent.sh  (rearmado automático)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 no encontrado. Instala con: brew install python@3.12" >&2
    exit 1
fi

echo "→ Creando venv en .venv/"
python3 -m venv .venv

echo "→ Instalando dependencias"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

chmod +x run.sh install-launchagent.sh 2>/dev/null || true

echo ""
echo "✓ Instalación lista."
echo ""
echo "Siguientes pasos:"
echo "    ./run.sh setup                    # auth interactiva, 1 vez"
echo "    ./run.sh targets \"<NombreSync>\"   # qué sync modules controlar"
echo "    ./install-launchagent.sh          # rearmado automático cada 5 min"
