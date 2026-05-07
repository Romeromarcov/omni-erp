// Cambiar contraseña de usuario (solo admin, sin old_password)
export async function changeUserPassword(old_password: string, new_password: string): Promise<{ message: string }> {
  return post<{ message: string }>(`/core/usuarios/change_password/`, { old_password, new_password });
}
import { get, post, put } from './api';

export interface EmpresaRef {
  id_empresa: string;
  nombre: string;
}

export interface SucursalRef {
  id_sucursal: string;
  nombre: string;
}

export interface Usuario {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  es_superusuario_innova: boolean;
  fecha_ultimo_login?: string;
  empresas?: EmpresaRef[];
  sucursales?: SucursalRef[];
  departamentos?: { id_departamento: string; nombre_departamento: string }[];
}

export async function fetchUsuarios(id_empresa?: string): Promise<Usuario[]> {
  const query = id_empresa ? `?id_empresa=${id_empresa}` : '';
  return get<Usuario[]>(`/core/usuarios/${query}`);
}

export interface UsuarioUpdatePayload {
  first_name?: string;
  last_name?: string;
  email?: string;
  empresas?: string[];
  sucursales?: string[];
  departamentos?: string[];
}

export async function createUsuario(data: Partial<Usuario> & { id_empresa?: string; empresas?: string[]; sucursales?: string[]; departamentos?: string[] }): Promise<Usuario> {
  return post<Usuario>('/core/usuarios/', data);
}

export async function updateUsuario(id: string, data: UsuarioUpdatePayload): Promise<Usuario> {
  return put<Usuario>(`/core/usuarios/${id}/`, data as Record<string, unknown>);
}
