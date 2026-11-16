import { lazy } from 'react';
import { Route } from 'react-router-dom';

const ActivacionesPage = lazy(() => import('../pages/Activaciones/ActivacionesPage'));
const IngestasBotsPage = lazy(() => import('../pages/Bots/IngestasBotsPage'));

export function activacionesRoutes() {
  return (
    <>
      <Route path="/activaciones" element={<ActivacionesPage />} />
      <Route path="/bots" element={<IngestasBotsPage />} />
    </>
  );
}
