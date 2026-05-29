# App `inventario`

Gestión de inventario: maestro de productos (con variantes, categorías y unidades de medida), stock actual, movimientos (kardex) y stock en consignación (cliente y proveedor). Soporta conversión entre unidades de medida y requisiciones internas.

**Prefijo API:** `/api/inventario/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Producto` | Maestro de producto. |
| `VarianteProducto` | Variante de un producto (talla, color, etc.). |
| `CategoriaProducto` | Categoría de productos. |
| `UnidadMedida` | Unidad de medida. |
| `ConversionUnidadMedida` | Factor de conversión entre unidades. |
| `StockActual` | Existencia actual por producto/almacén. |
| `MovimientoInventario` | Movimiento de stock (entrada/salida) — base del kardex. |
| `StockConsignacionCliente` | Stock en consignación en poder de clientes. |
| `StockConsignacionProveedor` | Stock en consignación recibido de proveedores. |
| `RequisicionInterna` / `DetalleRequisicion` | Requisiciones internas de material. |

## Endpoints

Recursos REST (CRUD vía router): `unidades-medida/`, `categorias-producto/`, `productos/`, `variantes-producto/`, `stock-actual/`, `movimientos-inventario/`, `conversiones-unidad-medida/`, `stock-consignacion-cliente/`, `stock-consignacion-proveedor/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET productos/{id}/kardex/` | Kardex (historial de movimientos) del producto. |
