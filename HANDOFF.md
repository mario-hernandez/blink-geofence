# HANDOFF — blink-setup-cameras

> Documento de traspaso. Léelo primero si llegas al proyecto sin contexto. El README es la guía de uso; este HANDOFF explica qué hay corriendo en el Mac y por qué.

## Resumen en 30 segundos

Sistema local en este Mac (M2 Pro de Mario) que automatiza un caso muy concreto:

- **Trigger**: el Mac detecta que se ha conectado al WiFi `MyHomeWiFi` (casa de Mario).
- **Acción**: muestra un diálogo nativo preguntando si desactivar las cámaras Blink de casa (`Living Room`) durante 5 horas.
- **Si Mario confirma**: desarma las cámaras y programa el rearmado automático.
- **Pasadas las 5 h**: un servicio en background rearma las cámaras por su cuenta.
- **Guards de seguridad** (overrides que fuerzan armado pese al desarmado):
  - **Franja nocturna 01:00–09:00**: siempre armadas (vigilancia mientras duerme).
  - **Fuera de casa**: si el Mac no está en la red de casa, siempre armadas.
- **Las cámaras del Office (company) nunca se tocan.**

## Componentes instalados en este Mac

| # | Componente | Identificador | Para qué |
|---|---|---|---|
| 1 | Atajo Shortcuts.app | `Blink: llegada a casa` | Detecta WiFi `MyHomeWiFi` y dispara el diálogo |
| 2 | LaunchAgent | `blink-geofence` | Cada 5 min ejecuta `enforce-policy` (guards + rearmado) |
| 3 | venv Python | `~/Desarrollo/blink-setup-cameras/.venv/` | `blinkpy 0.25.5` + `aiohttp` + `certifi` |
| 4 | Sesión OAuth Blink | `~/.config/blink/session.json` | Tokens de auth (dura meses) |
| 5 | Targets | `~/.config/blink/targets.json` | Lista de sync modules controlables (`Living Room`) |
| 6 | Huella red de casa | `~/.config/blink/home_network.json` | MAC del router de casa (`aa:bb:cc:dd:ee:ff`) para detectar presencia |
| 7 | Logs | `~/.config/blink/blink.log` y `launchagent.{out,err}` | Auditoría y debug |

## Lógica de la política (enforce-policy)

Cada 5 min el LaunchAgent ejecuta `enforce-policy`, que decide si forzar armado según esta prioridad:

1. **¿Es 01:00–09:00 (local)?** → ARMAR (franja nocturna). Anula cualquier desarmado en curso.
2. **¿Estamos fuera de casa?** (MAC del gateway ≠ `home_network.json`) → ARMAR (presencia). Anula desarmado.
3. **¿Venció el disarm-for?** (`rearm_at` pasado) → ARMAR (rearmado por tiempo).
4. Si nada aplica → no toca nada: respeta el desarmado legítimo (en casa, de día, dentro de las 5 h).

La detección de presencia usa la **MAC del router** y no el SSID porque macOS censura el SSID (`<redacted>`) sin permisos de Localización; la MAC del gateway vía `arp` no está censurada.

## ⚠️ Limitación importante: el Mac dormido

Todo el enforcement (rearmado y guards) corre en el LaunchAgent de **este Mac**. launchd NO ejecuta el job mientras el Mac está en sleep profundo — lo ejecuta una vez al despertar. Consecuencias:

- Si Mario desarma de noche y el Mac duerme antes de la 01:00, **la franja nocturna del MacBook no se aplica hasta que el Mac despierte**.
- Si Mario desarma, cierra el MacBook y se va, las cámaras quedarían desarmadas hasta que el Mac despierte o venza el `rearm_at`. **Esto lo cubre el backstop de abajo.**

**Backstop configurado (por Mario, 2026-05-26)**: en la **app Blink** hay un *schedule nativo* "Arm a la 01:00" para `Living Room`. Corre en la nube de Blink, independiente del Mac, y garantiza armado nocturno aunque el Mac esté dormido o apagado. **Solo arma, no desarma** (el desarmado lo controla este sistema vía el atajo de llegada). La franja del MacBook (`FORCED_ARM_START = 01:00`) está alineada con este schedule. Nota: blinkpy NO puede crear/leer schedules por API, así que este evento solo se gestiona desde la app Blink.

Todo el código del proyecto vive en **`~/Desarrollo/blink-setup-cameras/`** y está versionado en GitHub privado: `OWNER/blink-geofence`.

## Cómo verificar que sigue funcionando

```bash
cd ~/Desarrollo/blink-setup-cameras

# 1. La sesión Blink sigue viva → debe listar sync modules sin errores
./run.sh status

# 2. El LaunchAgent está cargado
launchctl print "gui/$UID/blink-geofence" | grep -E "state|run interval"

# 3. No hay errores recientes
tail -20 ~/.config/blink/blink.log
tail -20 ~/.config/blink/launchagent.err
```

Esperado:
- `status` muestra 3 sync modules. `Living Room` lleva `→ TARGET`.
- `launchctl print` muestra `state = waiting` y `run interval = 300 seconds`.
- Logs sin tracebacks.

## Cómo probarlo manualmente sin esperar a llegar a casa

```bash
# Simula la confirmación del atajo con un rearmado muy corto
./run.sh disarm-for 0.001    # desarma + programa rearmado a ~3.6s
./run.sh status              # verás "vencido — pendiente check-rearm"
./run.sh check-rearm         # arma + limpia el archivo
./run.sh status              # vuelve a armado limpio
```

Para probar el atajo (sin ir al WiFi de casa): abre Shortcuts.app, encuentra "Blink: llegada a casa" en la lista, dale al botón Run. Debería aparecer el diálogo.

## Cómo desinstalar todo

```bash
# 1. Detener y borrar el LaunchAgent
launchctl bootout "gui/$UID/blink-geofence"
rm ~/Library/LaunchAgents/blink-geofence.plist

# 2. Borrar el atajo: Shortcuts.app → click derecho en "Blink: llegada a casa" → Eliminar

# 3. (Opcional) Borrar config y sesión Blink
rm -rf ~/.config/blink

# 4. (Opcional) Borrar el repo local
rm -rf ~/Desarrollo/blink-setup-cameras
```

## Cómo recuperarte si algo va mal

| Síntoma | Diagnóstico | Solución |
|---|---|---|
| Las cámaras no se rearman tras 5 h | LaunchAgent no carga o falla | `launchctl print "gui/$UID/blink-geofence"` + revisar `launchagent.err` |
| El atajo no dispara al unirse al WiFi | Permiso "Run Shell Script" no aceptado o "Run immediately" desactivado | Shortcuts.app → revisar la automatización; ejecutarla manualmente una vez |
| `./run.sh status` da `Authentication failed` | Tokens Blink caducados (raro, dura meses) | `./run.sh setup` y vuelve a configurar la sesión |
| `CERTIFICATE_VERIFY_FAILED` | Python sin CA bundle | Ya resuelto en código (forzamos certifi). Si reaparece tras actualizar Python: `.venv/bin/pip install --upgrade certifi` |
| `No hay targets configurados` | Borraste `targets.json` o no se hizo en el setup | `./run.sh targets "Living Room"` |
| Por error se desarmaron cámaras del Office | Targets mal configurados | Revisar con `./run.sh targets` (sin args). Debe listar SOLO `Living Room`. Si hay otras, `./run.sh targets "Living Room"` para sobrescribir |

## Stack y decisiones técnicas

**Por qué `blinkpy` en vez de IFTTT/Alexa**: 100% local, sin coste, sin dependencias en servicios de terceros que puedan deprecarse.

**Por qué Python en venv en vez del Python del sistema**: el Python de macOS no incluye `certifi` actualizado y la cuenta Blink usa una CA que macOS sí tiene en su keychain pero Python no ve. Aislamos dependencias en `.venv/`.

**Por qué Shortcuts.app y no Hammerspoon u otro WiFi watcher**: trigger nativo del sistema, mantenido por Apple, sin daemons adicionales y sin permisos de accesibilidad/automation que requeriría Hammerspoon.

**Por qué LaunchAgent con poll cada 5 min y no `at`**: `atd` viene desactivado en macOS Sequoia/Tahoe (requiere `sudo` y se reactiva tras updates). LaunchAgent es la forma oficial Apple para tareas periódicas user-level y sobrevive a reinicios sin trucos.

**Por qué un solo target (`Living Room`)**: la cuenta Blink incluye tres sync modules. Los dos del Office (company) **NUNCA** deben tocarse desde este sistema — son cámaras de oficina con su propio ritmo y dueños múltiples. El filtro de targets es la salvaguarda.

## Roadmap

### Implementado (sesión 2026-05-26)

- ✅ **Horario forzado 01:00–09:00**: la franja nocturna fuerza armado y anula cualquier `disarm-for` activo. Constantes `FORCED_ARM_START` / `FORCED_ARM_END` en `blink_control.py`.
- ✅ **Presencia obligatoria fuera de casa**: detección por MAC del router (`set-home` + `home_network.json`). Si la MAC del gateway no coincide, fuerza armado.
- ✅ **enforce-policy**: comando unificado que el LaunchAgent ejecuta cada 5 min (reemplazó a `check-rearm`).

- ✅ **Schedule nativo Blink "Arm 01:00"** (configurado por Mario en la app, 2026-05-26): backstop nocturno robusto frente al Mac dormido. Solo arma, no desarma.

### Pendiente

- ⏳ Verificar el trigger Wi-Fi del atajo "Blink: llegada a casa" (que apunte a `MyHomeWiFi` + "Ejecutar inmediatamente").
- 💡 Posible mejora: si se quiere desarmar automáticamente al despertar en casa (sin re-confirmar el diálogo), habría que añadir una regla "en casa + fuera de franja → desarmar". No pedido aún; el modelo actual es "desarmado opt-in vía diálogo de llegada". Relevante porque el schedule de Blink arma a la 01:00 y no desarma, así que por la mañana en casa las cámaras siguen armadas hasta que Mario las desarme (atajo de llegada o manual).

## Contacto

Mario Hernández — `developer@supera.dev`. Proyecto personal, no productivo. Repo: `OWNER/blink-geofence` (privado).
