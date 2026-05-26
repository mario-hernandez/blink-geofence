# blink-geofence

![blink-geofence](assets/hero.png)

**Local geofencing for Amazon Blink cameras on macOS. Your cameras disarm when you get home and re-arm when you leave — no IFTTT, no Alexa, no cloud, no subscription.**

`No cloud` · `No subscription` · `100% local` · `macOS`

Blink has no real geofencing. The result is the classic annoyance: motion notifications while you're at home, or cameras that never arm when you leave. **blink-geofence** fixes that with a small local setup: a macOS Shortcuts automation detects when your Mac joins your home Wi-Fi and offers to disarm your cameras for a few hours; a background LaunchAgent re-arms them automatically and *forces* arming during a night window or whenever you're away from home.

> ⚠️ **Disclaimer.** This project is **not affiliated with Amazon or Blink**. It relies on an **unofficial API** (via [`blinkpy`](https://github.com/fronzbot/blinkpy)) that Amazon can change or break at any time, and automated use could get your account flagged. Provided **AS IS, with no warranty**. **Do not rely on it for life-safety or critical security** — it is a convenience layer, not an alarm system. See [Limitations](#limitations).

## Why this vs. the alternatives

| | blink-geofence | IFTTT | Alexa Routines | Home Assistant |
|---|---|---|---|---|
| No cloud account required | ✅ | ❌ | ❌ | ⚠️ |
| Cost | Free | Paid tier | Free* | 24/7 server |
| Forced night-time arming | ✅ | ❌ | ❌ | Manual |
| Away-from-home arming | ✅ | ⚠️ | ⚠️ | ✅ |
| Setup | A few commands | OK | OK | Hours |

## How it works

```
You join your home Wi-Fi  (macOS Shortcuts automation)
  └─→ Native dialog: "Disarm cameras for 5h?"
        └─→ run.sh disarm-for 5
              ├─→ Disarms your target sync module(s) (via blinkpy)
              └─→ Writes ~/.config/blink/rearm_at (timestamp +5h)

LaunchAgent "blink-geofence", every 5 minutes
  └─→ run.sh enforce-policy        (top-to-bottom priority)
        ├─→ In night window?        → ARM (overrides disarm)
        ├─→ Away from home?         → ARM (overrides disarm)
        ├─→ rearm_at expired?       → ARM + clear file
        └─→ nothing applies         → respect the current disarm
```

Presence is detected by the **router's MAC address** (via `arp`), not the SSID, because recent macOS redacts the SSID without Location permissions while the gateway MAC is not redacted.

## Requirements

- macOS (uses Shortcuts.app + launchd)
- Python 3.11+
- An Amazon Blink account with at least one Sync Module

## Install

```bash
git clone https://github.com/<you>/blink-geofence.git
cd blink-geofence

# 1. Dependencies in a venv
./install.sh

# 2. Authenticate with Blink (interactive: email + password + 2FA code)
./run.sh setup

# 3. Choose which sync modules this tool may control (others are NEVER touched)
./run.sh status                      # list all sync modules in your account
./run.sh targets "Living Room"       # only these respond to arm/disarm

# 4. Save your home network fingerprint (run while connected to home Wi-Fi)
./run.sh set-home

# 5. Install the background enforcement (every 5 min)
./install-launchagent.sh
```

## macOS Shortcuts automation

Open **Shortcuts.app → Automation → +** and configure:

**Trigger:** Wi-Fi → your home network → *When joined* → **Run immediately**.

**Actions:**
1. **Choose from Menu** — prompt `Disarm cameras for 5h?`, options `Yes, disarm 5h` / `No, keep armed`.
2. Under *Yes*: **Run Shell Script** → `/full/path/to/blink-geofence/run.sh disarm-for 5`
3. *(optional)* Under *Yes*: **Show Notification** confirming the action.

The first time it runs, macOS asks permission to run shell scripts — accept once.

## Commands

| Command | What it does |
|---|---|
| `./run.sh setup` | Interactive Blink auth (email + password + 2FA) |
| `./run.sh targets ["<name>" ...]` | No args: show targets. With args: set them. |
| `./run.sh set-home` | Save the current router MAC as the home network |
| `./run.sh status` | Sync module state + pending re-arm + guard state |
| `./run.sh arm` / `disarm` | Arm / disarm targets now |
| `./run.sh disarm-for <hours>` | Disarm + schedule re-arm in N hours |
| `./run.sh enforce-policy` | (LaunchAgent) Apply guards: night window, presence, re-arm |

## Configuration

Optional `~/.config/blink/config.json` (sensible defaults if absent):

```json
{
  "night_start": "01:00",
  "night_end": "09:00",
  "disarm_hours": 5
}
```

During `night_start`–`night_end` the cameras are force-armed regardless of any active disarm. Align this with a native **"Arm" schedule in the Blink app** as a robust backstop (see Limitations).

## Limitations

- **Mac asleep = no enforcement.** All logic runs on your Mac; launchd does not fire during deep sleep, only on wake. If you disarm at night and close the lid, the night window won't be enforced until the Mac wakes. **Backstop:** create a native *"Arm"* schedule in the Blink app (runs in Blink's cloud, independent of your Mac). `blinkpy` cannot create schedules via API, so this is a one-time manual step in the app.
- **Fail-open today.** If `enforce-policy` errors (expired token, Blink API down), it logs and exits without changing state — cameras stay as they were. A security-conscious deployment should treat any failure as "keep armed" and notify; that hardening is on the roadmap.
- **Presence is spoofable.** The gateway MAC can be faked by an attacker in range. Low-probability vector, but real.
- **Unofficial API.** Amazon can break `blinkpy` or flag automated accounts without notice.

## Security & privacy

- Blink session tokens live in `~/.config/blink/session.json` (chmod 600). An attacker with access to your Mac (or an unencrypted backup) could control your cameras. Encrypt your backups.
- Never commit `~/.config/blink/` — it is outside the repo and git-ignored by design.

## Files

| Path | Contents |
|---|---|
| `~/.config/blink/session.json` | Blink OAuth session (chmod 600) |
| `~/.config/blink/targets.json` | Sync modules under control |
| `~/.config/blink/home_network.json` | Home router MAC for presence |
| `~/.config/blink/config.json` | Night window + default disarm hours |
| `~/.config/blink/rearm_at` | Pending re-arm timestamp (only while a disarm-for is active) |
| `~/.config/blink/blink.log` | Operation log |
| `~/Library/LaunchAgents/blink-geofence.plist` | LaunchAgent definition |

## Uninstall

```bash
launchctl bootout "gui/$UID/blink-geofence"
rm ~/Library/LaunchAgents/blink-geofence.plist
rm -rf ~/.config/blink          # optional: removes session + config
# Remove the Shortcuts automation in Shortcuts.app
```

## License

MIT — see [LICENSE](LICENSE). This software is not affiliated with Amazon or Blink.
