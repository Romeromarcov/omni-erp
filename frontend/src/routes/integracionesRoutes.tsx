 
import { lazy } from 'react';
import { Route } from 'react-router-dom';

const IntegrationHubPage = lazy(() => import('../pages/Integraciones/IntegrationHubPage'));
const ConectorDetallePage = lazy(() => import('../pages/Integraciones/ConectorDetallePage'));

export function integracionesRoutes() {
  return (
    <>
      <Route path="/integraciones" element={<IntegrationHubPage />} />
      <Route path="/integraciones/conectores/:id" element={<ConectorDetallePage />} />
    </>
  );
}
