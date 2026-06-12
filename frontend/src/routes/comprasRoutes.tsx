import { lazy } from 'react';
import { Route } from 'react-router-dom';

const OrdenesCompraListPage = lazy(() => import('../pages/Compras/OrdenesCompraListPage'));
const OrdenCompraFormPage = lazy(() => import('../pages/Compras/OrdenCompraFormPage'));
const OrdenCompraDetailPage = lazy(() => import('../pages/Compras/OrdenCompraDetailPage'));
const CuentasPorPagarPage = lazy(() => import('../pages/Compras/CuentasPorPagarPage'));

export function comprasRoutes() {
  return (
    <>
      <Route path="/compras/ordenes" element={<OrdenesCompraListPage />} />
      <Route path="/compras/ordenes/nueva" element={<OrdenCompraFormPage />} />
      <Route path="/compras/ordenes/:id" element={<OrdenCompraDetailPage />} />
      <Route path="/compras/cuentas-por-pagar" element={<CuentasPorPagarPage />} />
    </>
  );
}
