import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/Core/Login/LoginPage';
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

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
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
          </Route>
        )}

        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  );
}
