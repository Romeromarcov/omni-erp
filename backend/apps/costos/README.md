# App `costos`

Costeo de producción: costos reales de producción, costo estándar por producto y análisis de variación (real vs. estándar). Complementa a `manufactura`.

**Prefijo API:** `/api/costos/`

## Modelos

| Modelo | Descripción |
|---|---|
| `CostoProduccion` | Costo real de una producción. |
| `CostoEstandarProducto` | Costo estándar definido por producto. |
| `AnalisisVariacionCosto` | Análisis de variación entre costo real y estándar. |

## Endpoints

Recursos REST (CRUD vía router): `costos-produccion/`, `costos-estandar-producto/`, `analisis-variacion-costo/`.
