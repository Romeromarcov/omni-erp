import { post, get, fetcher, setAccessToken, clearAccessToken } from './api';
import type { Usuario } from './users';
import type { LoginResponse, DispositivoInfo } from '../types/dispositivos';
import { getDeviceInfo } from '../utils/deviceFingerprint';
import { statusDeError } from '../utils/api';
import { verificarMfaLogin } from './mfa';
import {
  setSessionUser,
  setSessionRoles,
  setSessionPermisos,
  clearSession,
} from './session';

export class MfaChallengeError extends Error {
  readonly mfaToken: string;
  readonly metodo: string;

  constructor(mfaToken: string, metodo = 'TOTP') {
    super('Se requiere verificación de segundo factor (2FA).');
    this.name = 'MfaChallengeError';
    this.mfaToken = mfaToken;
    this.metodo = metodo;
  }
}

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

async function finalizarAutenticacion(res: LoginResponse): Promise<{
  token: string;
  usuario: Usuario;
  dispositivo?: DispositivoInfo;
}> {
  if (!res.access) {
    throw new Error('Respuesta de autenticación sin token de acceso.');
  }
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

  if (res.mfa_requerido && res.mfa_token) {
    throw new MfaChallengeError(res.mfa_token, res.metodo ?? 'TOTP');
  }

  return finalizarAutenticacion(res);
}

export async function verifyMfaAndFetchUser(mfaToken: string, codigo: string): Promise<{
  token: string;
  usuario: Usuario;
  dispositivo?: DispositivoInfo;
}> {
  const deviceInfo = getDeviceInfo();
  const res = await verificarMfaLogin(mfaToken, codigo, deviceInfo);
  return finalizarAutenticacion(res);
}

export type HydrateSessionResult =
  | { status: 'ok'; usuario: Usuario }
  | { status: 'rejected' }
  | { status: 'transient_error' };

function esRechazoAutenticacion(err: unknown, aceptar400: boolean): boolean {
  const status = statusDeError(err);
  if (status === 401 || status === 403 || (aceptar400 && status === 400)) {
    return true;
  }
  return err instanceof Error && err.message.startsWith('Sesión expirada');
}

/**
 * Rebuilds the session after a full page reload distinguishing confirmed auth
 * rejections (401/403, 400 on refresh without cookie, or 200 without access
 * token) from transient network/offline/5xx errors so offline outbox sales
 * survive F5 reloads while disconnected.
 */
export async function hydrateSessionResult(): Promise<HydrateSessionResult> {
  try {
    const refresh = await fetcher<{ access?: string }>('/auth/token/refresh/', {
      method: 'POST',
      body: JSON.stringify({}),
      timeoutMs: 15000,
    });
    if (!refresh.access) {
      clearAccessToken();
      clearSession();
      return { status: 'rejected' };
    }
    setAccessToken(refresh.access);
  } catch (err) {
    clearAccessToken();
    clearSession();
    return { status: esRechazoAutenticacion(err, true) ? 'rejected' : 'transient_error' };
  }

  try {
    const usuario = await get<Usuario>('/auth/profile/');
    setSessionUser(usuario);
    await loadRolesYPermisos(usuario.id);
    return { status: 'ok', usuario };
  } catch (err) {
    clearAccessToken();
    clearSession();
    return { status: esRechazoAutenticacion(err, false) ? 'rejected' : 'transient_error' };
  }
}

/**
 * Rebuilds the session after a full page reload. Uses the httpOnly refresh
 * cookie to obtain a fresh access token, then hydrates the user via the
 * lightweight auth profile endpoint. Returns the user on success, null if the
 * user is unauthenticated or offline.
 */
export async function hydrateSession(): Promise<Usuario | null> {
  const res = await hydrateSessionResult();
  return res.status === 'ok' ? res.usuario : null;
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
    // img-cache puede contener logos/adjuntos del tenant: también se purga.
    void caches.delete('img-cache').catch(() => undefined);
  }
}
