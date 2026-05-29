# App `integracion_b2b`

Integración B2B: configuración de integraciones entre empresas/sistemas, mapeo de campos entre esquemas y log de las integraciones ejecutadas.

**Prefijo API:** `/api/integracion-b2b/`

## Modelos

| Modelo | Descripción |
|---|---|
| `ConfiguracionIntegracion` | Configuración de una integración B2B. |
| `MapeoCampo` | Mapeo de campos entre esquemas. |
| `LogIntegracion` | Registro de integraciones ejecutadas. |

## Endpoints

Recursos REST (CRUD vía router): `configuracion-integracion/`, `logs-integracion/`, `mapeo-campos/`.
