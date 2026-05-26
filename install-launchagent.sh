#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# install-launchagent.sh — instala/recarga el LaunchAgent de rearmado.
#
# Qué es: un servicio macOS (user-level launchd) que ejecuta
# `run.sh enforce-policy` cada 5 minutos. Aplica los guards de seguridad:
#   - Franja nocturna 02:00-09:00 → fuerza armado.
#   - Fuera de casa (MAC del router != casa) → fuerza armado.
#   - disarm-for vencido → rearma.
# Si nada de eso aplica, respeta un desarmado legítimo (en casa, de día).
#
# Identificador completo (búscalo si dudas si está cargado):
#   Label:    blink-geofence
#   Plist:    ~/Library/LaunchAgents/blink-geofence.plist
#   Logs:     ~/.config/blink/launchagent.{out,err}
#
# Idempotente: si ya estaba cargado, lo recarga limpio (bootout + bootstrap).
# Sobrevive a reinicio del Mac (RunAtLoad=true + StartInterval=300).
#
# Para verificar después:
#   launchctl print "gui/$UID/blink-geofence" | head -20
#
# Para desinstalar:
#   launchctl bootout "gui/$UID/blink-geofence"
#   rm ~/Library/LaunchAgents/blink-geofence.plist
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="blink-geofence"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/.config/blink"

# Generamos el plist con paths absolutos resueltos en runtime, para que el
# proyecto sea portable: si lo mueves de directorio, basta con reinstalar.
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!--
  LaunchAgent del proyecto blink-setup-cameras.
  Generado por install-launchagent.sh. NO editar a mano — re-ejecuta el script.
  Repo: https://github.com/OWNER/blink-geofence
-->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/run.sh</string>
        <string>enforce-policy</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.config/blink/launchagent.out</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.config/blink/launchagent.err</string>
</dict>
</plist>
EOF

# bootout silencioso si ya estaba cargado (idempotencia).
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"

echo "✓ LaunchAgent cargado: $LABEL"
echo "  Plist:      $PLIST"
echo "  Intervalo:  cada 300s (5 min)"
echo "  Logs:       ~/.config/blink/launchagent.{out,err}"
echo ""
echo "Para desinstalar:"
echo "  launchctl bootout gui/\$UID/$LABEL && rm '$PLIST'"
