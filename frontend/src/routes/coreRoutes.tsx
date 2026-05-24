// Route config files export a factory function (non-component) alongside inline components.
// react-refresh/only-export-components is a dev-HMR concern; does not affect production.
/* eslint-disable react-refresh/only-export-components */
import { Route, Navigate } from 'react-router-dom';
import DashboardUserPage from '../pages/Core/Login/DashboardUserPage';
import RoleListPage from '../pages/Core/Usuarios/RoleListPage';
import AuditLogListPage from '../pages/Core/Auditoria';
import RoleDetailPage from '../pages/Core/Usuarios/RoleDetailPage';
import RoleCreatePage from '../pages/Core/Usuarios/RoleCreatePage';
import PermissionListPage from '../pages/Core/Usuarios/PermissionListPage';
import UserListPage from '../pages/Core/Usuarios/UserListPage';
import UserCreatePage from '../pages/Core/Usuarios/UserCreatePage';
import UserDetailPage from '../pages/Core/Usuarios/UserDetailPage';
import CompanyListPage from '../pages/Core/Empresas/CompanyListPage';
import CompanyDetailPage from '../pages/Core/Empresas/CompanyDetailPage';
import CompanyCreatePage from '../pages/Core/Empresas/CompanyCreatePage';
import BranchListPage from '../pages/Core/Sucursales/BranchListPage';
import BranchDetailPage from '../pages/Core/Sucursales/BranchDetailPage';
import BranchCreatePage from '../pages/Core/Sucursales/BranchCreatePage';
import DepartmentListPage from '../pages/Core/Departamentos/DepartmentListPage';
import DepartmentDetailPage from '../pages/Core/Departamentos/DepartmentDetailPage';

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
