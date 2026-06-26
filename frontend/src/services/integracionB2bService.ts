/**
 * Servicio de Integración B2B — configuración de integraciones, mapeo de campos
 * y logs de transacciones con sistemas externos.
 *
 * Endpoints del backend (`apps/integracion_b2b`, prefijo `/api/integracion-b2b/`).
 * Todos son CRUD estándar (DefaultRouter, sin @actions custom):
 *   /configuracion-integracion/   — configuración de una integración B2B.
 *   /mapeo-campos/                — mapeo campo interno→externo de una config.
 *   /logs-integracion/            — bitácora de transacciones (lectura útil).
 *
 * El aislamiento multi-tenant lo hace el backend (get_empresas_visible):
 * ConfiguracionIntegracion filtra por `?id_empresa=`; MapeoCampo y LogIntegracion
 * cuelgan de la configuración (`?id_configuracion_integracion=` / `?id_configuracion=`).
 * Los payloads son whitelist explícita de campos editables (CTF-005, defensa en
 * profundidad CWE-915).
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Estados de integración (convención de UI; backend acepta CharField libre) ─

export const ESTADO_INTEGRACION_COLOR = {
  exitoso: 'success' as const,
  pendiente: 'warning' as const,
  en_proceso: 'info' as const,
  error: 'error' as const,
  fallido: 'error' as const,
  reintentando: 'warning' as const,
};

// ── Configuración de integración ──────────────────────────────────────────────

export interface ConfiguracionIntegracion {
  id_configuracion: string;
  id_empresa: string;
  nombre_integracion: string;
  tipo_integracion: string;
  url_endpoint?: string | null;
  credenciales_json?: unknown;
  formato_datos: string;
  activo?: boolean;
  fecha_creacion?: string;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface ConfiguracionIntegracionPayload {
  id_empresa: string;
  nombre_integracion: string;
  tipo_integracion: string;
  url_endpoint: string | null;
  credenciales_json: unknown;
  formato_datos: string;
  activo: boolean;
}

// ── Mapeo de campo (interno→externo, por configuración) ───────────────────────

export interface MapeoCampo {
  id_mapeo_campo: string;
  id_configuracion_integracion: string;
  nombre_campo_interno: string;
  nombre_campo_externo: string;
  activo?: boolean;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface MapeoCampoPayload {
  id_configuracion_integracion: string;
  nombre_campo_interno: string;
  nombre_campo_externo: string;
  activo: boolean;
}

// ── Log de integración (lectura, por configuración) ───────────────────────────

export interface LogIntegracion {
  id_log_integracion: string;
  id_configuracion: string;
  fecha_hora?: string;
  tipo_transaccion: string;
  id_entidad_origen?: string | null;
  nombre_modelo_origen?: string | null;
  request_payload_json?: unknown;
  response_payload_json?: unknown;
  estado_integracion: string;
  mensaje_error?: string | null;
  duracion_ms?: number | null;
}

const BASE = '/integracion-b2b';

// ── Configuración de integración (CRUD) ───────────────────────────────────────

export const configuracionIntegracionService = {
  getAll: async (params?: { empresa?: string }): Promise<ConfiguracionIntegracion[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<ConfiguracionIntegracion> | ConfiguracionIntegracion[]
    >(`${BASE}/configuracion-integracion/${query ? '?' + query : ''}`);
    return toList<ConfiguracionIntegracion>(response);
  },

  getById: async (id: string): Promise<ConfiguracionIntegracion> =>
    get<ConfiguracionIntegracion>(`${BASE}/configuracion-integracion/${id}/`),

  create: async (
    payload: ConfiguracionIntegracionPayload,
  ): Promise<ConfiguracionIntegracion> =>
    post<ConfiguracionIntegracion>(
      `${BASE}/configuracion-integracion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: ConfiguracionIntegracionPayload,
  ): Promise<ConfiguracionIntegracion> =>
    patch<ConfiguracionIntegracion>(
      `${BASE}/configuracion-integracion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/configuracion-integracion/${id}/`);
  },
};

// ── Mapeo de campos (CRUD; filtrable por configuración) ───────────────────────

export const mapeoCampoService = {
  getAll: async (params?: { configuracion?: string }): Promise<MapeoCampo[]> => {
    const qs = new URLSearchParams();
    if (params?.configuracion) qs.set('id_configuracion_integracion', params.configuracion);
    const query = qs.toString();
    const response = await get<PaginatedResponse<MapeoCampo> | MapeoCampo[]>(
      `${BASE}/mapeo-campos/${query ? '?' + query : ''}`,
    );
    const lista = toList<MapeoCampo>(response);
    // El filtro por configuración lo refuerza el cliente además del querystring,
    // por si el backend ignora el parámetro (defensa en profundidad para la vista).
    return params?.configuracion
      ? lista.filter((m) => m.id_configuracion_integracion === params.configuracion)
      : lista;
  },

  getById: async (id: string): Promise<MapeoCampo> =>
    get<MapeoCampo>(`${BASE}/mapeo-campos/${id}/`),

  create: async (payload: MapeoCampoPayload): Promise<MapeoCampo> =>
    post<MapeoCampo>(`${BASE}/mapeo-campos/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: MapeoCampoPayload): Promise<MapeoCampo> =>
    patch<MapeoCampo>(
      `${BASE}/mapeo-campos/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/mapeo-campos/${id}/`);
  },
};

// ── Logs de integración (lectura por configuración) ───────────────────────────

export const logsIntegracionService = {
  getAll: async (params?: { configuracion?: string }): Promise<LogIntegracion[]> => {
    const qs = new URLSearchParams();
    if (params?.configuracion) qs.set('id_configuracion', params.configuracion);
    const query = qs.toString();
    const response = await get<PaginatedResponse<LogIntegracion> | LogIntegracion[]>(
      `${BASE}/logs-integracion/${query ? '?' + query : ''}`,
    );
    const lista = toList<LogIntegracion>(response);
    return params?.configuracion
      ? lista.filter((l) => l.id_configuracion === params.configuracion)
      : lista;
  },

  getById: async (id: string): Promise<LogIntegracion> =>
    get<LogIntegracion>(`${BASE}/logs-integracion/${id}/`),

  create: async (payload: Partial<LogIntegracion>): Promise<LogIntegracion> =>
    post<LogIntegracion>(
      `${BASE}/logs-integracion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: Partial<LogIntegracion>): Promise<LogIntegracion> =>
    patch<LogIntegracion>(
      `${BASE}/logs-integracion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/logs-integracion/${id}/`);
  },
};
