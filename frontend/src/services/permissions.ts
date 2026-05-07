import { get } from './api';

export type Permiso = {
  id_permiso: string;
  codigo_permiso: string;
  nombre_permiso: string;
  descripcion: string;
  modulo: string;
  activo: boolean;
};

export async function fetchPermisos(): Promise<Permiso[]> {
  return get<Permiso[]>('/permisos/');
}
