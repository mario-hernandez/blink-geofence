# blink-setup-cameras

> Si llegas al proyecto sin contexto, lee primero **[HANDOFF.md](HANDOFF.md)** — explica qué hay corriendo en el Mac, cómo verificarlo y cómo desinstalarlo. Este README es la guía de uso operativa.

Cuando tu Mac M2 Pro detecta que te has conectado al WiFi de casa (`MyHomeWiFi`), te pregunta con un diálogo nativo si quieres desactivar las cámaras Blink `Living Room` durante 5 horas. Si aceptas, las desarma y un LaunchAgent local las rearma automáticamente cuando vence el plazo. Las cámaras del Office (`Office A`, `Office B`) nunca se tocan.

## Arquitectura

```
WiFi MyHomeWiFi detectado (trigger nativo de Shortcuts.app)
   └─→ Atajo macOS muestra diálogo "¿Desarmar Blink 5h?"
         └─→ run.sh disarm-for 5
               ├─→ Desarma Living Room (vía blinkpy)
               └─→ Escribe ~/.config/blink/rearm_at con timestamp +5h

LaunchAgent blink-geofence cada 5 minutos
   └─→ run.sh check-rearm
         └─→ Si rearm_at venció: arma Living Room + borra archivo
```

## Stack

| Capa | Componente |
|---|---|
| API Blink | `blinkpy 0.25.5` (OAuth v2 con 2FA) |
| SSL | `certifi` (macOS Python no trae CA bundle) |
| Trigger WiFi | `Shortcuts.app` nativa (sin daemons extra) |
| Confirmación | Diálogo modal nativo (acción "Choose from Menu") |
| Rearmado | LaunchAgent local, poll cada 5 min |
| Storage | `~/.config/blink/` (session, targets, rearm_at, logs) |

## Setup local (este Mac, una vez)

```bash
cd ~/Desarrollo/blink-setup-cameras

# 1. Instalar dependencias en venv
./install.sh

# 2. Autenticarte con Blink (interactivo: email + password + código 2FA)
./run.sh setup

# 3. Configurar qué sync modules controlan arm/disarm
./run.sh status                          # ver todos los sync modules
./run.sh targets "Living Room"      # solo este responderá al trigger

# 4. Probar el ciclo manualmente
./run.sh disarm-for 0.001                # desarma + rearmado a ~3.6s
./run.sh status                          # muestra disarmed + rearmado pendiente
sleep 5
./run.sh check-rearm                     # detecta vencimiento, rearma
./run.sh status                          # vuelve a armed

# 5. Instalar el LaunchAgent (rearmado automático a 5h)
./install-launchagent.sh
```

## Atajo macOS Shortcuts.app

Abre **Shortcuts.app → sidebar "Automatización" → "+"** y configura:

### Trigger

| Campo | Valor |
|---|---|
| Tipo | **Wi-Fi** |
| Red | `MyHomeWiFi` |
| Disparar | **Cuando se una a esta red** |
| Ejecución | **Ejecutar inmediatamente** (no pedir confirmación del atajo — el atajo ya pregunta por su cuenta) |

### Acciones

**1. "Choose from Menu"** (Elegir del menú)
- Prompt: `¿Desactivar Blink Living Room 5h?`
- Opciones:
  - `Sí, desactivar 5h`
  - `No, dejar armado`

**2. Bajo la rama "Sí, desactivar 5h": "Run Shell Script"** (Ejecutar script de shell)
- Shell: `/bin/zsh`
- Pass input: `to script as arguments` (no importa, no usa stdin)
- Script:
  ```
  /path/to/blink-geofence/run.sh disarm-for 5
  ```

**3. (opcional) Bajo "Sí, desactivar 5h": "Show Notification"**
- Title: `Blink`
- Body: `Living Room desarmado 5h. Rearmado automático al vencer.`

La rama "No, dejar armado" queda vacía (no hacer nada).

### Primera ejecución

La primera vez que el atajo dispare, macOS te pedirá permiso para "Run Shell Script". Acepta. Después funciona en silencio.

Si quieres probarlo sin esperar a llegar a casa: abre la app Shortcuts, busca tu automatización en la lista, y dale al botón "Run" manualmente.

## Comandos

| Comando | Qué hace |
|---|---|
| `./run.sh setup` | Auth interactiva con Blink (email + password + 2FA) |
| `./run.sh targets ["<nombre>" ...]` | Sin args: muestra targets. Con args: los sobreescribe. |
| `./run.sh status` | Estado de todos los sync modules + rearmado pendiente si lo hay |
| `./run.sh arm` | Arma targets ahora |
| `./run.sh disarm` | Desarma targets ahora |
| `./run.sh disarm-for <horas>` | Desarma + programa rearmado en N horas |
| `./run.sh check-rearm` | (interno, lo llama el LaunchAgent) Si rearm_at venció, rearma |

## Archivos

| Path | Contenido |
|---|---|
| `~/.config/blink/session.json` | Sesión OAuth Blink (chmod 600) |
| `~/.config/blink/targets.json` | Lista de sync modules controlados |
| `~/.config/blink/rearm_at` | Timestamp ISO de cuándo rearmar (existe solo si hay disarm-for activo) |
| `~/.config/blink/blink.log` | Log de operaciones de blink_control.py |
| `~/.config/blink/launchagent.{out,err}` | Stdout/stderr del LaunchAgent |
| `~/Library/LaunchAgents/blink-geofence.plist` | Definición del LaunchAgent |

## Desinstalar

```bash
# Quitar el LaunchAgent
launchctl bootout "gui/$UID/blink-geofence"
rm ~/Library/LaunchAgents/blink-geofence.plist

# Borrar config (opcional)
rm -rf ~/.config/blink

# Quitar el atajo: Shortcuts.app → click derecho en la automatización → Borrar
```

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ERROR [BlinkTwoFARequiredError]` en `setup` | Primera vez, normal | El script lo gestiona automáticamente: pega el código 2FA |
| `CERTIFICATE_VERIFY_FAILED` | Python sin CA bundle | Ya resuelto (`certifi` + SSL context custom) |
| `No hay sesión guardada` | Falta el primer `setup` | `./run.sh setup` |
| `No hay targets configurados` | Falta `targets` | `./run.sh targets "Living Room"` |
| Atajo no dispara al unirse al WiFi | Permisos no aceptados o "Ejecutar inmediatamente" desactivado | Shortcuts.app → revisar la automatización |
| El rearmado no sucede a las 5h | LaunchAgent no cargado o sesión Blink caducada | `launchctl print gui/$UID/blink-geofence` para diagnosticar; mirar `launchagent.err` |
| Sesión Blink caduca (raro, dura meses) | Token expiró | `./run.sh setup` de nuevo |
