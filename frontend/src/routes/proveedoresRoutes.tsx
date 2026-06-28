import { lazy } from 'react';
import { Route } from 'react-router-dom';

const ProveedoresPage = lazy(() => import('../pages/Proveedores/ProveedoresPage'));

export function proveedoresRoutes() {
  return (
    <>
      <Route path="/proveedores/proveedores" element={<ProveedoresPage />} />
    </>
  );
}
