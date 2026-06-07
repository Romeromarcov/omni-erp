import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { shouldUseHashRouter } from './platform';
import LoginPage from './pages/Core/Login/LoginPage';
import SignupPage from './pages/Core/Signup/SignupPage';
import AppLayout from './components/layout/AppLayout';
import { useAuth } from './contexts/AuthContext';
import { ventasRoutes } from './routes/ventasRoutes';
import { finanzasRoutes } from './routes/finanzasRoutes';
import { coreRoutes } from './routes/coreRoutes';
import { configuracionRoutes } from './routes/configuracionRoutes';
import { integracionesRoutes } from './routes/integracionesRoutes';
import { inventarioRoutes } from './routes/inventarioRoutes';
import { fiscalRoutes } from './routes/fiscalRoutes';
import { cxcRoutes } from './routes/cxcRoutes';
import { escanerRoutes } from './routes/escanerRoutes';
import { saasRoutes } from './routes/saasRoutes';

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

        {token && (
          <Route element={<AppLayout />}>
            {coreRoutes()}
            {ventasRoutes()}
            {finanzasRoutes()}
            {configuracionRoutes()}
            {integracionesRoutes()}
            {inventarioRoutes()}
            {fiscalRoutes()}
            {cxcRoutes()}
            {escanerRoutes()}
            {saasRoutes()}
          </Route>
        )}

        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </Router>
  );
}
