# App `tesoreria`

Tesorería: movimientos internos de fondos, operaciones de cambio de divisa, movimientos bancarios y conciliación bancaria (incl. importación de extractos y conciliación automática).

**Prefijo API:** `/api/tesoreria/`

## Modelos

| Modelo | Descripción |
|---|---|
| `MovimientoInternoFondo` | Movimiento interno entre fondos/cajas. |
| `OperacionCambioDivisa` | Operación de cambio de divisa. |
| `MovimientoBancario` | Movimiento en cuenta bancaria. |
| `ConciliacionBancaria` | Proceso de conciliación bancaria. |

## Endpoints

Recursos REST (CRUD vía router): `cajas/`, `movimientos-internos-fondo/`, `operaciones-cambio-divisa/`, `movimientos-bancarios/`, `conciliaciones-bancarias/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `POST movimientos-bancarios/importar-csv/` | Importar movimientos desde CSV. |
| `POST conciliaciones-bancarias/conciliar-auto/` | Conciliación automática. |
| `POST conciliaciones-bancarias/{id}/cerrar/` | Cerrar conciliación. |
