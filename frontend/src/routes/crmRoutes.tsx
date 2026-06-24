import { lazy } from 'react';
import { Route } from 'react-router-dom';

const ClientesPage = lazy(() => import('../pages/CRM/ClientesPage'));

export function crmRoutes() {
  return (
    <>
      <Route path="/crm/clientes" element={<ClientesPage />} />
    </>
  );
}
