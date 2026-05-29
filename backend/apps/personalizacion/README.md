# App `personalizacion`

DSL declarativo de personalización por empresa. Permite definir entidades, estados y vistas personalizadas sin desplegar código nuevo (ver [ADR-005](../../../docs/decisions/ADR-005-dsl-personalizacion-declarativo.md)).

**Prefijo API:** `/api/personalizacion/`

## Modelos

| Modelo | Descripción |
|---|---|
| `PersonalizacionConfig` | Configuración de personalización activa por empresa. |
| `EntidadInstancia` | Instancias de entidades definidas dinámicamente. |
| `EstadoPersonalizado` | Estados personalizados de workflows. |
| `VistaPersonalizada` | Definición de vistas/UI personalizadas. |

## Endpoints

Recurso REST (CRUD vía router): `configuraciones/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET configuraciones/activa/` | Configuración de personalización activa. |
| `POST configuraciones/{id}/activar/` | Activar una configuración. |
| `GET configuraciones/historial/` | Historial de configuraciones. |
