import { lazy } from 'react';
import { Route } from 'react-router-dom';

const PedidosListPage = lazy(() => import('../pages/Ventas/Pedidos/PedidosListPage'));
const PedidoDetailPage = lazy(() => import('../pages/Ventas/Pedidos/PedidoDetailPage'));
const PedidoFormPage = lazy(() => import('../pages/Ventas/Pedidos/PedidoFormPage'));
const CotizacionesListPage = lazy(() => import('../pages/Ventas/Cotizaciones/CotizacionesListPage'));
const CotizacionDetailPage = lazy(() => import('../pages/Ventas/Cotizaciones/CotizacionDetailPage'));
const CotizacionFormPage = lazy(() => import('../pages/Ventas/Cotizaciones/CotizacionFormPage'));
const NotasVentaListPage = lazy(() => import('../pages/Ventas/NotasVenta/NotasVentaListPage'));
const NotaVentaDetailPage = lazy(() => import('../pages/Ventas/NotasVenta/NotaVentaDetailPage'));
const NotaVentaFormPage = lazy(() => import('../pages/Ventas/NotasVenta/NotaVentaFormPage'));
const NotasCreditoVentaListPage = lazy(() => import('../pages/Ventas/NotasCreditoVenta/NotasCreditoVentaListPage'));
const NotaCreditoVentaDetailPage = lazy(() => import('../pages/Ventas/NotasCreditoVenta/NotaCreditoVentaDetailPage'));
const NotaCreditoVentaFormPage = lazy(() => import('../pages/Ventas/NotasCreditoVenta/NotaCreditoVentaFormPage'));
const NotasCreditoFiscalListPage = lazy(() => import('../pages/Ventas/NotasCreditoFiscal/NotasCreditoFiscalListPage'));
const NotaCreditoFiscalDetailPage = lazy(() => import('../pages/Ventas/NotasCreditoFiscal/NotaCreditoFiscalDetailPage'));
const NotaCreditoFiscalFormPage = lazy(() => import('../pages/Ventas/NotasCreditoFiscal/NotaCreditoFiscalFormPage'));
const DevolucionesVentaListPage = lazy(() => import('../pages/Ventas/DevolucionesVenta/DevolucionesVentaListPage'));
const DevolucionVentaDetailPage = lazy(() => import('../pages/Ventas/DevolucionesVenta/DevolucionVentaDetailPage'));
const DevolucionVentaFormPage = lazy(() => import('../pages/Ventas/DevolucionesVenta/DevolucionVentaFormPage'));
const FacturasFiscalesListPage = lazy(() => import('../pages/Ventas/FacturasFiscales/FacturasFiscalesListPage'));
const FacturaFiscalDetailPage = lazy(() => import('../pages/Ventas/FacturasFiscales/FacturaFiscalDetailPage'));
const FacturaFiscalFormPage = lazy(() => import('../pages/Ventas/FacturasFiscales/FacturaFiscalFormPage'));
const ListasPrecioPage = lazy(() => import('../pages/Ventas/ListasPrecioPage'));
const ComisionesPage = lazy(() => import('../pages/Ventas/ComisionesPage'));

export function ventasRoutes() {
  return (
    <>
      <Route path="/ventas/pedidos" element={<PedidosListPage />} />
      <Route path="/ventas/pedidos/new" element={<PedidoFormPage />} />
      <Route path="/ventas/pedidos/:id_pedido" element={<PedidoDetailPage />} />
      <Route path="/ventas/pedidos/:id_pedido/edit" element={<PedidoFormPage />} />

      <Route path="/ventas/cotizaciones" element={<CotizacionesListPage />} />
      <Route path="/ventas/cotizaciones/new" element={<CotizacionFormPage />} />
      <Route path="/ventas/cotizaciones/:id_cotizacion" element={<CotizacionDetailPage />} />
      <Route path="/ventas/cotizaciones/:id_cotizacion/edit" element={<CotizacionFormPage />} />

      <Route path="/ventas/notas-venta" element={<NotasVentaListPage />} />
      <Route path="/ventas/notas-venta/new" element={<NotaVentaFormPage />} />
      <Route path="/ventas/notas-venta/:id_nota_venta" element={<NotaVentaDetailPage />} />
      <Route path="/ventas/notas-venta/:id_nota_venta/edit" element={<NotaVentaFormPage />} />

      <Route path="/ventas/notas-credito-venta" element={<NotasCreditoVentaListPage />} />
      <Route path="/ventas/notas-credito-venta/new" element={<NotaCreditoVentaFormPage />} />
      <Route path="/ventas/notas-credito-venta/:id" element={<NotaCreditoVentaDetailPage />} />
      <Route path="/ventas/notas-credito-venta/:id/edit" element={<NotaCreditoVentaFormPage />} />

      <Route path="/ventas/notas-credito-fiscal" element={<NotasCreditoFiscalListPage />} />
      <Route path="/ventas/notas-credito-fiscal/new" element={<NotaCreditoFiscalFormPage />} />
      <Route path="/ventas/notas-credito-fiscal/:id" element={<NotaCreditoFiscalDetailPage />} />
      <Route path="/ventas/notas-credito-fiscal/:id/edit" element={<NotaCreditoFiscalFormPage />} />

      <Route path="/ventas/devoluciones-venta" element={<DevolucionesVentaListPage />} />
      <Route path="/ventas/devoluciones-venta/new" element={<DevolucionVentaFormPage />} />
      <Route path="/ventas/devoluciones-venta/:id" element={<DevolucionVentaDetailPage />} />
      <Route path="/ventas/devoluciones-venta/:id/edit" element={<DevolucionVentaFormPage />} />

      <Route path="/ventas/facturas-fiscales" element={<FacturasFiscalesListPage />} />
      <Route path="/ventas/facturas-fiscales/new" element={<FacturaFiscalFormPage />} />
      <Route path="/ventas/facturas-fiscales/:id_factura" element={<FacturaFiscalDetailPage />} />
      <Route path="/ventas/facturas-fiscales/:id_factura/edit" element={<FacturaFiscalFormPage />} />

      <Route path="/ventas/listas-precio" element={<ListasPrecioPage />} />
      <Route path="/ventas/comisiones" element={<ComisionesPage />} />
    </>
  );
}
