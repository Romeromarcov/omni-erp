# App `core`

Núcleo del sistema: identidad, organización multi-tenant, seguridad y modelos base de los que dependen todas las demás apps. Aquí viven los modelos base (`OmniBaseModel`, `TimeStampedModel`), los mixins de integración, la autenticación JWT y las utilidades transversales (UUID7, validadores, almacenamiento, eventos, servidor MCP).

**Prefijo API:** `/api/core/` (la autenticación global vive bajo `/api/auth/*`, ver [`config/urls.py`](../../config/urls.py)).

## Modelos

| Modelo | Descripción |
|---|---|
| `Empresa` | Tenant raíz. Toda entidad de negocio cuelga de una empresa. |
| `Sucursal` | Sucursal de una empresa. |
| `Departamento` | Departamento dentro de una empresa/sucursal. |
| `Usuarios` | Usuario del sistema (extiende `AbstractUser`). |
| `Roles` / `Permisos` | Modelo de autorización (RBAC). |
| `RolPermisos` / `UsuarioRoles` | Tablas puente rol↔permiso y usuario↔rol. |
| `RegistroAuditoria` | Auditoría base de cambios. |
| `Dispositivo` | Dispositivos de usuario (fingerprint) para login y cajas físicas. |
| `CapabilityToken` | Tokens de capacidad (acceso acotado). |
| `Contacto` | Contactos genéricos reutilizables. |
| `ConfiguracionFlujoDocumentos` | Configuración del flujo documental por empresa. |
| `Notificacion` | Notificaciones de usuario. |

Archivos de soporte relevantes: `base_models.py` (modelos/mixins base), `serializers_base.py`, `auth_views.py` (login/JWT), `permissions.py`, `uuid.py` (UUID7), `validators.py`, `storage.py`, `email_service.py`, `events.py`, `mcp_server.py`, `signals.py`.

## Endpoints

### Recursos REST (CRUD vía router)

`usuarios/`, `empresas/`, `sucursales/`, `departamentos/`, `dispositivos/`, `roles/`, `permisos/`, `contactos/`, `flujo-documentos/`, `notificaciones/`.

### Rutas y acciones adicionales

| Ruta | Descripción |
|---|---|
| `GET usuarios/me/` | Usuario autenticado actual. |
| `POST usuarios/change_password/` | Cambio de contraseña del usuario. |
| `POST dispositivos/accion/` | Acciones sobre dispositivo (crear caja, abrir sesión, etc.). |
| `GET dashboard/kpis/` | KPIs del dashboard. |
| `GET dashboard/stats/` | Estadísticas del dashboard. |
| `GET usuario_roles/` | Listado usuario↔roles. |
| `... / <uuid>/` | Detalles de empresa, sucursal, usuario y departamento. |

ViewSets con acciones `activar` / `desactivar` (empresas, sucursales, etc.) y `marcar_leida` / `marcar_todas_leidas` / `no_leidas` (notificaciones).

> Detección de dispositivos y cajas físicas: ver [`README_dispositivos.md`](README_dispositivos.md).
