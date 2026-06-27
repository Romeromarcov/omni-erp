/**
 * Servicio de RRHH — Beneficios y Licencias (workstream F: UI para el módulo
 * hoy API-only). El backend (`apps/rrhh`, base /api/rrhh/) ya está 100 %.
 *
 * Endpoints (todos CRUD estándar de `BaseModelViewSet`; el tenant se resuelve por
 * `id_empresa` propio o vía el empleado padre — R-CODE-1):
 *   /rrhh/beneficios/            (BeneficioViewSet)        — catálogo de beneficios
 *   /rrhh/beneficios-empleado/   (BeneficioEmpleadoViewSet)— asignación a empleado
 *   /rrhh/tipos-licencia/        (TipoLicenciaViewSet)     — tipos de licencia
 *   /rrhh/licencias-empleado/    (LicenciaEmpleadoViewSet) — licencia solicitada
 *
 * El backend NO expone filtros por querystring ni acciones custom (aprobar/
 * rechazar): el estado de `BeneficioEmpleado`/`LicenciaEmpleado` es un campo
 * escribible, así que aprobar/rechazar/cancelar una licencia es un PATCH a
 * `estado`. Los filtros por empleado/estado se aplican client-side.
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

const BASE = '/rrhh';

// ── Beneficio (catálogo) ──────────────────────────────────────────────────────

export type TipoBeneficio =
  | 'MONETARIO'
  | 'NO_MONETARIO'
  | 'TIEMPO'
  | 'SALUD'
  | 'EDUCACION'
  | 'TRANSPORTE'
  | 'ALIMENTACION'
  | 'OTRO';

export interface Beneficio {
  id_beneficio: string;
  id_empresa?: string;
  nombre_beneficio: string;
  descripcion: string | null;
  tipo_beneficio: TipoBeneficio | string;
  /** Montos/porcentajes como string decimal (R-CODE-4). */
  monto_fijo: string | null;
  porcentaje_salario: string | null;
  es_obligatorio: boolean;
  activo: boolean;
  fecha_creacion?: string;
}

/** Payload de escritura (whitelist; `id_empresa` requerido por el serializer). */
export interface BeneficioPayload {
  id_empresa: string;
  nombre_beneficio: string;
  descripcion: string | null;
  tipo_beneficio: string;
  monto_fijo: string | null;
  porcentaje_salario: string | null;
  es_obligatorio: boolean;
  activo: boolean;
}

// ── BeneficioEmpleado (asignación) ────────────────────────────────────────────

export type EstadoBeneficioEmpleado = 'ACTIVO' | 'SUSPENDIDO' | 'TERMINADO';

export interface BeneficioEmpleado {
  id_beneficio_empleado: string;
  id_empleado: number;
  id_beneficio: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  /** Montos/porcentajes como string decimal (R-CODE-4). */
  monto_personalizado: string | null;
  porcentaje_personalizado: string | null;
  estado: EstadoBeneficioEmpleado | string;
  observaciones: string | null;
  fecha_creacion?: string;
}

export interface BeneficioEmpleadoPayload {
  id_empleado: number;
  id_beneficio: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  monto_personalizado: string | null;
  porcentaje_personalizado: string | null;
  estado: string;
  observaciones: string | null;
}

// ── TipoLicencia ──────────────────────────────────────────────────────────────

export interface TipoLicencia {
  id_tipo_licencia: string;
  id_empresa?: string;
  nombre_tipo: string;
  descripcion: string | null;
  es_remunerada: boolean;
  /** Campo del backend con tilde (`dias_maximos_por_año`). */
  dias_maximos_por_año: number | null;
  requiere_aprobacion: boolean;
  activo: boolean;
  fecha_creacion?: string;
}

export interface TipoLicenciaPayload {
  id_empresa: string;
  nombre_tipo: string;
  descripcion: string | null;
  es_remunerada: boolean;
  dias_maximos_por_año: number | null;
  requiere_aprobacion: boolean;
  activo: boolean;
}

// ── LicenciaEmpleado ──────────────────────────────────────────────────────────

export type EstadoLicencia =
  | 'PENDIENTE'
  | 'APROBADA'
  | 'RECHAZADA'
  | 'EN_CURSO'
  | 'FINALIZADA'
  | 'CANCELADA';

export interface LicenciaEmpleado {
  id_licencia: string;
  id_empleado: number;
  id_tipo_licencia: string;
  fecha_inicio: string;
  fecha_fin: string;
  dias_solicitados: number;
  motivo: string;
  estado: EstadoLicencia | string;
  id_aprobador: number | null;
  fecha_aprobacion: string | null;
  observaciones_aprobacion: string | null;
  fecha_creacion?: string;
}

export interface LicenciaEmpleadoPayload {
  id_empleado: number;
  id_tipo_licencia: string;
  fecha_inicio: string;
  fecha_fin: string;
  dias_solicitados: number;
  motivo: string;
  estado: string;
}

/** Cambio de estado (aprobar/rechazar/cancelar) — PATCH parcial sobre `estado`. */
export interface CambioEstadoLicenciaPayload {
  estado: EstadoLicencia | string;
  observaciones_aprobacion?: string | null;
}

// ── beneficiosService (catálogo) ──────────────────────────────────────────────

export const beneficiosService = {
  getAll: async (): Promise<Beneficio[]> => {
    const response = await get<PaginatedResponse<Beneficio> | Beneficio[]>(`${BASE}/beneficios/`);
    return toList<Beneficio>(response);
  },

  getById: async (id: string): Promise<Beneficio> =>
    get<Beneficio>(`${BASE}/beneficios/${id}/`),

  create: async (payload: BeneficioPayload): Promise<Beneficio> =>
    post<Beneficio>(`${BASE}/beneficios/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: BeneficioPayload): Promise<Beneficio> =>
    patch<Beneficio>(`${BASE}/beneficios/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/beneficios/${id}/`);
  },
};

// ── beneficiosEmpleadoService (asignaciones) ──────────────────────────────────

export const beneficiosEmpleadoService = {
  /** Asignaciones; filtrable por empleado (client-side: el backend no filtra). */
  getAll: async (params?: { empleado?: number | string }): Promise<BeneficioEmpleado[]> => {
    const response = await get<PaginatedResponse<BeneficioEmpleado> | BeneficioEmpleado[]>(
      `${BASE}/beneficios-empleado/`,
    );
    const lista = toList<BeneficioEmpleado>(response);
    return params?.empleado !== undefined && params.empleado !== ''
      ? lista.filter((b) => String(b.id_empleado) === String(params.empleado))
      : lista;
  },

  create: async (payload: BeneficioEmpleadoPayload): Promise<BeneficioEmpleado> =>
    post<BeneficioEmpleado>(
      `${BASE}/beneficios-empleado/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: BeneficioEmpleadoPayload): Promise<BeneficioEmpleado> =>
    patch<BeneficioEmpleado>(
      `${BASE}/beneficios-empleado/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/beneficios-empleado/${id}/`);
  },
};

// ── tiposLicenciaService ──────────────────────────────────────────────────────

export const tiposLicenciaService = {
  getAll: async (): Promise<TipoLicencia[]> => {
    const response = await get<PaginatedResponse<TipoLicencia> | TipoLicencia[]>(
      `${BASE}/tipos-licencia/`,
    );
    return toList<TipoLicencia>(response);
  },

  getById: async (id: string): Promise<TipoLicencia> =>
    get<TipoLicencia>(`${BASE}/tipos-licencia/${id}/`),

  create: async (payload: TipoLicenciaPayload): Promise<TipoLicencia> =>
    post<TipoLicencia>(`${BASE}/tipos-licencia/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: TipoLicenciaPayload): Promise<TipoLicencia> =>
    patch<TipoLicencia>(
      `${BASE}/tipos-licencia/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/tipos-licencia/${id}/`);
  },
};

// ── licenciasEmpleadoService ──────────────────────────────────────────────────

export const licenciasEmpleadoService = {
  /** Licencias; filtrable por empleado y/o estado (ambos client-side). */
  getAll: async (params?: {
    empleado?: number | string;
    estado?: string;
  }): Promise<LicenciaEmpleado[]> => {
    const response = await get<PaginatedResponse<LicenciaEmpleado> | LicenciaEmpleado[]>(
      `${BASE}/licencias-empleado/`,
    );
    let lista = toList<LicenciaEmpleado>(response);
    if (params?.empleado !== undefined && params.empleado !== '') {
      lista = lista.filter((l) => String(l.id_empleado) === String(params.empleado));
    }
    if (params?.estado) {
      lista = lista.filter((l) => l.estado === params.estado);
    }
    return lista;
  },

  create: async (payload: LicenciaEmpleadoPayload): Promise<LicenciaEmpleado> =>
    post<LicenciaEmpleado>(
      `${BASE}/licencias-empleado/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: LicenciaEmpleadoPayload): Promise<LicenciaEmpleado> =>
    patch<LicenciaEmpleado>(
      `${BASE}/licencias-empleado/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  /**
   * Cambia el estado de la licencia (aprobar/rechazar/cancelar). El backend no
   * tiene acción custom: se hace con un PATCH parcial sobre `estado` (+ nota).
   */
  cambiarEstado: async (
    id: string,
    payload: CambioEstadoLicenciaPayload,
  ): Promise<LicenciaEmpleado> =>
    patch<LicenciaEmpleado>(
      `${BASE}/licencias-empleado/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/licencias-empleado/${id}/`);
  },
};
