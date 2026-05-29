import { post, get } from './api';
import type { Usuario } from './users';
import type { LoginResponse, DispositivoInfo } from '../types/dispositivos';
import { getDeviceInfo } from '../utils/deviceFingerprint';

export async function fetchMe(): Promise<Usuario> {
  return get<Usuario>('/core/usuarios/me/');
}

export async function loginAndFetchUser(username: string, password: string): Promise<{
  token: string;
  // SEC-03: refresh token is now managed as an httpOnly cookie by the browser.
  // It is NO LONGER returned here to prevent XSS exposure.
  usuario: Usuario;
  dispositivo?: DispositivoInfo;
}> {
  // Obtener información del dispositivo
  const deviceInfo = getDeviceInfo();

  const res = await post<LoginResponse>('/auth/login/', {
    username,
    password,
    ...deviceInfo
  });

  // Guardar access token en localStorage.
  // SEC-03: el refresh token ya NO se guarda en localStorage — el backend lo envía
  // como httpOnly cookie (path=/api/auth/) que el navegador gestiona automáticamente.
  localStorage.setItem('token', res.access);

  // Obtener el usuario autenticado
  const usuario = await fetchMe();
  localStorage.setItem('usuario', JSON.stringify(usuario));
  if (usuario && usuario.id) {
    localStorage.setItem('id_usuario', usuario.id);
  }

  // Cargar roles y permisos del usuario
  type Role = { id: number; name: string };
  let roles: Role[] = [];
  let permisos: string[] = [];
  try {
    const rolesRes = await get(`/core/usuario_roles/?id_usuario=${usuario.id}`);
    roles = Array.isArray(rolesRes) ? rolesRes.map(r => ({ id: r.id_rol, name: r.id_rol_nombre_rol })) : [];
    localStorage.setItem('roles', JSON.stringify(roles));
    // Opcional: cargar permisos por rol
    const permisosSet = new Set<string>();
    interface Permiso {
      codigo_permiso: string;
      // agrega otras propiedades si es necesario
    }
    if (Array.isArray(rolesRes)) {
      for (const r of rolesRes) {
        if (r.id_rol_permisos && Array.isArray(r.id_rol_permisos)) {
          r.id_rol_permisos.forEach((p: Permiso) => permisosSet.add(p.codigo_permiso));
        }
      }
    }
    permisos = Array.from(permisosSet);
    localStorage.setItem('permisos', JSON.stringify(permisos));
  } catch {
    // Si falla la carga de roles/permisos, continuar sin bloquear el login
    localStorage.setItem('roles', JSON.stringify([]));
    localStorage.setItem('permisos', JSON.stringify([]));
  }

  return {
    token: res.access,
    usuario,
    dispositivo: res.dispositivo
  };
}
