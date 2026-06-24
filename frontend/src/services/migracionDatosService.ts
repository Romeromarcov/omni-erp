/**
 * Servicio de Migración de Datos — plantillas y procesos de importación.
 *
 * Endpoints del backend (`apps/migracion_datos`, prefijo `/api/migracion-datos/`).
 * Todos son CRUD estándar (DefaultRouter, sin @actions custom):
 *   /plantillas-migracion/        — catálogo GLOBAL de plantillas. La ESCRITURA
 *                                   (create/update/delete) está restringida a
 *                                   superusuario (`SuperuserWriteMixin`): para un
 *                                   usuario normal devuelve 403. La lectura sí
 *                                   funciona. La UI maneja el 403 con mensajeDeError.
 *   /procesos-migracion/          — instancia de un proceso de migración (estado).
 *   /detalles-error-migracion/    — errores de un proceso (lectura útil).
 *
 * El aislamiento multi-tenant lo hace el backend (get_empresas_visible):
 * ProcesoMigracion filtra por `?id_empresa=` y DetalleErrorMigracion cuelga del
 * proceso. Los payloads son whitelist explícita de campos editables (CTF-005,
 * defensa en profundidad CWE-915).
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Estados de proceso (convención de UI; backend acepta CharField libre) ─────

export type EstadoProceso = 'PENDIENTE' | 'EN_PROCESO' | 'COMPLETADO' | 'FALLIDO' | 'CANCELADO';

export const ESTADO_PROCESO_OPCIONES: { value: EstadoProceso; label: string }[] = [
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'EN_PROCESO', label: 'En proceso' },
  { value: 'COMPLETADO', label: 'Completado' },
  { value: 'FALLIDO', label: 'Fallido' },
  { value: 'CANCELADO', label: 'Cancelado' },
];

// Color del chip por estado del proceso.
export const ESTADO_PROCESO_COLOR = {
  pendiente: 'warning' as const,
  en_proceso: 'info' as const,
  completado: 'success' as const,
  fallido: 'error' as const,
  cancelado: 'default' as const,
};

// ── Plantilla de migración (catálogo global) ──────────────────────────────────

export interface PlantillaMigracion {
  id_plantilla_migracion: string;
  nombre_plantilla: string;
  modulo_destino: string;
  modelo_destino: string;
  formato_archivo: string;
  estructura_json: unknown;
  activo?: boolean;
  fecha_creacion?: string;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface PlantillaMigracionPayload {
  nombre_plantilla: string;
  modulo_destino: string;
  modelo_destino: string;
  formato_archivo: string;
  estructura_json: unknown;
  activo: boolean;
}

// ── Proceso de migración (runtime) ─────────────────────────────────────────────

export interface ProcesoMigracion {
  id_proceso_migracion: string;
  id_empresa: string;
  id_plantilla_migracion: string;
  id_usuario_ejecutor: string;
  fecha_inicio?: string;
  fecha_fin?: string | null;
  estado_proceso: string;
  total_registros_procesados?: number;
  total_registros_exitosos?: number;
  total_registros_fallidos?: number;
  ruta_archivo_cargado: string;
  ruta_archivo_errores?: string | null;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface ProcesoMigracionPayload {
  id_empresa: string;
  id_plantilla_migracion: string;
  id_usuario_ejecutor: string;
  estado_proceso: string;
  total_registros_procesados: number;
  total_registros_exitosos: number;
  total_registros_fallidos: number;
  ruta_archivo_cargado: string;
  ruta_archivo_errores: string | null;
}

// ── Detalle de error de migración (lectura) ────────────────────────────────────

export interface DetalleErrorMigracion {
  id_detalle_error: string;
  id_proceso_migracion: string;
  numero_fila_archivo?: number | null;
  campo_error?: string | null;
  mensaje_error: string;
  datos_originales_json?: unknown;
  fecha_registro_error?: string;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface DetalleErrorMigracionPayload {
  id_proceso_migracion: string;
  numero_fila_archivo: number | null;
  campo_error: string | null;
  mensaje_error: string;
  datos_originales_json: unknown;
}

const BASE = '/migracion-datos';

// ── Plantillas de migración (CRUD; escritura solo superusuario) ───────────────

export const plantillasMigracionService = {
  getAll: async (params?: { activo?: boolean }): Promise<PlantillaMigracion[]> => {
    const qs = new URLSearchParams();
    if (params?.activo !== undefined) qs.set('activo', String(params.activo));
    const query = qs.toString();
    const response = await get<PaginatedResponse<PlantillaMigracion> | PlantillaMigracion[]>(
      `${BASE}/plantillas-migracion/${query ? '?' + query : ''}`,
    );
    return toList<PlantillaMigracion>(response);
  },

  getById: async (id: string): Promise<PlantillaMigracion> =>
    get<PlantillaMigracion>(`${BASE}/plantillas-migracion/${id}/`),

  create: async (payload: PlantillaMigracionPayload): Promise<PlantillaMigracion> =>
    post<PlantillaMigracion>(
      `${BASE}/plantillas-migracion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: PlantillaMigracionPayload): Promise<PlantillaMigracion> =>
    patch<PlantillaMigracion>(
      `${BASE}/plantillas-migracion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/plantillas-migracion/${id}/`);
  },
};

// ── Procesos de migración (CRUD) ──────────────────────────────────────────────

export const procesosMigracionService = {
  getAll: async (params?: {
    empresa?: string;
    plantilla?: string;
    estado?: string;
  }): Promise<ProcesoMigracion[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.plantilla) qs.set('id_plantilla_migracion', params.plantilla);
    if (params?.estado) qs.set('estado_proceso', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<ProcesoMigracion> | ProcesoMigracion[]>(
      `${BASE}/procesos-migracion/${query ? '?' + query : ''}`,
    );
    return toList<ProcesoMigracion>(response);
  },

  getById: async (id: string): Promise<ProcesoMigracion> =>
    get<ProcesoMigracion>(`${BASE}/procesos-migracion/${id}/`),

  create: async (payload: ProcesoMigracionPayload): Promise<ProcesoMigracion> =>
    post<ProcesoMigracion>(
      `${BASE}/procesos-migracion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: ProcesoMigracionPayload): Promise<ProcesoMigracion> =>
    patch<ProcesoMigracion>(
      `${BASE}/procesos-migracion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/procesos-migracion/${id}/`);
  },
};

// ── Detalles de error de migración (lectura por proceso) ──────────────────────

export const detallesErrorMigracionService = {
  getAll: async (params?: { proceso?: string }): Promise<DetalleErrorMigracion[]> => {
    const qs = new URLSearchParams();
    if (params?.proceso) qs.set('id_proceso_migracion', params.proceso);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<DetalleErrorMigracion> | DetalleErrorMigracion[]
    >(`${BASE}/detalles-error-migracion/${query ? '?' + query : ''}`);
    const lista = toList<DetalleErrorMigracion>(response);
    // El filtro por proceso lo refuerza el cliente además del querystring, por si
    // el backend ignora el parámetro (defensa en profundidad para la vista).
    return params?.proceso
      ? lista.filter((d) => d.id_proceso_migracion === params.proceso)
      : lista;
  },

  getById: async (id: string): Promise<DetalleErrorMigracion> =>
    get<DetalleErrorMigracion>(`${BASE}/detalles-error-migracion/${id}/`),

  create: async (payload: DetalleErrorMigracionPayload): Promise<DetalleErrorMigracion> =>
    post<DetalleErrorMigracion>(
      `${BASE}/detalles-error-migracion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: DetalleErrorMigracionPayload,
  ): Promise<DetalleErrorMigracion> =>
    patch<DetalleErrorMigracion>(
      `${BASE}/detalles-error-migracion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/detalles-error-migracion/${id}/`);
  },
};
