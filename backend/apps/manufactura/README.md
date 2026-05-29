# App `manufactura`

Manufactura discreta: listas de materiales (BOM), rutas de producción con centros de trabajo y operaciones, órdenes de producción, consumo de materiales y registro de producción terminada. Cubre el negocio piloto de fábrica de muebles.

**Prefijo API:** `/api/manufactura/`

## Modelos

| Modelo | Descripción |
|---|---|
| `ListaMateriales` / `ListaMaterialesDetalle` | BOM y sus componentes. |
| `RutaProduccion` / `RutaProduccionDetalle` | Ruta de producción y sus pasos. |
| `CentroTrabajo` | Centro de trabajo. |
| `OperacionProduccion` | Operación productiva. |
| `OrdenProduccion` | Orden de producción. |
| `ConsumoMaterial` | Consumo de materiales en una orden. |
| `ProduccionTerminada` | Registro de producto terminado. |
| `RegistroOperacion` | Registro de ejecución de operaciones. |

## Endpoints

Recursos REST (CRUD vía router): `listas-materiales/`, `listas-materiales-detalle/`, `rutas-produccion/`, `rutas-produccion-detalle/`, `centros-trabajo/`, `operaciones-produccion/`, `ordenes-produccion/`, `consumos-material/`, `produccion-terminada/`, `registros-operacion/`.
