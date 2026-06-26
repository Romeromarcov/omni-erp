import { lazy } from 'react';
import { Route } from 'react-router-dom';

const IntegracionB2bPage = lazy(() => import('../pages/IntegracionB2b/IntegracionB2bPage'));

export function integracionB2bRoutes() {
  return (
    <>
      <Route path="/integracion-b2b" element={<IntegracionB2bPage />} />
    </>
  );
}
