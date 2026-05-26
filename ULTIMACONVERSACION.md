# Última conversación

## Reanudar

```bash
cd ~/Desarrollo/blink-setup-cameras
claude --resume da717ab1-1141-4522-b90f-67083c633f99
```

## Fecha

2026-05-26

## Resumen

Sistema completo de auto-disarm Blink al llegar a casa: `blink_control.py` con OAuth v2 + 2FA, atajo macOS Shortcuts.app (`Blink: llegada a casa`) sobre WiFi `MyHomeWiFi`, LaunchAgent `blink-geofence` que ejecuta `enforce-policy` cada 5 min. Guards implementados: franja nocturna 02:00–09:00 siempre armado + presencia (fuera de la red de casa, detectada por MAC del router, fuerza armado). Documentado en `HANDOFF.md`, repo privado `OWNER/blink-geofence`.

Backstop nube configurado por Mario: schedule Blink "Arm 01:00" (solo arma). Franja del MacBook alineada a 01:00–09:00.

Pendiente: (1) verificar el trigger Wi-Fi del atajo (apunta a `MyHomeWiFi` + "Ejecutar inmediatamente"); (2) opcional: regla "al despertar en casa → desarmar" porque el schedule de Blink no desarma y por la mañana las cámaras siguen armadas hasta desarmar a mano.
