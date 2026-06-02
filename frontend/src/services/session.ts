// In-memory session store (FE-HIGH-13).
//
// PII and credential-adjacent data (the authenticated user, roles, permissions,
// the open caja física, device info) live ONLY in memory — never in localStorage.
// On a full page reload this is rebuilt from POST /auth/token/refresh/ (cookie)
// + GET /auth/profile/ by AuthContext.
//
// localStorage is reserved for non-PII UI selection only: id_empresa,
// id_sucursal, lang, sidebar_collapsed, device fingerprint.
import type { Usuario } from './users';
import type { DispositivoInfo } from '../types/dispositivos';

export interface CajaFisicaSel {
  id_caja_fisica: string;
  nombre: string;
  tipo_caja: string;
}

interface SessionState {
  usuario: Usuario | null;
  roles: Array<{ id: number; name: string }>;
  permisos: string[];
  cajaFisica: CajaFisicaSel | null;
  dispositivoInfo: DispositivoInfo | null;
}

const state: SessionState = {
  usuario: null,
  roles: [],
  permisos: [],
  cajaFisica: null,
  dispositivoInfo: null,
};

export function getSessionUser(): Usuario | null {
  return state.usuario;
}
export function setSessionUser(usuario: Usuario | null): void {
  state.usuario = usuario;
}

export function getSessionRoles(): Array<{ id: number; name: string }> {
  return state.roles;
}
export function setSessionRoles(roles: Array<{ id: number; name: string }>): void {
  state.roles = roles;
}

export function getSessionPermisos(): string[] {
  return state.permisos;
}
export function setSessionPermisos(permisos: string[]): void {
  state.permisos = permisos;
}

export function getSessionCajaFisica(): CajaFisicaSel | null {
  return state.cajaFisica;
}
export function setSessionCajaFisica(caja: CajaFisicaSel | null): void {
  state.cajaFisica = caja;
}

export function getSessionDispositivoInfo(): DispositivoInfo | null {
  return state.dispositivoInfo;
}
export function setSessionDispositivoInfo(info: DispositivoInfo | null): void {
  state.dispositivoInfo = info;
}

export function getSessionUsuarioId(): string {
  return state.usuario?.id ?? '';
}

export function clearSession(): void {
  state.usuario = null;
  state.roles = [];
  state.permisos = [];
  state.cajaFisica = null;
  state.dispositivoInfo = null;
}
