#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — bootstrap the project on a fresh machine.
#
# Creates .venv/ and installs blinkpy + aiohttp + certifi.
# Idempotent: reuses the venv if it already exists.
#
# After this script, run:
#   ./run.sh setup            (interactive auth: email + password + 2FA)
#   ./run.sh targets "..."    (which sync modules to control)
#   ./run.sh set-home         (save your home router MAC, while on home Wi-Fi)
#   ./install-launchagent.sh  (background enforcement every 5 min)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 not found. Install with: brew install python@3.12" >&2
    exit 1
fi

echo "→ Creating venv in .venv/"
python3 -m venv .venv

echo "→ Installing dependencies"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

chmod +x run.sh install-launchagent.sh 2>/dev/null || true

echo ""
echo "✓ Install complete."
echo ""
echo "Next steps:"
echo "    ./run.sh setup                  # interactive auth, once"
echo "    ./run.sh targets \"<SyncName>\"   # which sync modules to control"
echo "    ./run.sh set-home               # save home router MAC (on home Wi-Fi)"
echo "    ./install-launchagent.sh        # background enforcement every 5 min"
