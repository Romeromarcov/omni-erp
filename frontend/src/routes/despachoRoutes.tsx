import { lazy } from 'react';
import { Route } from 'react-router-dom';

const DespachosPage = lazy(() => import('../pages/Despacho/DespachosPage'));
const PortalConductorPage = lazy(() => import('../pages/Despacho/PortalConductorPage'));

export function despachoRoutes() {
  return (
    <>
      <Route path="/despacho" element={<DespachosPage />} />
      <Route path="/despacho/portal-conductor" element={<PortalConductorPage />} />
    </>
  );
}
