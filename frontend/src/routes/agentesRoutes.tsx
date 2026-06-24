import { lazy } from 'react';
import { Route } from 'react-router-dom';

const AgentesPage = lazy(() => import('../pages/Agentes/AgentesPage'));

export function agentesRoutes() {
  return (
    <>
      <Route path="/agentes" element={<AgentesPage />} />
    </>
  );
}
