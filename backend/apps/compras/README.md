# App `compras`

Ciclo de compra completo: desde la requisición y la solicitud de cotización (con ofertas de proveedor) hasta la orden de compra, la recepción de mercancía y la factura de compra.

**Prefijo API:** `/api/compras/`

## Modelos

| Documento | Encabezado | Detalle |
|---|---|---|
| Requisición | `RequisicionCompra` | `DetalleRequisicionCompra` |
| Solicitud de cotización | `SolicitudCotizacion` | `DetalleSolicitudCotizacion` |
| Oferta de proveedor | `OfertaProveedor` | `DetalleOfertaProveedor` |
| Orden de compra | `OrdenCompra` | `DetalleOrdenCompra` |
| Recepción de mercancía | `RecepcionMercancia` | `DetalleRecepcionMercancia` |
| Factura de compra | `FacturaCompra` | `DetalleFacturaCompra` |

## Endpoints

Recursos REST (CRUD vía router): `ordenes-compra/`, `detalles-orden-compra/`, `recepciones-mercancia/`, `detalles-recepcion-mercancia/`, `facturas-compra/`, `detalles-factura-compra/`, `requisiciones-compra/`, `detalles-requisicion-compra/`, `solicitudes-cotizacion/`, `detalles-solicitud-cotizacion/`, `ofertas-proveedor/`, `detalles-oferta-proveedor/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `POST ordenes-compra/{id}/aprobar/` | Aprobar orden de compra. |
| `POST recepciones-mercancia/recepcionar/` | Registrar recepción de mercancía. |
| `POST facturas-compra/facturar/` | Generar factura de compra. |
