import { lazy, Suspense } from 'react';
import { Route } from 'react-router-dom';

const ConnectPerfilPage = lazy(() => import('../pages/Connect/ConnectPerfilPage'));

export function connectRoutes() {
  return (
    <Route
      path="/connect/perfil"
      element={
        <Suspense fallback={<div>Cargando…</div>}>
          <ConnectPerfilPage />
        </Suspense>
      }
    />
  );
}
