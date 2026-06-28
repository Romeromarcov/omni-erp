/**
 * Servicio de Gestión de Aprobaciones — motor configurable de aprobaciones.
 *
 * Endpoints del backend (`apps/gestion_aprobaciones`, prefijo
 * `/api/gestion-aprobaciones/`). Todos son CRUD estándar (DefaultRouter, sin
 * @actions custom):
 *   /tipos-aprobacion/         — configuración: qué se aprueba (por módulo).
 *   /flujos-aprobacion/        — configuración: etapas/aprobadores por tipo.
 *   /solicitudes-aprobacion/   — instancia runtime de una aprobación en curso.
 *   /registros-aprobacion/     — cada decisión (aprobado/rechazado) de una etapa.
 *
 * El aislamiento multi-tenant lo hace el backend (get_empresas_visible);
 * TipoAprobacion filtra por `?id_empresa=`, el resto cuelga del tipo. Los montos
 * viajan como STRING decimal (R-CODE-4). Los payloads son whitelist explícita de
 * campos editables (CTF-005, defensa en profundidad CWE-915).
 *
 * `estado_solicitud` y `tipo_decision` son CharField libres en el backend (sin
 * choices). La UI propone valores convencionales y el backend los acepta tal
 * cual; "aprobar/rechazar" se modela creando un RegistroAprobacion y/o
 * PATCH-eando el `estado_solicitud` de la solicitud (no hay endpoint dedicado).
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Estados de solicitud (convención de UI; backend acepta CharField libre) ───

export type EstadoSolicitud = 'PENDIENTE' | 'EN_PROCESO' | 'APROBADA' | 'RECHAZADA' | 'CANCELADA';

export const ESTADO_SOLICITUD_OPCIONES: { value: EstadoSolicitud; label: string }[] = [
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'EN_PROCESO', label: 'En proceso' },
  { value: 'APROBADA', label: 'Aprobada' },
  { value: 'RECHAZADA', label: 'Rechazada' },
  { value: 'CANCELADA', label: 'Cancelada' },
];

/** Tipo de decisión de un registro de aprobación. */
export type TipoDecision = 'APROBADO' | 'RECHAZADO';

export const TIPO_DECISION_OPCIONES: { value: TipoDecision; label: string }[] = [
  { value: 'APROBADO', label: 'Aprobado' },
  { value: 'RECHAZADO', label: 'Rechazado' },
];

/** True si la solicitud está en un estado terminal (no admite más decisiones). */
export function solicitudEstaCerrada(estado: string): boolean {
  return estado === 'APROBADA' || estado === 'RECHAZADA' || estado === 'CANCELADA';
}

// ── Tipo de aprobación ────────────────────────────────────────────────────────

export interface TipoAprobacion {
  id_tipo_aprobacion: string;
  id_empresa: string;
  codigo_tipo: string;
  nombre_tipo: string;
  descripcion?: string | null;
  modulo_origen: string;
  activo?: boolean;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface TipoAprobacionPayload {
  id_empresa: string;
  codigo_tipo: string;
  nombre_tipo: string;
  descripcion: string | null;
  modulo_origen: string;
  activo: boolean;
}

// ── Flujo de aprobación (etapa) ───────────────────────────────────────────────

export interface FlujoAprobacion {
  id_flujo_aprobacion: string;
  id_tipo_aprobacion: string;
  orden_etapa: number;
  nombre_etapa: string;
  rol_aprobador?: string | null;
  id_usuario_aprobador?: string | null;
  monto_minimo?: string | null;
  monto_maximo?: string | null;
  activo?: boolean;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface FlujoAprobacionPayload {
  id_tipo_aprobacion: string;
  orden_etapa: number;
  nombre_etapa: string;
  rol_aprobador: string | null;
  id_usuario_aprobador: string | null;
  monto_minimo: string | null;
  monto_maximo: string | null;
  activo: boolean;
}

// ── Solicitud de aprobación (runtime) ─────────────────────────────────────────

export interface SolicitudAprobacion {
  id_solicitud_aprobacion: string;
  id_tipo_aprobacion: string;
  id_entidad_origen: string;
  nombre_modelo_origen: string;
  id_usuario_solicitante: string;
  fecha_solicitud?: string;
  estado_solicitud: string;
  comentarios_solicitante?: string | null;
  fecha_ultima_actualizacion?: string;
  etapa_actual_flujo?: string | null;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface SolicitudAprobacionPayload {
  id_tipo_aprobacion: string;
  id_entidad_origen: string;
  nombre_modelo_origen: string;
  id_usuario_solicitante: string;
  estado_solicitud: string;
  comentarios_solicitante: string | null;
  etapa_actual_flujo: string | null;
}

/** Payload parcial para actualizar solo el estado de una solicitud (PATCH). */
export interface SolicitudEstadoPayload {
  estado_solicitud: string;
}

// ── Registro de aprobación (decisión) ─────────────────────────────────────────

export interface RegistroAprobacion {
  id_registro_aprobacion: string;
  id_solicitud_aprobacion: string;
  id_flujo_aprobacion_etapa: string;
  id_usuario_aprobador: string;
  fecha_decision?: string;
  tipo_decision: string;
  comentarios?: string | null;
}

/** Whitelist explícita de campos editables (CTF-005, defensa CWE-915). */
export interface RegistroAprobacionPayload {
  id_solicitud_aprobacion: string;
  id_flujo_aprobacion_etapa: string;
  id_usuario_aprobador: string;
  tipo_decision: string;
  comentarios: string | null;
}

const BASE = '/gestion-aprobaciones';

// ── Tipos de aprobación (CRUD) ────────────────────────────────────────────────

export const tiposAprobacionService = {
  getAll: async (params?: { empresa?: string; modulo?: string }): Promise<TipoAprobacion[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.modulo) qs.set('modulo_origen', params.modulo);
    const query = qs.toString();
    const response = await get<PaginatedResponse<TipoAprobacion> | TipoAprobacion[]>(
      `${BASE}/tipos-aprobacion/${query ? '?' + query : ''}`,
    );
    return toList<TipoAprobacion>(response);
  },

  getById: async (id: string): Promise<TipoAprobacion> =>
    get<TipoAprobacion>(`${BASE}/tipos-aprobacion/${id}/`),

  create: async (payload: TipoAprobacionPayload): Promise<TipoAprobacion> =>
    post<TipoAprobacion>(`${BASE}/tipos-aprobacion/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: TipoAprobacionPayload): Promise<TipoAprobacion> =>
    patch<TipoAprobacion>(
      `${BASE}/tipos-aprobacion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/tipos-aprobacion/${id}/`);
  },
};

// ── Flujos de aprobación (CRUD) ───────────────────────────────────────────────

export const flujosAprobacionService = {
  getAll: async (params?: { tipo?: string }): Promise<FlujoAprobacion[]> => {
    const qs = new URLSearchParams();
    if (params?.tipo) qs.set('id_tipo_aprobacion', params.tipo);
    const query = qs.toString();
    const response = await get<PaginatedResponse<FlujoAprobacion> | FlujoAprobacion[]>(
      `${BASE}/flujos-aprobacion/${query ? '?' + query : ''}`,
    );
    return toList<FlujoAprobacion>(response);
  },

  getById: async (id: string): Promise<FlujoAprobacion> =>
    get<FlujoAprobacion>(`${BASE}/flujos-aprobacion/${id}/`),

  create: async (payload: FlujoAprobacionPayload): Promise<FlujoAprobacion> =>
    post<FlujoAprobacion>(
      `${BASE}/flujos-aprobacion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: FlujoAprobacionPayload): Promise<FlujoAprobacion> =>
    patch<FlujoAprobacion>(
      `${BASE}/flujos-aprobacion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/flujos-aprobacion/${id}/`);
  },
};

// ── Solicitudes de aprobación (CRUD + cambio de estado) ───────────────────────

export const solicitudesAprobacionService = {
  getAll: async (params?: { tipo?: string; estado?: string }): Promise<SolicitudAprobacion[]> => {
    const qs = new URLSearchParams();
    if (params?.tipo) qs.set('id_tipo_aprobacion', params.tipo);
    if (params?.estado) qs.set('estado_solicitud', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<SolicitudAprobacion> | SolicitudAprobacion[]>(
      `${BASE}/solicitudes-aprobacion/${query ? '?' + query : ''}`,
    );
    return toList<SolicitudAprobacion>(response);
  },

  getById: async (id: string): Promise<SolicitudAprobacion> =>
    get<SolicitudAprobacion>(`${BASE}/solicitudes-aprobacion/${id}/`),

  create: async (payload: SolicitudAprobacionPayload): Promise<SolicitudAprobacion> =>
    post<SolicitudAprobacion>(
      `${BASE}/solicitudes-aprobacion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: SolicitudAprobacionPayload): Promise<SolicitudAprobacion> =>
    patch<SolicitudAprobacion>(
      `${BASE}/solicitudes-aprobacion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  /** PATCH parcial: actualiza solo el estado (al registrar una decisión). */
  cambiarEstado: async (id: string, estado: string): Promise<SolicitudAprobacion> =>
    patch<SolicitudAprobacion>(`${BASE}/solicitudes-aprobacion/${id}/`, {
      estado_solicitud: estado,
    }),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/solicitudes-aprobacion/${id}/`);
  },
};

// ── Registros de aprobación / decisiones (CRUD) ───────────────────────────────

export const registrosAprobacionService = {
  getAll: async (params?: { solicitud?: string }): Promise<RegistroAprobacion[]> => {
    const qs = new URLSearchParams();
    if (params?.solicitud) qs.set('id_solicitud_aprobacion', params.solicitud);
    const query = qs.toString();
    const response = await get<PaginatedResponse<RegistroAprobacion> | RegistroAprobacion[]>(
      `${BASE}/registros-aprobacion/${query ? '?' + query : ''}`,
    );
    const lista = toList<RegistroAprobacion>(response);
    return params?.solicitud
      ? lista.filter((r) => r.id_solicitud_aprobacion === params.solicitud)
      : lista;
  },

  getById: async (id: string): Promise<RegistroAprobacion> =>
    get<RegistroAprobacion>(`${BASE}/registros-aprobacion/${id}/`),

  create: async (payload: RegistroAprobacionPayload): Promise<RegistroAprobacion> =>
    post<RegistroAprobacion>(
      `${BASE}/registros-aprobacion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: RegistroAprobacionPayload): Promise<RegistroAprobacion> =>
    patch<RegistroAprobacion>(
      `${BASE}/registros-aprobacion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/registros-aprobacion/${id}/`);
  },
};
