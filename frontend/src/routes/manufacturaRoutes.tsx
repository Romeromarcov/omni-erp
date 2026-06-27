import { lazy } from 'react';
import { Route } from 'react-router-dom';

const OrdenesProduccionListPage = lazy(() => import('../pages/Manufactura/OrdenesProduccionListPage'));
const OrdenProduccionFormPage = lazy(() => import('../pages/Manufactura/OrdenProduccionFormPage'));
const OrdenProduccionDetailPage = lazy(() => import('../pages/Manufactura/OrdenProduccionDetailPage'));
const CosteoOrdenPage = lazy(() => import('../pages/Manufactura/CosteoOrdenPage'));
const MrpOrdenPage = lazy(() => import('../pages/Manufactura/MrpOrdenPage'));
const DatosMaestrosPage = lazy(() => import('../pages/Manufactura/DatosMaestrosPage'));

export function manufacturaRoutes() {
  return (
    <>
      <Route path="/manufactura/maestros" element={<DatosMaestrosPage />} />
      <Route path="/manufactura/listas-materiales" element={<DatosMaestrosPage />} />
      <Route path="/manufactura/rutas" element={<DatosMaestrosPage />} />
      <Route path="/manufactura/centros-trabajo" element={<DatosMaestrosPage />} />
      <Route path="/manufactura/ordenes" element={<OrdenesProduccionListPage />} />
      <Route path="/manufactura/ordenes/nueva" element={<OrdenProduccionFormPage />} />
      <Route path="/manufactura/ordenes/:id" element={<OrdenProduccionDetailPage />} />
      <Route path="/manufactura/ordenes/:id/costeo" element={<CosteoOrdenPage />} />
      <Route path="/manufactura/ordenes/:id/mrp" element={<MrpOrdenPage />} />
    </>
  );
}
