# App `gestion_aprobaciones`

Motor de flujos de aprobación: define tipos de aprobación y flujos multi-etapa por monto y `Departamento`, SLA en horas con escalación automática por Celery Beat aislada por tenant (`rls_tenant_context`), y gestiona las solicitudes y sus registros de decisión. Conectores opt-in para `REQUISICION_COMPRA`, `ORDEN_COMPRA`, `GASTO`, `PAGO_TERCERO` y `OPERACION_CAMBIO_DIVISA`.

**Prefijo API:** `/api/gestion-aprobaciones/`

## Modelos

| Modelo | Descripción |
|---|---|
| `TipoAprobacion` | Tipo de aprobación (qué se aprueba). |
| `FlujoAprobacion` | Flujo multi-etapa con reglas de aprobadores, `id_departamento`, `sla_horas` y escalación. |
| `SolicitudAprobacion` | Solicitud concreta en curso con reloj de etapa (`fecha_inicio_etapa`) y flag `escalada`. |
| `RegistroAprobacion` | Registro de cada decisión (aprobado/rechazado) en una etapa. |

## Endpoints, Celery y MCP

- Recursos REST (CRUD vía router): `tipos-aprobacion/`, `flujos-aprobacion/`, `solicitudes-aprobacion/`, `registros-aprobacion/`.
- Acción personalizada: `POST solicitudes-aprobacion/{id}/decidir/` (aprobar o rechazar la etapa actual).
- Tarea Celery Beat (`gestion_aprobaciones.escalar_solicitudes_vencidas`): evaluación periódica de SLA vencidos aislada por tenant.
- Herramientas MCP (`apps/gestion_aprobaciones/mcp.py`): `aprobaciones_pendientes` (`aprobaciones:read`), `aprobaciones_decidir` (`aprobaciones:write`).
