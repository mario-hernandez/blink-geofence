# blink-setup-cameras

**Automatización local para armar/desarmar cámaras Blink según tu presencia en casa, con vigilancia nocturna forzada. 100% local: sin IFTTT, sin Alexa, sin servicios de terceros ni costes.**

> Si llegas al proyecto sin contexto, lee primero **[HANDOFF.md](HANDOFF.md)** — explica qué hay corriendo en el Mac, cómo verificarlo y cómo desinstalarlo. Este README es la guía de uso operativa.

Cuando tu Mac M2 Pro detecta que te has conectado al WiFi de casa (`MyHomeWiFi`), te pregunta con un diálogo nativo si quieres desactivar las cámaras Blink `Living Room` durante 5 horas. Si aceptas, las desarma y un LaunchAgent local las rearma automáticamente cuando vence el plazo. Dos **guards** fuerzan armado pese al desarmado: la **franja nocturna 01:00–09:00** y la **ausencia de casa** (Mac fuera de la red de casa). Las cámaras del Office (`Office A`, `Office B`) nunca se tocan.

> ⚠️ Limitación: el enforcement corre en este Mac; si está en sleep profundo no se aplica hasta que despierte. El backstop es un **schedule nativo de Blink "Arm 01:00"** (configurado en la app, corre en la nube), que garantiza el armado nocturno aunque el Mac esté dormido. Detalle en [HANDOFF.md](HANDOFF.md).

## Arquitectura

```
WiFi MyHomeWiFi detectado (trigger nativo de Shortcuts.app)
   └─→ Atajo macOS muestra diálogo "¿Desarmar Blink 5h?"
         └─→ run.sh disarm-for 5
               ├─→ Desarma Living Room (vía blinkpy)
               └─→ Escribe ~/.config/blink/rearm_at con timestamp +5h

LaunchAgent blink-geofence cada 5 minutos
   └─→ run.sh enforce-policy   (prioridad de arriba a abajo)
         ├─→ ¿01:00-09:00?        → ARMA (anula desarmado)
         ├─→ ¿fuera de casa?      → ARMA (anula desarmado)
         ├─→ ¿rearm_at vencido?   → ARMA + borra archivo
         └─→ nada aplica          → respeta el desarmado en curso
```

## Comportamiento en un día típico

| Momento | Estado de `Living Room` | Quién lo decide |
|---|---|---|
| Llegas a casa (te unes al WiFi) | Diálogo "¿Desarmar 5h?" → si aceptas, **desarmado** | Atajo Shortcuts + MacBook |
| En casa, de día | **desarmado** (sin notificaciones molestas) | — |
| Sales de casa (dejas el WiFi) | **armado** (guard de presencia) | MacBook, si está despierto |
| **01:00** | **armado** siempre | Blink (nube) + refuerzo MacBook |
| 01:00–09:00 | **armado** siempre | Blink + MacBook |
| Pasan las 5h de un desarmado | **armado** (rearmado) | MacBook, si está despierto |
| Por la mañana en casa | sigue **armado** hasta que lo desarmes a mano | ver nota abajo |

> **Nota de diseño**: el schedule de Blink arma a la 01:00 pero **no desarma**. Por la mañana, estando en casa, las cámaras siguen armadas y pueden darte notificaciones al moverte, hasta que las desarmes (el atajo solo salta al *unirte* al WiFi, no estando ya conectado). Desármalas a mano (`./run.sh disarm` o ejecutando el atajo manualmente) o pídeme que añada la regla "al despertar en casa → desarmar".

## Stack

| Capa | Componente |
|---|---|
| API Blink | `blinkpy 0.25.5` (OAuth v2 con 2FA) |
| SSL | `certifi` (macOS Python no trae CA bundle) |
| Trigger WiFi | `Shortcuts.app` nativa (sin daemons extra) |
| Confirmación | Diálogo modal nativo (acción "Choose from Menu") |
| Presencia | MAC del router vía `arp` (el SSID está censurado por macOS) |
| Guards + rearmado | LaunchAgent local (`enforce-policy`), poll cada 5 min |
| Storage | `~/.config/blink/` (session, targets, home_network, rearm_at, logs) |

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

# 4. Guardar la huella de la red de casa (ejecutar CONECTADO al WiFi de casa)
./run.sh set-home                        # guarda la MAC del router como "casa"

# 5. Probar el ciclo manualmente
./run.sh disarm-for 0.001                # desarma + rearmado a ~3.6s
./run.sh status                          # muestra disarmed + rearmado + guards
sleep 5
./run.sh enforce-policy                  # aplica guards / rearmado
./run.sh status                          # vuelve a armed

# 6. Instalar el LaunchAgent (enforce-policy cada 5 min)
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
| `./run.sh set-home` | Guarda la MAC del router actual como huella de la red de casa |
| `./run.sh status` | Estado de sync modules + rearmado pendiente + estado de los guards |
| `./run.sh arm` | Arma targets ahora |
| `./run.sh disarm` | Desarma targets ahora |
| `./run.sh disarm-for <horas>` | Desarma + programa rearmado en N horas |
| `./run.sh enforce-policy` | (interno, lo llama el LaunchAgent) Aplica guards: franja nocturna, presencia, rearmado |
| `./run.sh check-rearm` | (legacy) Solo el rearmado por tiempo, sin guards |

## Archivos

| Path | Contenido |
|---|---|
| `~/.config/blink/session.json` | Sesión OAuth Blink (chmod 600) |
| `~/.config/blink/targets.json` | Lista de sync modules controlados |
| `~/.config/blink/home_network.json` | MAC del router de casa para detectar presencia |
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
| `status` dice "FUERA de casa" estando en casa | Cambiaste de router o la huella es vieja | `./run.sh set-home` conectado al WiFi de casa |
| Se arma sola al instalar disarm-for | Estás en franja 01:00–09:00 o fuera de casa (guard correcto) | Es el comportamiento esperado; revisa `./run.sh status` → sección Guards |
| Quiero cambiar la franja nocturna | Horas hardcodeadas | Edita `FORCED_ARM_START`/`FORCED_ARM_END` en `blink_control.py` |
| La franja nocturna no arma con el Mac dormido | launchd no corre en sleep profundo | Configura el schedule nativo de Blink (ver HANDOFF, sección "Mac dormido") |
