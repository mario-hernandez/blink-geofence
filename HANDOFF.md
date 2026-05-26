# HANDOFF — blink-setup-cameras

> Documento de traspaso. Léelo primero si llegas al proyecto sin contexto. El README es la guía de uso; este HANDOFF explica qué hay corriendo en el Mac y por qué.

## Resumen en 30 segundos

Sistema local en este Mac (M2 Pro de Mario) que automatiza un caso muy concreto:

- **Trigger**: el Mac detecta que se ha conectado al WiFi `MyHomeWiFi` (casa de Mario).
- **Acción**: muestra un diálogo nativo preguntando si desactivar las cámaras Blink de casa (`Living Room`) durante 5 horas.
- **Si Mario confirma**: desarma las cámaras y programa el rearmado automático.
- **Pasadas las 5 h**: un servicio en background rearma las cámaras por su cuenta.
- **Las cámaras del Office (company) nunca se tocan.**

## Componentes instalados en este Mac

| # | Componente | Identificador | Para qué |
|---|---|---|---|
| 1 | Atajo Shortcuts.app | `Blink: llegada a casa` | Detecta WiFi `MyHomeWiFi` y dispara el diálogo |
| 2 | LaunchAgent | `blink-geofence` | Cada 5 min comprueba si hay un rearmado pendiente |
| 3 | venv Python | `~/Desarrollo/blink-setup-cameras/.venv/` | `blinkpy 0.25.5` + `aiohttp` + `certifi` |
| 4 | Sesión OAuth Blink | `~/.config/blink/session.json` | Tokens de auth (dura meses) |
| 5 | Targets | `~/.config/blink/targets.json` | Lista de sync modules controlables (`Living Room`) |
| 6 | Logs | `~/.config/blink/blink.log` y `launchagent.{out,err}` | Auditoría y debug |

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

## Roadmap pendiente (pedido por Mario, sesión 2026-05-26)

Cuando se retome el trabajo, añadir capa de "guards" que ignoren la confirmación del atajo cuando las condiciones no se cumplan:

1. **Horario forzado armado**: entre 02:00 y 09:00 las cámaras deben estar siempre armadas, independientemente de lo que se haya pedido. Si Mario confirma "desarmar 5 h" a las 23:00, al llegar las 02:00 el sistema rearma automáticamente y cancela el rearmado de las 5 h (o el rearmado normal vuelve a operar tras las 09:00 si así lo decidimos).

2. **Presencia obligatoria**: si el Mac no está conectado a `MyHomeWiFi` (Mario fuera de casa), forzar armado. Hoy esto está implícito (no se dispara el trigger del atajo), pero como capa defensiva el LaunchAgent podría comprobar SSID actual y rearmar si no es el de casa, incluso si `rearm_at` aún no venció.

Diseño esbozado:
- Un comando nuevo `./run.sh enforce-policy` que evalúa: "¿es hora forzada? ¿estás en casa?" y arma si procede.
- El LaunchAgent llama a `enforce-policy` en vez de a `check-rearm` directamente (que pasa a ser una sub-operación interna).
- `enforce-policy` puede vetar incluso un `disarm-for` activo si las condiciones dicen lo contrario.

## Contacto

Mario Hernández — `developer@supera.dev`. Proyecto personal, no productivo. Repo: `OWNER/blink-geofence` (privado).
