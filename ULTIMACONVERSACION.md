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

Pendiente: (1) verificar el trigger Wi-Fi del atajo (apunta a `MyHomeWiFi` + "Ejecutar inmediatamente"); (2) backstop recomendado para el Mac dormido: schedule nativo "Arm 02:00" en la app Blink.
