import { get, post, put } from './api';

export type Rol = {
  id_rol: string;
  nombre_rol: string;
  descripcion: string;
  activo: boolean;
  id_empresa?: string;
};

export async function fetchRoles(): Promise<Rol[]> {
  return get<Rol[]>('/core/roles/');
}

export async function fetchRol(id_rol: string): Promise<Rol> {
  return get<Rol>(`/core/roles/${id_rol}/`);
}

export async function createRol(data: Partial<Rol>): Promise<Rol> {
  return post<Rol>('/core/roles/', data);
}

export async function updateRol(id_rol: string, data: Partial<Rol>): Promise<Rol> {
  return put<Rol>(`/core/roles/${id_rol}/`, data);
}
