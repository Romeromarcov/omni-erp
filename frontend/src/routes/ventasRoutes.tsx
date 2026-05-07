import { Route } from 'react-router-dom';
import PedidosListPage from '../pages/Ventas/Pedidos/PedidosListPage';
import PedidoDetailPage from '../pages/Ventas/Pedidos/PedidoDetailPage';
import PedidoFormPage from '../pages/Ventas/Pedidos/PedidoFormPage';
import CotizacionesListPage from '../pages/Ventas/Cotizaciones/CotizacionesListPage';
import CotizacionDetailPage from '../pages/Ventas/Cotizaciones/CotizacionDetailPage';
import CotizacionFormPage from '../pages/Ventas/Cotizaciones/CotizacionFormPage';
import NotasVentaListPage from '../pages/Ventas/NotasVenta/NotasVentaListPage';
import NotaVentaDetailPage from '../pages/Ventas/NotasVenta/NotaVentaDetailPage';
import NotaVentaFormPage from '../pages/Ventas/NotasVenta/NotaVentaFormPage';
import NotasCreditoVentaListPage from '../pages/Ventas/NotasCreditoVenta/NotasCreditoVentaListPage';
import NotaCreditoVentaDetailPage from '../pages/Ventas/NotasCreditoVenta/NotaCreditoVentaDetailPage';
import NotaCreditoVentaFormPage from '../pages/Ventas/NotasCreditoVenta/NotaCreditoVentaFormPage';
import NotasCreditoFiscalListPage from '../pages/Ventas/NotasCreditoFiscal/NotasCreditoFiscalListPage';
import NotaCreditoFiscalDetailPage from '../pages/Ventas/NotasCreditoFiscal/NotaCreditoFiscalDetailPage';
import NotaCreditoFiscalFormPage from '../pages/Ventas/NotasCreditoFiscal/NotaCreditoFiscalFormPage';
import DevolucionesVentaListPage from '../pages/Ventas/DevolucionesVenta/DevolucionesVentaListPage';
import DevolucionVentaDetailPage from '../pages/Ventas/DevolucionesVenta/DevolucionVentaDetailPage';
import DevolucionVentaFormPage from '../pages/Ventas/DevolucionesVenta/DevolucionVentaFormPage';
import FacturasFiscalesListPage from '../pages/Ventas/FacturasFiscales/FacturasFiscalesListPage';
import FacturaFiscalDetailPage from '../pages/Ventas/FacturasFiscales/FacturaFiscalDetailPage';
import FacturaFiscalFormPage from '../pages/Ventas/FacturasFiscales/FacturaFiscalFormPage';

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
    </>
  );
}
