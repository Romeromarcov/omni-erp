/* eslint-disable react-refresh/only-export-components */
import { lazy } from 'react';
import { Route, Navigate } from 'react-router-dom';
import { getSessionUser, getSessionRoles } from '../services/session';

const DashboardUserPage = lazy(() => import('../pages/Core/Login/DashboardUserPage'));
const RoleListPage = lazy(() => import('../pages/Core/Usuarios/RoleListPage'));
const AuditLogListPage = lazy(() => import('../pages/Core/Auditoria'));
const RoleDetailPage = lazy(() => import('../pages/Core/Usuarios/RoleDetailPage'));
const RoleCreatePage = lazy(() => import('../pages/Core/Usuarios/RoleCreatePage'));
const PermissionListPage = lazy(() => import('../pages/Core/Usuarios/PermissionListPage'));
const UserListPage = lazy(() => import('../pages/Core/Usuarios/UserListPage'));
const UserCreatePage = lazy(() => import('../pages/Core/Usuarios/UserCreatePage'));
const UserDetailPage = lazy(() => import('../pages/Core/Usuarios/UserDetailPage'));
const CompanyListPage = lazy(() => import('../pages/Core/Empresas/CompanyListPage'));
const CompanyDetailPage = lazy(() => import('../pages/Core/Empresas/CompanyDetailPage'));
const CompanyCreatePage = lazy(() => import('../pages/Core/Empresas/CompanyCreatePage'));
const BranchListPage = lazy(() => import('../pages/Core/Sucursales/BranchListPage'));
const BranchDetailPage = lazy(() => import('../pages/Core/Sucursales/BranchDetailPage'));
const BranchCreatePage = lazy(() => import('../pages/Core/Sucursales/BranchCreatePage'));
const DepartmentListPage = lazy(() => import('../pages/Core/Departamentos/DepartmentListPage'));
const DepartmentDetailPage = lazy(() => import('../pages/Core/Departamentos/DepartmentDetailPage'));

function DashboardRoute() {
  // FE-HIGH-13: user/empresa/sucursal come from the in-memory session, not
  // localStorage. empresa/sucursal are resolved from the user's lists using the
  // non-PII UI selection ids kept in localStorage.
  const user = getSessionUser();
  const idEmpresaSel = localStorage.getItem('id_empresa');
  const idSucursalSel = localStorage.getItem('id_sucursal');
  const empresa = user?.empresas?.find((e) => String(e.id_empresa) === String(idEmpresaSel))
    ?? user?.empresas?.[0]
    ?? null;
  const sucursal = user?.sucursales?.find((s) => String(s.id_sucursal) === String(idSucursalSel))
    ?? user?.sucursales?.[0]
    ?? null;
  const actividades = [{ id: 1, descripcion: 'Inicio de sesión', fecha: new Date().toISOString().slice(0, 10) }];
  if (user?.id) {
    const dashboardUser = {
      id: Number(user.id),
      first_name: user.first_name,
      last_name: user.last_name,
      roles: getSessionRoles(),
    };
    return <DashboardUserPage user={dashboardUser} empresa={empresa || { nombre: '' }} sucursal={sucursal || { nombre: '' }} actividades={actividades} />;
  }
  return <Navigate to="/login" replace />;
}

function DepartamentosRoute() {
  const empresaId = localStorage.getItem('id_empresa');
  return empresaId
    ? <Navigate to={`/empresas/${empresaId}/departamentos`} replace />
    : <div style={{ textAlign: 'center', marginTop: 64, fontSize: 20 }}>Seleccione una empresa para ver sus departamentos.</div>;
}

export function coreRoutes() {
  return (
    <>
      <Route path="/dashboard" element={<DashboardRoute />} />
      <Route path="/roles" element={<RoleListPage />} />
      <Route path="/roles/new" element={<RoleCreatePage />} />
      <Route path="/roles/:id_rol" element={<RoleDetailPage />} />
      <Route path="/permisos" element={<PermissionListPage />} />
      <Route path="/auditoria" element={<AuditLogListPage />} />

      <Route path="/empresas" element={<CompanyListPage />} />
      <Route path="/empresas/new" element={<CompanyCreatePage />} />
      <Route path="/empresas/:id_empresa" element={<CompanyDetailPage />} />

      <Route path="/empresas/:id_empresa/usuarios" element={<UserListPage />} />
      <Route path="/empresas/:id_empresa/usuarios/new" element={<UserCreatePage />} />
      <Route path="/empresas/:id_empresa/usuarios/:id" element={<UserDetailPage />} />

      <Route path="/empresas/:id_empresa/sucursales" element={<BranchListPage />} />
      <Route path="/empresas/:id_empresa/sucursales/new" element={<BranchCreatePage />} />
      <Route path="/sucursales/:id_sucursal" element={<BranchDetailPage />} />
      <Route path="/sucursales/:id_sucursal/edit" element={<BranchDetailPage />} />

      <Route path="/empresas/:id_empresa/departamentos" element={<DepartmentListPage />} />
      <Route path="/departamentos" element={<DepartamentosRoute />} />
      <Route path="/departamentos/:id_departamento" element={<DepartmentDetailPage />} />
      <Route path="/departamentos/:id_departamento/edit" element={<DepartmentDetailPage />} />
    </>
  );
}
