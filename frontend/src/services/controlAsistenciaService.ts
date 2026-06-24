/**
 * Servicio de Control de Asistencia — horarios de trabajo, asignaciones de
 * horario, registros de marcaje y resúmenes diarios con flujo de revisión.
 *
 * Endpoints del backend (`apps/control_asistencia`, base /api/control-asistencia/):
 *   horarios-trabajo/            — CRUD + GET activos/ + POST {id}/desactivar/
 *   asignaciones-horario/        — CRUD + GET activas/ + GET por_empleado/ + POST {id}/finalizar/
 *   registros-asistencia/        — CRUD + POST marcar_asistencia/ + GET por_empleado_fecha/ + GET hoy/
 *   resumenes-asistencia-diario/ — CRUD + POST generar_resumen_diario/ + POST {id}/aprobar/
 *                                  + GET pendientes_revision/ + GET reporte_mensual/
 *
 * Aislamiento multi-tenant (R-CODE-1): lo hace el backend vía
 * get_empresas_visible. Las horas/decimales viajan como string para no perder
 * precisión del DecimalField del backend (R-CODE-4).
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

export type TipoMarcado = 'ENTRADA' | 'SALIDA' | 'INICIO_DESCANSO' | 'FIN_DESCANSO';

export type MetodoMarcado = 'BIOMETRICO' | 'MANUAL' | 'WEB' | 'MOVIL' | 'GPS';

export type EstadoRevision = 'PENDIENTE' | 'REVISADO' | 'APROBADO';

/** Horario de trabajo (plantilla de jornada del tenant). */
export interface HorarioTrabajo {
  id_horario: string;
  id_empresa: string;
  nombre_horario: string;
  descripcion?: string | null;
  dias_semana_json?: unknown;
  total_horas_semanales: string;
  activo: boolean;
}

/**
 * Payload de escritura de HorarioTrabajo: whitelist explícita de campos
 * editables (CTF-005, defensa en profundidad CWE-915). `activo` NO se envía: lo
 * gobierna la acción desactivar/. `total_horas_semanales` como string (R-CODE-4).
 */
export interface HorarioTrabajoPayload {
  id_empresa: string;
  nombre_horario: string;
  descripcion: string | null;
  dias_semana_json: unknown;
  total_horas_semanales: string;
}

/** Asignación de un horario a un empleado (con vigencia). */
export interface AsignacionHorario {
  id_asignacion_horario: string;
  id_empleado: number | null;
  id_horario: string;
  fecha_inicio: string;
  fecha_fin?: string | null;
  activo: boolean;
}

/** Payload de escritura de AsignacionHorario (whitelist, CTF-005). */
export interface AsignacionHorarioPayload {
  id_empleado: number | null;
  id_horario: string;
  fecha_inicio: string;
  fecha_fin: string | null;
}

/** Registro de marcaje de asistencia (entrada/salida/descanso). */
export interface RegistroAsistencia {
  id_registro_asistencia: string;
  id_empleado: number | null;
  fecha_hora_marcado: string;
  tipo_marcado: TipoMarcado;
  metodo_marcado: MetodoMarcado;
  ubicacion_gps_json?: unknown;
  observaciones?: string | null;
  fecha_creacion?: string;
}

/** Payload de escritura (CRUD) de RegistroAsistencia (whitelist, CTF-005). */
export interface RegistroAsistenciaPayload {
  id_empleado: number | null;
  fecha_hora_marcado: string;
  tipo_marcado: TipoMarcado;
  metodo_marcado: MetodoMarcado;
  observaciones: string | null;
}

/**
 * Payload de la acción marcar_asistencia/. El backend usa `empleado_id`
 * (no `id_empleado`) y crea el registro con `fecha_hora_marcado=now()`.
 * `metodo_marcado` por defecto 'WEB' si no se envía.
 */
export interface MarcarAsistenciaPayload {
  empleado_id: number | string;
  tipo_marcado: TipoMarcado;
  metodo_marcado?: MetodoMarcado;
  observaciones?: string | null;
}

/** Resumen diario de asistencia con flujo de revisión. */
export interface ResumenAsistenciaDiario {
  id_resumen_diario: string;
  id_empleado: number | null;
  fecha: string;
  hora_entrada_real?: string | null;
  hora_salida_real?: string | null;
  horas_trabajadas_netas: string;
  horas_extras_normal: string;
  horas_extras_feriado: string;
  minutos_tardanza: number;
  es_ausencia: boolean;
  id_licencia_asociada?: string | null;
  estado_revision: EstadoRevision;
  observaciones_supervisor?: string | null;
  fecha_creacion?: string;
}

/** Respuesta de la acción generar_resumen_diario/. */
export interface GenerarResumenResponse {
  mensaje: string;
  fecha: string;
}

const BASE = '/control-asistencia';

// ── Horarios de trabajo (CRUD + activos + desactivar) ─────────────────────────

export const horariosTrabajoService = {
  getAll: async (params?: { empresa?: string; activo?: boolean; search?: string }): Promise<
    HorarioTrabajo[]
  > => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('id_empresa', params.empresa);
    if (params?.activo !== undefined) qs.set('activo', String(params.activo));
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<HorarioTrabajo> | HorarioTrabajo[]>(
      `${BASE}/horarios-trabajo/${query ? '?' + query : ''}`,
    );
    return toList<HorarioTrabajo>(response);
  },

  getById: async (id: string): Promise<HorarioTrabajo> =>
    get<HorarioTrabajo>(`${BASE}/horarios-trabajo/${id}/`),

  activos: async (): Promise<HorarioTrabajo[]> => {
    const response = await get<PaginatedResponse<HorarioTrabajo> | HorarioTrabajo[]>(
      `${BASE}/horarios-trabajo/activos/`,
    );
    return toList<HorarioTrabajo>(response);
  },

  create: async (payload: HorarioTrabajoPayload): Promise<HorarioTrabajo> =>
    post<HorarioTrabajo>(
      `${BASE}/horarios-trabajo/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: HorarioTrabajoPayload): Promise<HorarioTrabajo> =>
    patch<HorarioTrabajo>(
      `${BASE}/horarios-trabajo/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/horarios-trabajo/${id}/`);
  },

  desactivar: async (id: string): Promise<HorarioTrabajo> =>
    post<HorarioTrabajo>(`${BASE}/horarios-trabajo/${id}/desactivar/`, {}),
};

// ── Asignaciones de horario (CRUD + activas + por empleado + finalizar) ───────

export const asignacionesHorarioService = {
  getAll: async (params?: {
    empleado?: number | string;
    horario?: string;
    activo?: boolean;
  }): Promise<AsignacionHorario[]> => {
    const qs = new URLSearchParams();
    if (params?.empleado !== undefined && params.empleado !== '')
      qs.set('id_empleado', String(params.empleado));
    if (params?.horario) qs.set('id_horario', params.horario);
    if (params?.activo !== undefined) qs.set('activo', String(params.activo));
    const query = qs.toString();
    const response = await get<PaginatedResponse<AsignacionHorario> | AsignacionHorario[]>(
      `${BASE}/asignaciones-horario/${query ? '?' + query : ''}`,
    );
    return toList<AsignacionHorario>(response);
  },

  getById: async (id: string): Promise<AsignacionHorario> =>
    get<AsignacionHorario>(`${BASE}/asignaciones-horario/${id}/`),

  activas: async (empleadoId?: number | string): Promise<AsignacionHorario[]> => {
    const qs =
      empleadoId !== undefined && empleadoId !== ''
        ? `?empleado_id=${encodeURIComponent(String(empleadoId))}`
        : '';
    const response = await get<PaginatedResponse<AsignacionHorario> | AsignacionHorario[]>(
      `${BASE}/asignaciones-horario/activas/${qs}`,
    );
    return toList<AsignacionHorario>(response);
  },

  porEmpleado: async (empleadoId: number | string): Promise<AsignacionHorario[]> => {
    const response = await get<PaginatedResponse<AsignacionHorario> | AsignacionHorario[]>(
      `${BASE}/asignaciones-horario/por_empleado/?empleado_id=${encodeURIComponent(
        String(empleadoId),
      )}`,
    );
    return toList<AsignacionHorario>(response);
  },

  create: async (payload: AsignacionHorarioPayload): Promise<AsignacionHorario> =>
    post<AsignacionHorario>(
      `${BASE}/asignaciones-horario/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: AsignacionHorarioPayload): Promise<AsignacionHorario> =>
    patch<AsignacionHorario>(
      `${BASE}/asignaciones-horario/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/asignaciones-horario/${id}/`);
  },

  /** Finaliza la asignación (activo=false). `fecha_fin` opcional (backend usa hoy). */
  finalizar: async (id: string, fechaFin?: string | null): Promise<AsignacionHorario> =>
    post<AsignacionHorario>(
      `${BASE}/asignaciones-horario/${id}/finalizar/`,
      fechaFin ? { fecha_fin: fechaFin } : {},
    ),
};

// ── Registros de asistencia (CRUD + marcaje + por empleado/fecha + hoy) ───────

export const registrosAsistenciaService = {
  getAll: async (params?: {
    empleado?: number | string;
    tipo?: string;
    metodo?: string;
  }): Promise<RegistroAsistencia[]> => {
    const qs = new URLSearchParams();
    if (params?.empleado !== undefined && params.empleado !== '')
      qs.set('id_empleado', String(params.empleado));
    if (params?.tipo) qs.set('tipo_marcado', params.tipo);
    if (params?.metodo) qs.set('metodo_marcado', params.metodo);
    const query = qs.toString();
    const response = await get<PaginatedResponse<RegistroAsistencia> | RegistroAsistencia[]>(
      `${BASE}/registros-asistencia/${query ? '?' + query : ''}`,
    );
    return toList<RegistroAsistencia>(response);
  },

  getById: async (id: string): Promise<RegistroAsistencia> =>
    get<RegistroAsistencia>(`${BASE}/registros-asistencia/${id}/`),

  create: async (payload: RegistroAsistenciaPayload): Promise<RegistroAsistencia> =>
    post<RegistroAsistencia>(
      `${BASE}/registros-asistencia/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: RegistroAsistenciaPayload): Promise<RegistroAsistencia> =>
    patch<RegistroAsistencia>(
      `${BASE}/registros-asistencia/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/registros-asistencia/${id}/`);
  },

  /** Marcaje de asistencia: el backend pone `fecha_hora_marcado=now()`. */
  marcarAsistencia: async (payload: MarcarAsistenciaPayload): Promise<RegistroAsistencia> => {
    const body: Record<string, unknown> = {
      empleado_id: payload.empleado_id,
      tipo_marcado: payload.tipo_marcado,
    };
    if (payload.metodo_marcado) body.metodo_marcado = payload.metodo_marcado;
    if (payload.observaciones) body.observaciones = payload.observaciones;
    return post<RegistroAsistencia>(`${BASE}/registros-asistencia/marcar_asistencia/`, body);
  },

  porEmpleadoFecha: async (params: {
    empleado: number | string;
    fechaInicio?: string;
    fechaFin?: string;
  }): Promise<RegistroAsistencia[]> => {
    const qs = new URLSearchParams();
    qs.set('empleado_id', String(params.empleado));
    if (params.fechaInicio) qs.set('fecha_inicio', params.fechaInicio);
    if (params.fechaFin) qs.set('fecha_fin', params.fechaFin);
    const response = await get<PaginatedResponse<RegistroAsistencia> | RegistroAsistencia[]>(
      `${BASE}/registros-asistencia/por_empleado_fecha/?${qs.toString()}`,
    );
    return toList<RegistroAsistencia>(response);
  },

  hoy: async (empleadoId?: number | string): Promise<RegistroAsistencia[]> => {
    const qs =
      empleadoId !== undefined && empleadoId !== ''
        ? `?empleado_id=${encodeURIComponent(String(empleadoId))}`
        : '';
    const response = await get<PaginatedResponse<RegistroAsistencia> | RegistroAsistencia[]>(
      `${BASE}/registros-asistencia/hoy/${qs}`,
    );
    return toList<RegistroAsistencia>(response);
  },
};

// ── Resúmenes diarios (CRUD + generar + aprobar + pendientes + reporte) ───────

export const resumenesAsistenciaService = {
  getAll: async (params?: {
    empleado?: number | string;
    fecha?: string;
    estado?: string;
    ausencia?: boolean;
  }): Promise<ResumenAsistenciaDiario[]> => {
    const qs = new URLSearchParams();
    if (params?.empleado !== undefined && params.empleado !== '')
      qs.set('id_empleado', String(params.empleado));
    if (params?.fecha) qs.set('fecha', params.fecha);
    if (params?.estado) qs.set('estado_revision', params.estado);
    if (params?.ausencia !== undefined) qs.set('es_ausencia', String(params.ausencia));
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<ResumenAsistenciaDiario> | ResumenAsistenciaDiario[]
    >(`${BASE}/resumenes-asistencia-diario/${query ? '?' + query : ''}`);
    return toList<ResumenAsistenciaDiario>(response);
  },

  getById: async (id: string): Promise<ResumenAsistenciaDiario> =>
    get<ResumenAsistenciaDiario>(`${BASE}/resumenes-asistencia-diario/${id}/`),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/resumenes-asistencia-diario/${id}/`);
  },

  /** Genera resúmenes diarios. Sin `fecha` el backend usa hoy. */
  generarResumenDiario: async (params?: {
    fecha?: string;
    empleadoId?: number | string;
  }): Promise<GenerarResumenResponse> => {
    const body: Record<string, unknown> = {};
    if (params?.fecha) body.fecha = params.fecha;
    if (params?.empleadoId !== undefined && params.empleadoId !== '')
      body.empleado_id = params.empleadoId;
    return post<GenerarResumenResponse>(
      `${BASE}/resumenes-asistencia-diario/generar_resumen_diario/`,
      body,
    );
  },

  /** Aprueba el resumen (PENDIENTE/REVISADO → APROBADO). */
  aprobar: async (id: string, observaciones?: string): Promise<ResumenAsistenciaDiario> =>
    post<ResumenAsistenciaDiario>(
      `${BASE}/resumenes-asistencia-diario/${id}/aprobar/`,
      observaciones ? { observaciones } : {},
    ),

  pendientesRevision: async (params?: {
    empleado?: number | string;
    fechaDesde?: string;
    fechaHasta?: string;
  }): Promise<ResumenAsistenciaDiario[]> => {
    const qs = new URLSearchParams();
    if (params?.empleado !== undefined && params.empleado !== '')
      qs.set('empleado_id', String(params.empleado));
    if (params?.fechaDesde) qs.set('fecha_desde', params.fechaDesde);
    if (params?.fechaHasta) qs.set('fecha_hasta', params.fechaHasta);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<ResumenAsistenciaDiario> | ResumenAsistenciaDiario[]
    >(`${BASE}/resumenes-asistencia-diario/pendientes_revision/${query ? '?' + query : ''}`);
    return toList<ResumenAsistenciaDiario>(response);
  },
};
