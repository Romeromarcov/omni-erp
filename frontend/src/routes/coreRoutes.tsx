/* eslint-disable react-refresh/only-export-components */
import { lazy } from 'react';
import { Route, Navigate } from 'react-router-dom';

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
  const userStr = localStorage.getItem('usuario');
  const empresaStr = localStorage.getItem('empresa');
  const sucursalStr = localStorage.getItem('sucursal');
  let user = null, empresa = null, sucursal = null;
  try { user = userStr ? JSON.parse(userStr) : null; } catch { /* ignore */ }
  try { empresa = empresaStr ? JSON.parse(empresaStr) : null; } catch { /* ignore */ }
  try { sucursal = sucursalStr ? JSON.parse(sucursalStr) : null; } catch { /* ignore */ }
  const actividades = [{ id: 1, descripcion: 'Inicio de sesión', fecha: new Date().toISOString().slice(0, 10) }];
  if (user?.id) {
    return <DashboardUserPage user={user} empresa={empresa || { nombre: '' }} sucursal={sucursal || { nombre: '' }} actividades={actividades} />;
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
