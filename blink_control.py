#!/usr/bin/env python3
"""
blink_control.py — Control programático de cámaras Blink.

Forma parte del proyecto blink-setup-cameras. Sirve dos roles:

  1) CLI manual desde Terminal (./run.sh <comando>).
  2) Backend invocado por:
       - El atajo macOS "Blink: llegada a casa" (Shortcuts.app) cuando
         detecta que el Mac se ha unido al WiFi MyHomeWiFi.
       - El LaunchAgent "blink-geofence" que cada 5 minutos
         verifica si hay un rearmado pendiente de vencimiento.

Identificadores clave (búscalos en el sistema):
  - LaunchAgent label:   blink-geofence
  - LaunchAgent plist:   ~/Library/LaunchAgents/blink-geofence.plist
  - Atajo Shortcuts:     "Blink: llegada a casa"
  - Directorio config:   ~/.config/blink/
  - Logs:                ~/.config/blink/blink.log

Comandos:
    ./run.sh setup                        Auth interactiva (1 vez): email + password + 2FA.
    ./run.sh targets [<nombre>...]        Sin args: muestra. Con args: configura sync modules.
    ./run.sh set-home                     Guarda la MAC del router actual como "red de casa".
    ./run.sh status                       Estado de sync modules + rearmado + guards.
    ./run.sh arm                          Arma targets ahora.
    ./run.sh disarm                       Desarma targets ahora.
    ./run.sh disarm-for <horas>           Desarma + programa rearmado en N horas.
    ./run.sh enforce-policy               (lo llama el LaunchAgent) Aplica guards: franja
                                          nocturna 01:00-09:00, presencia fuera de casa, y
                                          rearmado vencido → fuerza armado. Idempotente.
    ./run.sh check-rearm                  (legacy) Solo el rearmado por tiempo, sin guards.
"""

import asyncio
import json
import logging
import os
import re
import ssl
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from getpass import getpass
from pathlib import Path

import certifi
from aiohttp import ClientSession, TCPConnector
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink


# ─────────────────────────────────────────────────────────────────────────────
# Rutas y configuración
# ─────────────────────────────────────────────────────────────────────────────

# Todo se guarda en ~/.config/blink/ con permisos 600/700 — no se versiona
# (ver .gitignore). El directorio se crea automáticamente en el primer uso.
CONFIG_DIR = Path.home() / ".config" / "blink"

# Tokens OAuth de la sesión Blink. Persisten varios meses sin re-auth.
SESSION_FILE = CONFIG_DIR / "session.json"

# Lista de sync modules a controlar. Sin esto, arm/disarm fallan a propósito
# (no queremos tocar TODOS los sync modules de la cuenta por accidente —
# en particular, hay sync modules del Office que no deben tocarse).
TARGETS_FILE = CONFIG_DIR / "targets.json"

# Timestamp ISO de cuándo rearmar. Solo existe si hay un disarm-for activo.
# El LaunchAgent lo lee cada 5 min y, si está vencido, arma + borra archivo.
REARM_FILE = CONFIG_DIR / "rearm_at"

# Huella de la red de casa: la MAC del router (gateway). La usamos en vez del
# SSID porque macOS reciente CENSURA el SSID (lo devuelve como "<redacted>")
# sin permisos de Localización, pero la MAC del gateway vía ARP no está sujeta
# a esa censura y es igual de única/estable.
HOME_NETWORK_FILE = CONFIG_DIR / "home_network.json"

# Log de operaciones (rotación manual si crece — bajo volumen, no urgente).
LOG_FILE = CONFIG_DIR / "blink.log"

# ─────────────────────────────────────────────────────────────────────────────
# Política de guards (overrides que FUERZAN armado)
# ─────────────────────────────────────────────────────────────────────────────

# Franja nocturna: entre estas horas (local) las cámaras se fuerzan armadas
# pase lo que pase, anulando cualquier disarm-for activo. Vigilancia mientras
# se duerme. Alineada con el schedule nativo de Blink (Arm 01:00), que es el
# backstop robusto cuando el Mac está dormido (ver HANDOFF).
FORCED_ARM_START = time(1, 0)   # 01:00
FORCED_ARM_END = time(9, 0)     # 09:00


def _setup_logging():
    """Inicializa el log de operaciones. CONFIG_DIR queda con permisos 700."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


log = logging.getLogger("blink_control")


def _make_session() -> ClientSession:
    """
    Crea un aiohttp.ClientSession con el bundle de CAs de certifi.

    macOS no expone su CA store al Python de python.org / Homebrew, así que
    sin esto cualquier petición HTTPS a Blink falla con
    SSL: CERTIFICATE_VERIFY_FAILED. certifi viene como dependencia transitiva
    de aiohttp/blinkpy, así que no añade peso extra.
    """
    ctx = ssl.create_default_context(cafile=certifi.where())
    return ClientSession(connector=TCPConnector(ssl=ctx))


# ─────────────────────────────────────────────────────────────────────────────
# Targets (qué sync modules controla arm/disarm)
# ─────────────────────────────────────────────────────────────────────────────

def _load_targets() -> list[str] | None:
    """Devuelve la lista de nombres configurados, o None si el archivo no existe."""
    if not TARGETS_FILE.exists():
        return None
    with open(TARGETS_FILE) as f:
        data = json.load(f)
    return data.get("targets", [])


def _save_targets(names: list[str]):
    """Sobrescribe la config de targets con la lista dada (chmod 600)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TARGETS_FILE, "w") as f:
        json.dump({"targets": names}, f, indent=2, ensure_ascii=False)
    os.chmod(TARGETS_FILE, 0o600)


# ─────────────────────────────────────────────────────────────────────────────
# Detección de red de casa (por MAC del gateway, no por SSID)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_mac(mac: str) -> str:
    """Canoniza una MAC a 'aa:bb:cc:dd:ee:ff' (arp puede omitir el padding 0)."""
    try:
        return ":".join(f"{int(p, 16):02x}" for p in mac.split(":"))
    except (ValueError, AttributeError):
        return (mac or "").lower()


def _gateway_mac() -> str | None:
    """
    MAC del router de la red actual, o None si no hay gateway (sin red).

    route -n get default  → IP del gateway
    arp -n <ip>           → MAC del gateway
    Ambos son comandos del sistema, rápidos y sin permisos especiales.
    """
    try:
        out = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        m = re.search(r"gateway:\s*([\d.]+)", out)
        if not m:
            return None
        gw_ip = m.group(1)

        arp_out = subprocess.run(
            ["arp", "-n", gw_ip],
            capture_output=True, text=True, timeout=5,
        ).stdout
        mac = re.search(r"([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})", arp_out)
        return _normalize_mac(mac.group(1)) if mac else None
    except Exception:
        return None


def _load_home_mac() -> str | None:
    """MAC del router de casa guardada con `set-home`, o None si no configurada."""
    if not HOME_NETWORK_FILE.exists():
        return None
    with open(HOME_NETWORK_FILE) as f:
        return json.load(f).get("gateway_mac")


def _is_home() -> bool | None:
    """
    True si estamos en la red de casa, False si no, None si no se puede decidir.

    Devuelve None solo cuando NO hay huella de casa configurada — en ese caso
    enforce-policy NO debe forzar armado por presencia (no sabe dónde estás).
    Si hay huella pero no hay gateway actual (sin red), devuelve False (= fuera).
    """
    home = _load_home_mac()
    if home is None:
        return None
    current = _gateway_mac()
    if current is None:
        return False  # sin red conocida → tratamos como "fuera de casa"
    return _normalize_mac(current) == _normalize_mac(home)


def cmd_set_home():
    """Guarda la MAC del router actual como huella de la red de casa."""
    mac = _gateway_mac()
    if mac is None:
        raise SystemExit(
            "No se pudo detectar el gateway. ¿Estás conectado a la red de casa?"
        )
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(HOME_NETWORK_FILE, "w") as f:
        json.dump({"gateway_mac": mac}, f, indent=2)
    os.chmod(HOME_NETWORK_FILE, 0o600)
    print(f"✓ Red de casa guardada (MAC del router): {mac}")
    print(f"  en {HOME_NETWORK_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# Comandos
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_setup():
    """
    Auth interactiva (solo la primera vez en cada dispositivo).

    blinkpy 0.25.5 usa OAuth v2: el flow de 2FA lanza una excepción específica
    BlinkTwoFARequiredError en vez de pedir el código por stdin (como hacía la
    versión vieja). Aquí la capturamos, pedimos el código, y llamamos a
    complete_2fa_login() manualmente.
    """
    print("Setup interactivo de Blink (solo la primera vez)\n")
    username = input("Email Blink: ").strip()
    password = getpass("Password: ")

    async with _make_session() as session:
        blink = Blink(session=session)

        # OJO: Auth ignora el session del Blink si no se le pasa explícitamente,
        # y se crea uno propio sin contexto SSL. Hay que pasarle session=session
        # para que use nuestro bundle de certifi.
        blink.auth = Auth(
            {"username": username, "password": password},
            no_prompt=True,  # gestionamos el 2FA manualmente abajo
            session=session,
        )

        try:
            await blink.start()
        except BlinkTwoFARequiredError:
            print("\nBlink ha enviado un código 2FA a tu email/SMS.")
            code = input("Código 2FA: ").strip()
            ok = await blink.auth.complete_2fa_login(code)
            if not ok:
                raise SystemExit("Verificación 2FA falló. Revisa el código y reintenta.")
            # Tras 2FA ok, repetimos start() para cargar networks y sync modules.
            await blink.start()

        # Persiste tokens (incluye refresh_token). Reusable durante meses.
        await blink.save(str(SESSION_FILE))

    os.chmod(SESSION_FILE, 0o600)
    print(f"\n✓ Sesión guardada en {SESSION_FILE}")
    print("Ya puedes usar arm / disarm / status sin re-autenticarte.")


async def _load_blink(session):
    """
    Carga la sesión guardada y arranca Blink. Falla rápido si no hay session.

    No hace prompt de 2FA (no_prompt=True): si los tokens caducaron, mejor que
    falle visiblemente y el usuario ejecute setup de nuevo, en vez de quedarse
    colgado esperando input que nunca llegará (caso típico: ejecución desde
    LaunchAgent sin TTY).
    """
    if not SESSION_FILE.exists():
        raise SystemExit(
            f"No hay sesión guardada en {SESSION_FILE}.\n"
            f"Ejecuta primero: {sys.argv[0]} setup"
        )
    with open(SESSION_FILE) as f:
        creds = json.load(f)
    blink = Blink(session=session)
    blink.auth = Auth(creds, no_prompt=True, session=session)
    await blink.start()
    return blink


async def cmd_set_armed(armed: bool):
    """Arma o desarma SOLO los sync modules configurados como targets."""
    label = "armed" if armed else "disarmed"

    # Sin targets configurados, fallamos en vez de tocar todos los sync modules
    # de la cuenta (que incluyen los del Office, que NO deben tocarse).
    targets = _load_targets()
    if targets is None:
        raise SystemExit(
            f"No hay targets configurados. Ejecuta primero:\n"
            f"  {sys.argv[0]} targets \"NombreSyncModule\" [...]"
        )
    if not targets:
        raise SystemExit("Lista de targets vacía. Añade al menos uno con `targets <nombre>`.")

    async with _make_session() as session:
        blink = await _load_blink(session)
        if not blink.sync:
            raise SystemExit("No se encontraron sync modules en la cuenta.")

        # Aviso visible si la config se desincronizó del estado real de Blink
        # (ej. renombraste un sync module en la app y no actualizaste targets).
        missing = [n for n in targets if n not in blink.sync]
        if missing:
            print(f"Aviso: targets no encontrados (ignorados): {missing}", file=sys.stderr)

        applied = 0
        for name in targets:
            sync = blink.sync.get(name)
            if sync is None:
                continue
            await sync.async_arm(armed)
            log.info("%s -> %s", name, label)
            print(f"{name}: {label}")
            applied += 1
        if applied == 0:
            raise SystemExit("Ningún target válido en la cuenta. Revisa la config.")


async def cmd_status():
    """Muestra estado actual de todos los sync modules + rearmado pendiente."""
    targets = _load_targets() or []
    target_set = set(targets)

    async with _make_session() as session:
        blink = await _load_blink(session)
        # force=True para evitar cache: queremos el estado real, no el último visto.
        await blink.refresh(force=True)
        for name, sync in blink.sync.items():
            state = "armed" if sync.arm else "disarmed"
            mark = "→ TARGET" if name in target_set else ""
            print(f"{name}: {state} {mark}".rstrip())

    # Si hay rearmado programado, lo mostramos para diagnóstico.
    if REARM_FILE.exists():
        with open(REARM_FILE) as f:
            ts = datetime.fromisoformat(f.read().strip())
        local = ts.astimezone()
        remaining = ts - datetime.now(timezone.utc)
        if remaining.total_seconds() > 0:
            mins = int(remaining.total_seconds() // 60)
            print(f"\nRearmado programado: {local:%Y-%m-%d %H:%M} ({mins} min restantes)")
        else:
            print(f"\nRearmado programado: {local:%Y-%m-%d %H:%M} (vencido — pendiente enforce-policy)")

    # Estado de los guards (overrides que fuerzan armado).
    now_t = datetime.now().time()
    in_window = FORCED_ARM_START <= now_t < FORCED_ARM_END
    home = _is_home()
    home_txt = {True: "en casa", False: "FUERA de casa", None: "sin huella (set-home)"}[home]
    print("\nGuards:")
    print(f"  Franja nocturna {FORCED_ARM_START:%H:%M}-{FORCED_ARM_END:%H:%M}: "
          f"{'ACTIVA (forzaría armado)' if in_window else 'inactiva'}")
    print(f"  Presencia: {home_txt}"
          + ("  → forzaría armado" if home is False else ""))
    reason = _policy_reason()
    print(f"  Veredicto enforce-policy: "
          + (f"ARMAR ({reason})" if reason else "respeta estado actual"))


async def cmd_disarm_for(hours: float):
    """
    Desarma targets ahora y escribe rearm_at = ahora + hours.

    Lo llama el atajo Shortcuts "Blink: llegada a casa" cuando el usuario
    confirma "Sí, desactivar 5h" en el diálogo. El rearmado lo hará
    check-rearm cuando el LaunchAgent lo dispare tras vencer.
    """
    await cmd_set_armed(False)

    rearm_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(REARM_FILE, "w") as f:
        f.write(rearm_at.isoformat())
    os.chmod(REARM_FILE, 0o600)

    local = rearm_at.astimezone()
    print(f"\n→ Rearmado programado para {local:%Y-%m-%d %H:%M} ({hours}h)")
    log.info("disarm-for %sh, rearm_at=%s", hours, rearm_at.isoformat())


async def cmd_check_rearm():
    """
    Idempotente, silencioso si no hay nada que hacer.

    Ejecutado cada 5 min por el LaunchAgent blink-geofence.
    Si rearm_at existe Y ya pasó, arma targets y borra el archivo.
    En cualquier otro caso, sale sin hacer ruido (no spam de logs ni notifs).
    """
    if not REARM_FILE.exists():
        return

    with open(REARM_FILE) as f:
        rearm_at = datetime.fromisoformat(f.read().strip())
    now = datetime.now(timezone.utc)

    if now < rearm_at:
        # Aún no toca rearmar. Loggeamos cuánto falta para auditar comportamiento.
        log.info("check-rearm: %s restantes", rearm_at - now)
        return

    log.info("check-rearm: vencido (%s), armando targets", rearm_at.isoformat())
    await cmd_set_armed(True)
    REARM_FILE.unlink()
    print(f"✓ Rearmado tras vencer rearm_at = {rearm_at.isoformat()}")


def _rearm_due() -> bool:
    """True si hay un disarm-for activo cuyo plazo ya venció."""
    if not REARM_FILE.exists():
        return False
    with open(REARM_FILE) as f:
        rearm_at = datetime.fromisoformat(f.read().strip())
    return datetime.now(timezone.utc) >= rearm_at


def _policy_reason() -> str | None:
    """
    Decide si las cámaras DEBEN forzarse armadas y por qué. None = no forzar.

    Prioridad (de mayor a menor):
      1) franja-nocturna  → dentro de 01:00-09:00 local.
      2) fuera-de-casa    → hay huella de casa y NO estamos en ella.
      3) rearmado-vencido → el disarm-for activo ya cumplió su plazo.

    Si ninguna aplica, devuelve None y se respeta el desarmado en curso.
    """
    now_t = datetime.now().time()
    # La franja puede no cruzar medianoche (01:00 < 09:00), comparación directa.
    if FORCED_ARM_START <= now_t < FORCED_ARM_END:
        return "franja-nocturna"

    home = _is_home()
    # home is None → no hay huella configurada → no forzamos por presencia.
    if home is False:
        return "fuera-de-casa"

    if _rearm_due():
        return "rearmado-vencido"

    return None


async def cmd_enforce_policy():
    """
    Punto de entrada del LaunchAgent (cada 5 min). Idempotente y silencioso.

    Evalúa la política de guards y, si procede, ARMA los targets. Reemplaza a
    check-rearm: cubre el rearmado por tiempo Y los dos overrides (horario y
    presencia). Cuando arma por un override, anula el disarm-for en curso
    borrando rearm_at (el desarmado se considera consumido).

    Si la política no exige armado, NO toca nada: respeta un desarmado legítimo
    (en casa, de día, con disarm-for vigente).
    """
    reason = _policy_reason()
    if reason is None:
        log.info("enforce-policy: sin acción")
        return

    log.info("enforce-policy: armando por '%s'", reason)
    await cmd_set_armed(True)
    if REARM_FILE.exists():
        REARM_FILE.unlink()
    print(f"✓ Armado forzado por: {reason}")


def cmd_targets(names: list[str]):
    """Sin args: muestra la config actual. Con args: la sobrescribe."""
    if not names:
        targets = _load_targets()
        if targets is None:
            print(f"(sin targets configurados — {TARGETS_FILE} no existe)")
            return
        if not targets:
            print("(targets vacíos)")
            return
        for t in targets:
            print(t)
        return

    _save_targets(names)
    print(f"✓ Targets guardados en {TARGETS_FILE}:")
    for n in names:
        print(f"  - {n}")


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main():
    _setup_logging()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    cmd = sys.argv[1].lower()
    try:
        if cmd == "setup":
            asyncio.run(cmd_setup())
        elif cmd == "arm":
            asyncio.run(cmd_set_armed(True))
        elif cmd == "disarm":
            asyncio.run(cmd_set_armed(False))
        elif cmd == "disarm-for":
            if len(sys.argv) < 3:
                raise SystemExit("Uso: disarm-for <horas>")
            asyncio.run(cmd_disarm_for(float(sys.argv[2])))
        elif cmd == "check-rearm":
            asyncio.run(cmd_check_rearm())
        elif cmd == "enforce-policy":
            asyncio.run(cmd_enforce_policy())
        elif cmd == "set-home":
            cmd_set_home()
        elif cmd == "status":
            asyncio.run(cmd_status())
        elif cmd == "targets":
            cmd_targets(sys.argv[2:])
        else:
            print(__doc__)
            sys.exit(2)
    except SystemExit:
        raise
    except Exception as exc:
        # Tracebacks van al stderr Y al log: útil para debuggear el LaunchAgent
        # (cuyo stderr va a ~/.config/blink/launchagent.err) y para CLI manual.
        log.exception("Error ejecutando %s", cmd)
        import traceback
        print(f"ERROR [{type(exc).__name__}]: {exc!r}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
