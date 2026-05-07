import { get } from './api';

export interface UsuarioRol {
  id_usuario_rol: string;
  id_usuario: string;
  id_rol: string;
  fecha_asignacion: string;
  id_usuario_username?: string;
  id_rol_nombre?: string;
}

export async function fetchUsuarioRoles(id_usuario: string): Promise<UsuarioRol[]> {
  return get<UsuarioRol[]>(`/core/usuario_roles/?id_usuario=${id_usuario}`);
}
