import { lazy } from 'react';
import { Route } from 'react-router-dom';

const ClientesPage = lazy(() => import('../pages/CRM/ClientesPage'));
const CrmPipelineKanbanPage = lazy(() => import('../pages/CRM/CrmPipelineKanbanPage'));

export function crmRoutes() {
  return (
    <>
      <Route path="/crm/clientes" element={<ClientesPage />} />
      <Route path="/crm/pipeline" element={<CrmPipelineKanbanPage />} />
    </>
  );
}
