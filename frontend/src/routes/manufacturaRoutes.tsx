import { lazy } from 'react';
import { Route } from 'react-router-dom';

const OrdenesProduccionListPage = lazy(() => import('../pages/Manufactura/OrdenesProduccionListPage'));
const OrdenProduccionFormPage = lazy(() => import('../pages/Manufactura/OrdenProduccionFormPage'));
const OrdenProduccionDetailPage = lazy(() => import('../pages/Manufactura/OrdenProduccionDetailPage'));
const CosteoOrdenPage = lazy(() => import('../pages/Manufactura/CosteoOrdenPage'));
const MrpOrdenPage = lazy(() => import('../pages/Manufactura/MrpOrdenPage'));

export function manufacturaRoutes() {
  return (
    <>
      <Route path="/manufactura/ordenes" element={<OrdenesProduccionListPage />} />
      <Route path="/manufactura/ordenes/nueva" element={<OrdenProduccionFormPage />} />
      <Route path="/manufactura/ordenes/:id" element={<OrdenProduccionDetailPage />} />
      <Route path="/manufactura/ordenes/:id/costeo" element={<CosteoOrdenPage />} />
      <Route path="/manufactura/ordenes/:id/mrp" element={<MrpOrdenPage />} />
    </>
  );
}
