import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import LoginPage from './pages/Core/Login/LoginPage';
import SidebarMenu from './components/SidebarMenu';
import { SidebarProvider, useSidebar } from './components/SidebarContext';
import { useAuth } from './contexts/AuthContext';
import { ventasRoutes } from './routes/ventasRoutes';
import { finanzasRoutes } from './routes/finanzasRoutes';
import { coreRoutes } from './routes/coreRoutes';
import { configuracionRoutes } from './routes/configuracionRoutes';

function ProtectedLayout() {
  const { isCollapsed, isMobile } = useSidebar();
  const marginLeft = isMobile ? 0 : (isCollapsed ? 60 : 200);
  return (
    <div style={{ display: 'flex' }}>
      <SidebarMenu />
      <div style={{ marginLeft, width: '100%', transition: 'margin-left 0.3s ease' }}>
        <Outlet />
      </div>
    </div>
  );
}

export default function AppRouter() {
  const { token } = useAuth();
  return (
    <BrowserRouter>
      <SidebarProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<LoginPage />} />

          {token && (
            <Route element={<ProtectedLayout />}>
              {coreRoutes()}
              {ventasRoutes()}
              {finanzasRoutes()}
              {configuracionRoutes()}
            </Route>
          )}

          <Route path="*" element={<Navigate to="/login" />} />
        </Routes>
      </SidebarProvider>
    </BrowserRouter>
  );
}
