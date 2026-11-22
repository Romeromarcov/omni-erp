import { lazy, Suspense } from 'react';
import { Route } from 'react-router-dom';

const ConnectPerfilPage = lazy(() => import('../pages/Connect/ConnectPerfilPage'));
const ConnectAnaliticasPage = lazy(() => import('../pages/Connect/ConnectAnaliticasPage'));
const ConnectTarjetasPage = lazy(() => import('../pages/Connect/ConnectTarjetasPage'));

export function connectRoutes() {
  return (
    <>
      <Route
        path="/connect/perfil"
        element={
          <Suspense fallback={<div>Cargando…</div>}>
            <ConnectPerfilPage />
          </Suspense>
        }
      />
      <Route
        path="/connect/analiticas"
        element={
          <Suspense fallback={<div>Cargando…</div>}>
            <ConnectAnaliticasPage />
          </Suspense>
        }
      />
      <Route
        path="/connect/tarjetas"
        element={
          <Suspense fallback={<div>Cargando…</div>}>
            <ConnectTarjetasPage />
          </Suspense>
        }
      />
    </>
  );
}
