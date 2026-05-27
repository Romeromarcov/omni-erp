import { Route } from 'react-router-dom';
import IntegrationHubPage from '../pages/Integraciones/IntegrationHubPage';
import ConectorDetallePage from '../pages/Integraciones/ConectorDetallePage';

export function integracionesRoutes() {
  return (
    <>
      <Route path="/integraciones" element={<IntegrationHubPage />} />
      <Route path="/integraciones/conectores/:id" element={<ConectorDetallePage />} />
    </>
  );
}
