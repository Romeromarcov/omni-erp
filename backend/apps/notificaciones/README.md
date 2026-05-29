# App `notificaciones`

Sistema de notificaciones: plantillas, eventos disparadores, suscripciones de usuarios y log de envíos. Soporta múltiples canales (ver `CanalNotificacion`).

**Prefijo API:** `/api/notificaciones/`

## Modelos

| Modelo | Descripción |
|---|---|
| `PlantillaNotificacion` | Plantilla de mensaje por evento/canal. |
| `EventoNotificacion` | Evento de negocio que dispara notificaciones. |
| `SuscripcionNotificacion` | Suscripción de un usuario a eventos. |
| `LogNotificacion` | Registro de notificaciones enviadas. |
| `CanalNotificacion` | Enum de canales disponibles (email, push, etc.). |

## Endpoints

Recurso REST (CRUD vía router): `notificaciones/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET notificaciones/mis-notificaciones/` | Notificaciones del usuario autenticado. |
| `PATCH notificaciones/{id}/marcar-leida/` | Marcar una notificación como leída. |
