# App `contabilidad`

Contabilidad: plan de cuentas, diarios contables con secuencias atómicas, asientos contables con sus detalles (trazabilidad por tercero `core.Contacto`), contra-asientos de reversión, períodos contables y cierre de ejercicio, y el mapeo contable que genera asientos automáticos a partir de eventos de negocio (ventas, compras, pagos). La contabilidad es opcional por empresa: una bodega informal puede operar sin plan de cuentas ni diarios (ver [ADR-006](../../../docs/decisions/ADR-006-asientos-contables-automaticos.md)).

**Prefijo API:** `/api/contabilidad/`

## Modelos

| Modelo | Descripción |
|---|---|
| `PlanCuentas` | Cuenta del plan contable (jerárquico). |
| `DiarioContable` | Diario contable por empresa (`account.journal`, secuencias opcionales y cuentas por defecto). |
| `AsientoContable` | Asiento contable (encabezado, `id_diario`, `asiento_revertido`, `es_cierre`). |
| `DetalleAsiento` | Línea de asiento (débito/crédito + `id_contacto` opcional). |
| `MapeoContable` | Reglas de mapeo evento de negocio → asiento automático (con `id_diario` opcional). |
| `PeriodoContable` | Período contable mensual (`ABIERTO`/`CERRADO`) y vínculo al cierre anual. |

## Endpoints

Recursos REST (CRUD vía router): `plan-cuentas/`, `diarios/`, `periodos-contables/`, `asientos-contables/`, `detalles-asiento/`, `mapeos-contables/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET plan-cuentas/activos/` · `por_tipo/` | Vistas del plan de cuentas. |
| `POST asientos-contables/{id}/aprobar/` · `anular/` · `revertir/` | Aprobar, anular (borrador) o revertir por contra-asiento (aprobado). |
| `GET asientos-contables/balance_comprobacion/` | Balance de comprobación. |
| `POST periodos-contables/cerrar/` · `{id}/cerrar/` · `{id}/reabrir/` | Cierre y reapertura de períodos contables mensuales. |
| `POST periodos-contables/cerrar-ejercicio/` | Cierre anual de cuentas de resultado a patrimonio y cierre de los 12 períodos. |
| `GET mapeos-contables/tipos-asiento/` | Catálogo de tipos de asiento automático. |
