import { lazy } from 'react';
import { Route } from 'react-router-dom';

const CostosPage = lazy(() => import('../pages/Costos/CostosPage'));

export function costosRoutes() {
  return (
    <>
      <Route path="/costos" element={<CostosPage />} />
    </>
  );
}
