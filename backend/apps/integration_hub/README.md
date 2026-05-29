# App `integration_hub`

Hub de integraciones con sistemas externos. Define proveedores de conector, instancias configuradas por empresa, jobs de sincronización y logs detallados. Permite probar conexiones, disparar sincronizaciones y previsualizar datos antes de importarlos (ver [ADR-003](../../../docs/decisions/ADR-003-integration-hub-mcp.md)).

**Prefijo API:** `/api/integration-hub/`

## Modelos

| Modelo | Descripción |
|---|---|
| `ConectorProveedor` | Tipo de conector disponible (catálogo). |
| `ConectorInstancia` | Instancia de conector configurada por empresa. |
| `EntidadSincronizada` | Entidad externa sincronizada. |
| `JobSincronizacion` | Job de sincronización. |
| `LogDetalleSincronizacion` | Detalle/log de la sincronización. |

## Endpoints

Recursos REST (CRUD vía router): `proveedores/`, `instancias/`, `jobs/`.

Rutas y acciones adicionales:

| Ruta | Descripción |
|---|---|
| `GET status/` | Estado general del hub. |
| `POST instancias/{id}/test/` | Probar conexión. |
| `POST instancias/{id}/sync/` | Disparar sincronización. |
| `GET instancias/{id}/jobs/` · `logs/` | Jobs y logs de la instancia. |
| `GET instancias/{id}/entidades/{tipo}/` · `preview/{tipo}/` | Listar/previsualizar entidades. |
| `POST jobs/{id}/cancelar/` | Cancelar un job. |
