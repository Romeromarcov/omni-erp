import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { shouldUseHashRouter } from './platform';
import LoginPage from './pages/Core/Login/LoginPage';
import SignupPage from './pages/Core/Signup/SignupPage';
import AppLayout from './components/layout/AppLayout';
import { useAuth } from './contexts/AuthContext';
import { lazy, Suspense } from 'react';
import { ventasRoutes } from './routes/ventasRoutes';
import { finanzasRoutes } from './routes/finanzasRoutes';
import { coreRoutes } from './routes/coreRoutes';
import { configuracionRoutes } from './routes/configuracionRoutes';
import { integracionesRoutes } from './routes/integracionesRoutes';
import { inventarioRoutes } from './routes/inventarioRoutes';
import { fiscalRoutes } from './routes/fiscalRoutes';
import { cxcRoutes } from './routes/cxcRoutes';
import { crmRoutes } from './routes/crmRoutes';
import { proveedoresRoutes } from './routes/proveedoresRoutes';
import { gastosRoutes } from './routes/gastosRoutes';
import { despachoRoutes } from './routes/despachoRoutes';
import { manufacturaRoutes } from './routes/manufacturaRoutes';
import { costosRoutes } from './routes/costosRoutes';
import { comprasRoutes } from './routes/comprasRoutes';
import { rrhhRoutes } from './routes/rrhhRoutes';
import { controlAsistenciaRoutes } from './routes/controlAsistenciaRoutes';
import { contabilidadRoutes } from './routes/contabilidadRoutes';
import { tesoreriaRoutes } from './routes/tesoreriaRoutes';
import { escanerRoutes } from './routes/escanerRoutes';
import { saasRoutes } from './routes/saasRoutes';
import { isModuleEnabled } from './config/appProfile';

const PosPage = lazy(() => import('./pages/Ventas/POS/PosPage'));

export default function AppRouter() {
  const { token, isLoading } = useAuth();

  // While rehydrating the session from the refresh cookie, avoid flashing the
  // login page (which would otherwise win the route race for a logged-in user).
  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        Cargando…
      </div>
    );
  }

  // Router adaptativo: rutas limpias en web, hash routing en shells nativos
  // (Electron file:// / Capacitor) donde la recarga por ruta no resuelve.
  const Router = shouldUseHashRouter() ? HashRouter : BrowserRouter;

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/" element={<LoginPage />} />

        {/* POS de mostrador (sub-fase 1.G): pantalla completa, sin AppLayout. */}
        {token && isModuleEnabled('ventas') && (
          <Route
            path="/pos"
            element={
              <Suspense fallback={<div>Cargando…</div>}>
                <PosPage />
              </Suspense>
            }
          />
        )}

        {token && (
          <Route element={<AppLayout />}>
            {coreRoutes()}
            {isModuleEnabled('ventas') ? ventasRoutes() : null}
            {finanzasRoutes()}
            {configuracionRoutes()}
            {integracionesRoutes()}
            {isModuleEnabled('inventario') ? inventarioRoutes() : null}
            {isModuleEnabled('fiscal') ? fiscalRoutes() : null}
            {cxcRoutes()}
            {crmRoutes()}
            {proveedoresRoutes()}
            {gastosRoutes()}
            {despachoRoutes()}
            {isModuleEnabled('manufactura') ? manufacturaRoutes() : null}
            {costosRoutes()}
            {isModuleEnabled('compras') ? comprasRoutes() : null}
            {isModuleEnabled('rrhh') ? rrhhRoutes() : null}
            {controlAsistenciaRoutes()}
            {isModuleEnabled('contabilidad') ? contabilidadRoutes() : null}
            {isModuleEnabled('tesoreria') ? tesoreriaRoutes() : null}
            {isModuleEnabled('escaner') ? escanerRoutes() : null}
            {saasRoutes()}
          </Route>
        )}

        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </Router>
  );
}
