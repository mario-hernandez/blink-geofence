#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — single entry point for blink_control.py
#
# This wrapper is the only entry point the rest of the system uses:
#   - The macOS Shortcuts automation calls it as:
#         /path/to/blink-geofence/run.sh disarm-for 5
#   - The LaunchAgent (blink-geofence) calls it as:
#         /path/to/blink-geofence/run.sh enforce-policy
#   - You call it manually from a terminal:
#         ./run.sh status | arm | disarm | setup | targets | set-home | disarm-for | enforce-policy
#
# Responsibilities:
#   1) Ensure the right working directory (regardless of caller).
#   2) Activate the venv (.venv/) created by ./install.sh.
#   3) Delegate arguments to blink_control.py.
#
# Why not /usr/bin/env python3 directly: the venv carries certifi and blinkpy;
# the system Python does not.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "venv not found. Run ./install.sh first." >&2
    exit 1
fi

exec .venv/bin/python blink_control.py "$@"
