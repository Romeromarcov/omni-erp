# App `contabilidad`

Contabilidad: plan de cuentas, asientos contables con sus detalles y el mapeo contable que genera asientos automáticos a partir de eventos de negocio (ventas, compras, pagos). La contabilidad es opcional por empresa: una bodega informal puede operar sin plan de cuentas (ver [ADR-006](../../../docs/decisions/ADR-006-asientos-contables-automaticos.md)).

**Prefijo API:** `/api/contabilidad/`

## Modelos

| Modelo | Descripción |
|---|---|
| `PlanCuentas` | Cuenta del plan contable (jerárquico). |
| `AsientoContable` | Asiento contable (encabezado). |
| `DetalleAsiento` | Línea de asiento (débito/crédito). |
| `MapeoContable` | Reglas de mapeo evento de negocio → asiento automático. |

## Endpoints

Recursos REST (CRUD vía router): `plan-cuentas/`, `asientos-contables/`, `detalles-asiento/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET plan-cuentas/activos/` · `por-tipo/` | Vistas del plan de cuentas. |
| `POST asientos-contables/{id}/aprobar/` · `anular/` | Aprobar / anular asiento. |
| `GET asientos-contables/balance_comprobacion/` | Balance de comprobación. |
