import { post, get, fetcher, setAccessToken, clearAccessToken } from './api';
import type { Usuario } from './users';
import type { LoginResponse, DispositivoInfo } from '../types/dispositivos';
import { getDeviceInfo } from '../utils/deviceFingerprint';
import {
  setSessionUser,
  setSessionRoles,
  setSessionPermisos,
  clearSession,
} from './session';

export async function fetchMe(): Promise<Usuario> {
  return get<Usuario>('/core/usuarios/me/');
}

interface Role {
  id: number;
  name: string;
}

/**
 * Loads the user's roles + flattened permission codes into the in-memory
 * session store. Never blocks login on failure.
 */
export async function loadRolesYPermisos(usuarioId: string): Promise<void> {
  try {
    const rolesRes = await get(`/core/usuario_roles/?id_usuario=${usuarioId}`);
    const roles: Role[] = Array.isArray(rolesRes)
      ? rolesRes.map((r) => ({ id: r.id_rol, name: r.id_rol_nombre_rol }))
      : [];
    const permisosSet = new Set<string>();
    interface Permiso {
      codigo_permiso: string;
    }
    if (Array.isArray(rolesRes)) {
      for (const r of rolesRes) {
        if (r.id_rol_permisos && Array.isArray(r.id_rol_permisos)) {
          r.id_rol_permisos.forEach((p: Permiso) => permisosSet.add(p.codigo_permiso));
        }
      }
    }
    setSessionRoles(roles);
    setSessionPermisos(Array.from(permisosSet));
  } catch {
    // Si falla la carga de roles/permisos, continuar sin bloquear el login.
    setSessionRoles([]);
    setSessionPermisos([]);
  }
}

export async function loginAndFetchUser(username: string, password: string): Promise<{
  token: string;
  // SEC-03: refresh token is managed as an httpOnly cookie by the browser.
  // It is NOT returned here to prevent XSS exposure.
  usuario: Usuario;
  dispositivo?: DispositivoInfo;
}> {
  const deviceInfo = getDeviceInfo();

  const res = await post<LoginResponse>('/auth/login/', {
    username,
    password,
    ...deviceInfo,
  });

  // FE-HIGH-13: access token kept in memory only (never localStorage).
  // The refresh token arrives as an httpOnly cookie set by the backend.
  setAccessToken(res.access);

  const usuario = await fetchMe();
  setSessionUser(usuario);

  await loadRolesYPermisos(usuario.id);

  return {
    token: res.access,
    usuario,
    dispositivo: res.dispositivo,
  };
}

/**
 * Rebuilds the session after a full page reload. Uses the httpOnly refresh
 * cookie to obtain a fresh access token, then hydrates the user via the
 * lightweight auth profile endpoint. Returns the user on success, null if the
 * user is unauthenticated (no/expired cookie).
 */
export async function hydrateSession(): Promise<Usuario | null> {
  try {
    const refresh = await fetcher<{ access?: string }>('/auth/token/refresh/', {
      method: 'POST',
      body: JSON.stringify({}),
      timeoutMs: 15000,
    });
    if (!refresh.access) {
      return null;
    }
    setAccessToken(refresh.access);
  } catch {
    clearAccessToken();
    clearSession();
    return null;
  }

  try {
    const usuario = await get<Usuario>('/auth/profile/');
    setSessionUser(usuario);
    await loadRolesYPermisos(usuario.id);
    return usuario;
  } catch {
    clearAccessToken();
    clearSession();
    return null;
  }
}

/**
 * Clears all in-memory auth state. The httpOnly refresh cookie is left to the
 * backend / its own expiry; there is no client-side logout endpoint.
 */
export function logoutSession(): void {
  clearAccessToken();
  clearSession();
  // Offline Nivel 1: el SW cachea respuestas GET de la API (Workbox
  // 'api-cache'). Al cerrar sesión se purga para que otro usuario del mismo
  // navegador no pueda ver datos del tenant anterior estando offline.
  // Best-effort: si la Cache API no existe (tests/jsdom) no hace nada.
  if (typeof caches !== 'undefined') {
    void caches.delete('api-cache').catch(() => undefined);
  }
}
