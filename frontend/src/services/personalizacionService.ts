/**
 * Servicio de Personalización — versiones del DSL de personalización por empresa.
 *
 * Endpoints del backend (`apps/personalizacion`, prefijo `/api/personalizacion/`).
 * Solo `configuraciones/` (PersonalizacionConfigViewSet) está expuesto por el
 * router; las demás entidades del módulo (EntidadInstancia, EstadoPersonalizado,
 * VistaPersonalizada) NO tienen router.
 *
 *   GET    configuraciones/                 — CRUD estándar (lista paginada/array).
 *   GET    configuraciones/activa/?empresa_id=    — config activa (404 si no hay).
 *   POST   configuraciones/{id}/activar/    — activa esta versión, desactiva las demás.
 *   GET    configuraciones/historial/?empresa_id= — todas las versiones (desc por version).
 *
 * El aislamiento multi-tenant lo hace el backend (get_empresas_visible). El payload
 * es whitelist explícita de campos editables (CTF-005, defensa en profundidad CWE-915).
 */
import { get, post, patch, del } from './api';
import { toList, statusDeError, type PaginatedResponse } from '../utils/api';

// ── Estado de aplicación (convención de UI para el chip activo/inactivo) ──────

export const ACTIVO_COLOR = {
  sí: 'success' as const,
  si: 'success' as const,
  no: 'default' as const,
};

// ── Versión de configuración del DSL ──────────────────────────────────────────

export interface PersonalizacionConfig {
  id_config: string;
  id_empresa: string;
  version: number;
  descripcion: string;
  config_yaml: string;
  config_dict: unknown;
  activo: boolean;
  fecha_creacion?: string;
  fecha_aplicacion?: string | null;
  resultado_aplicacion?: unknown;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface PersonalizacionConfigPayload {
  id_empresa: string;
  descripcion: string;
  config_yaml: string;
  config_dict: unknown;
}

const BASE = '/personalizacion';

export const personalizacionConfigService = {
  getAll: async (params?: { empresa?: string }): Promise<PersonalizacionConfig[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<PersonalizacionConfig> | PersonalizacionConfig[]
    >(`${BASE}/configuraciones/${query ? '?' + query : ''}`);
    return toList<PersonalizacionConfig>(response);
  },

  /** Historial de versiones (desc por version) de la empresa indicada. */
  historial: async (empresaId?: string): Promise<PersonalizacionConfig[]> => {
    const qs = new URLSearchParams();
    if (empresaId) qs.set('empresa_id', empresaId);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<PersonalizacionConfig> | PersonalizacionConfig[]
    >(`${BASE}/configuraciones/historial/${query ? '?' + query : ''}`);
    return toList<PersonalizacionConfig>(response);
  },

  getById: async (id: string): Promise<PersonalizacionConfig> =>
    get<PersonalizacionConfig>(`${BASE}/configuraciones/${id}/`),

  /** Config activa de la empresa. El backend responde 404 si no hay; lo mapeamos a null. */
  activa: async (empresaId?: string): Promise<PersonalizacionConfig | null> => {
    const qs = new URLSearchParams();
    if (empresaId) qs.set('empresa_id', empresaId);
    const query = qs.toString();
    try {
      return await get<PersonalizacionConfig>(
        `${BASE}/configuraciones/activa/${query ? '?' + query : ''}`,
      );
    } catch (e: unknown) {
      if (statusDeError(e) === 404) return null;
      throw e;
    }
  },

  create: async (payload: PersonalizacionConfigPayload): Promise<PersonalizacionConfig> =>
    post<PersonalizacionConfig>(
      `${BASE}/configuraciones/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: PersonalizacionConfigPayload,
  ): Promise<PersonalizacionConfig> =>
    patch<PersonalizacionConfig>(
      `${BASE}/configuraciones/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/configuraciones/${id}/`);
  },

  /** Activa esta versión (rollback): desactiva las demás de la misma empresa. */
  activar: async (id: string): Promise<PersonalizacionConfig> =>
    post<PersonalizacionConfig>(`${BASE}/configuraciones/${id}/activar/`, {}),
};
