/* eslint-disable react-refresh/only-export-components */
import { lazy } from 'react';
import { Route, Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const AdminSaasDashboardPage = lazy(() => import('../pages/SaaS/AdminSaasDashboardPage'));
const PlanListPage = lazy(() => import('../pages/SaaS/PlanListPage'));
const PlanFormPage = lazy(() => import('../pages/SaaS/PlanFormPage'));
const SuscripcionListPage = lazy(() => import('../pages/SaaS/SuscripcionListPage'));
const SuscripcionCreatePage = lazy(() => import('../pages/SaaS/SuscripcionCreatePage'));
const TenantListPage = lazy(() => import('../pages/SaaS/TenantListPage'));

/**
 * Guard del Panel SaaS: solo el dueño del software (es_superusuario_omni) puede
 * entrar. Esto es defensa en profundidad de UI — el backend ya restringe la
 * escritura de planes a superusuarios; aquí evitamos exponer la consola del
 * proveedor a tenants. Un usuario sin el rol es redirigido a su dashboard.
 */
function RequireSuperuserOmni() {
  const { user } = useAuth();
  if (!user?.es_superusuario_omni) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}

export function saasRoutes() {
  return (
    <Route element={<RequireSuperuserOmni />}>
      <Route path="/admin-saas" element={<AdminSaasDashboardPage />} />
      <Route path="/admin-saas/tenants" element={<TenantListPage />} />
      <Route path="/admin-saas/planes" element={<PlanListPage />} />
      <Route path="/admin-saas/planes/new" element={<PlanFormPage />} />
      <Route path="/admin-saas/planes/:id_plan" element={<PlanFormPage />} />
      <Route path="/admin-saas/suscripciones" element={<SuscripcionListPage />} />
      <Route path="/admin-saas/suscripciones/new" element={<SuscripcionCreatePage />} />
    </Route>
  );
}
