#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — wrapper único para invocar blink_control.py
#
# Este wrapper es el ÚNICO punto de entrada visible al sistema:
#   - El atajo macOS "Blink: llegada a casa" lo llama con:
#         /path/to/blink-geofence/run.sh disarm-for 5
#   - El LaunchAgent blink-geofence lo llama con:
#         /path/to/blink-geofence/run.sh check-rearm
#   - El usuario lo llama manualmente desde Terminal:
#         ./run.sh status / arm / disarm / setup / targets / disarm-for / check-rearm
#
# Responsabilidades:
#   1) Asegurar cwd correcto (independiente de quién llama).
#   2) Activar el venv (.venv/) — instalado por ./install.sh.
#   3) Delegar argumentos a blink_control.py.
#
# Por qué no usar /usr/bin/env python3 directamente: el venv tiene certifi y
# blinkpy. El Python del sistema no.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "venv no encontrado. Ejecuta primero: ./install.sh" >&2
    exit 1
fi

exec .venv/bin/python blink_control.py "$@"
