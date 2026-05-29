# App `gestion_aprobaciones`

Motor de flujos de aprobación: define tipos de aprobación y flujos multi-etapa, y gestiona las solicitudes y sus registros de decisión. Usado transversalmente por compras, gastos, nómina, etc.

**Prefijo API:** `/api/gestion-aprobaciones/`

## Modelos

| Modelo | Descripción |
|---|---|
| `TipoAprobacion` | Tipo de aprobación (qué se aprueba). |
| `FlujoAprobacion` | Flujo multi-etapa con reglas de aprobadores. |
| `SolicitudAprobacion` | Solicitud concreta en curso. |
| `RegistroAprobacion` | Registro de cada decisión (aprobado/rechazado) en una etapa. |

## Endpoints

Recursos REST (CRUD vía router): `tipos-aprobacion/`, `flujos-aprobacion/`, `solicitudes-aprobacion/`, `registros-aprobacion/`.
