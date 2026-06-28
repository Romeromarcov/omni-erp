import { lazy } from 'react';
import { Route } from 'react-router-dom';

const DespachosPage = lazy(() => import('../pages/Despacho/DespachosPage'));

export function despachoRoutes() {
  return (
    <>
      <Route path="/despacho" element={<DespachosPage />} />
    </>
  );
}
