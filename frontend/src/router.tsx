import { lazy, Suspense } from 'react';
import { BrowserRouter, HashRouter, Routes, Route } from 'react-router-dom';
import { shouldUseHashRouter } from './platform';

const PublicConnectCardPage = lazy(() => import('./pages/Connect/PublicConnectCardPage'));
const PortalClientePage = lazy(() => import('./pages/Ventas/PortalClientePage'));
const AuthenticatedApp = lazy(() => import('./AuthenticatedApp'));

export default function AppRouter() {
  // Router adaptativo: rutas limpias en web, hash routing en shells nativos
  // (Electron file:// / Capacitor) donde la recarga por ruta no resuelve.
  const Router = shouldUseHashRouter() ? HashRouter : BrowserRouter;

  return (
    <Router>
      <Suspense fallback={<div>Cargando…</div>}>
        <Routes>
          <Route path="/c/:slug" element={<PublicConnectCardPage />} />
          <Route path="/portal/cliente" element={<PortalClientePage />} />
          <Route path="*" element={<AuthenticatedApp />} />
        </Routes>
      </Suspense>
    </Router>
  );
}
