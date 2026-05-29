# App `gastos`

Gestión de gastos: categorías, registro de gastos con flujo de aprobación y pago, y reembolsos. Integra con el clasificador de gastos por IA (ver app `agentes`).

**Prefijo API:** `/api/gastos/`

## Modelos

| Modelo | Descripción |
|---|---|
| `CategoriaGasto` | Categoría de gasto. |
| `Gasto` | Gasto registrado (con estado de aprobación/pago). |
| `ReembolsoGasto` | Reembolso de gasto a empleado. |

## Endpoints

Recursos REST (CRUD vía router): `categorias-gasto/`, `gastos/`, `reembolsos-gasto/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET categorias-gasto/activas/` | Categorías activas. |
| `POST gastos/{id}/aprobar/` · `rechazar/` | Aprobar / rechazar gasto. |
| `GET gastos/pendientes_aprobacion/` · `resumen_por_categoria/` | Bandeja y resumen de gastos. |
| `POST reembolsos-gasto/{id}/procesar_pago/` · `anular/` | Procesar / anular reembolso. |
| `GET reembolsos-gasto/pendientes_pago/` | Reembolsos pendientes de pago. |
