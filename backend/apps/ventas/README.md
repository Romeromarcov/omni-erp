# App `ventas`

Ciclo de venta completo: desde la cotización y el pedido hasta la nota de venta, la factura fiscal y las notas de crédito / devoluciones. Gestiona también las listas de precio. Genera PDFs de cotización (`pdf_cotizacion.py`) y emite eventos de dominio.

**Prefijo API:** `/api/ventas/`

## Modelos

| Documento | Encabezado | Detalle |
|---|---|---|
| Cotización | `Cotizacion` | `DetalleCotizacion` |
| Pedido | `Pedido` | `DetallePedido` |
| Nota de venta | `NotaVenta` | `DetalleNotaVenta` |
| Factura fiscal | `FacturaFiscal` | `DetalleFacturaFiscal` |
| Nota de crédito (venta) | `NotaCreditoVenta` | `DetalleNotaCreditoVenta` |
| Nota de crédito fiscal | `NotaCreditoFiscal` | `DetalleNotaCreditoFiscal` |
| Devolución | `DevolucionVenta` | `DetalleDevolucionVenta` |
| Listas de precio | `ListaPrecio` | `DetallePrecio` |

## Endpoints

Recursos REST (CRUD vía router): `pedidos/`, `detalles-pedido/`, `notas-venta/`, `detalles-nota-venta/`, `facturas-fiscales/`, `detalles-factura-fiscal/`, `cotizaciones/`, `detalles-cotizacion/`, `notas-credito-venta/`, `detalles-nota-credito-venta/`, `notas-credito-fiscal/`, `detalles-nota-credito-fiscal/`, `devoluciones-venta/`, `detalles-devolucion-venta/`, `listas-precio/`, `detalles-precio/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `POST pedidos/{id}/confirmar/` | Confirmar un pedido. |
| `GET .../{id}/pdf/` | Generar PDF (cotización / documento). |
| `POST .../{id}/importar-masivo/` | Importación masiva de líneas. |
