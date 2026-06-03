import { lazy } from 'react';
import { Route } from 'react-router-dom';

const EscanerPage = lazy(() => import('../pages/Escaner/EscanerPage'));

export function escanerRoutes() {
  return (
    <>
      <Route path="/escaner" element={<EscanerPage />} />
    </>
  );
}
