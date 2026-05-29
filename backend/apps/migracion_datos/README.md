# App `migracion_datos`

Migración/importación de datos: plantillas de migración, procesos de importación y registro de errores por fila. Usada para cargar datos iniciales o migrar desde sistemas previos.

**Prefijo API:** `/api/migracion-datos/`

## Modelos

| Modelo | Descripción |
|---|---|
| `PlantillaMigracion` | Plantilla que define el mapeo de importación. |
| `ProcesoMigracion` | Ejecución de una migración. |
| `DetalleErrorMigracion` | Error detectado en una fila durante la migración. |

## Endpoints

Recursos REST (CRUD vía router): `plantillas-migracion/`, `procesos-migracion/`, `detalles-error-migracion/`.
