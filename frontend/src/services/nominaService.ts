/**
 * Servicio de Nómina — períodos, procesos LOTTT y recibos (workstream F).
 *
 * Endpoints del backend (`apps/nomina`, base /api/nomina/):
 *   GET  /nomina/procesos-nomina/                 — lista paginada de procesos
 *   GET  /nomina/procesos-nomina/{id}/            — detalle del proceso
 *   POST /nomina/procesos-nomina/                 — crea proceso (estado EN_PROCESO)
 *   POST /nomina/procesos-nomina/{id}/procesar/   — procesa la nómina LOTTT (PR #80):
 *        body opcional {"empleados": {"<id_empleado>": {"horas_extra_diurnas": "4", …}}}
 *        · 400 → NominaProcesoError (re-proceso: los recibos emitidos son inmutables)
 *        · 422 → AsientoError (contabilidad activa sin mapeo NOMINA)
 *   GET  /nomina/nominas/?id_proceso_nomina={id}  — recibos del proceso (filtro real DRF)
 *   GET  /nomina/periodos-nomina/                 — períodos de nómina
 *   POST /nomina/periodos-nomina/                 — crea período
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 *
 * GAP de idempotencia (documentado, NO resuelto aquí): `ProcesoNominaViewSet.procesar`
 * NO está decorado con `@idempotent` (apps/core/idempotency.py), así que enviar la
 * cabecera `Idempotency-Key` hoy no tendría efecto y no se envía. Mitigación real
 * del backend: el servicio toma `select_for_update()` sobre el proceso y solo
 * procesa estado EN_PROCESO — un doble submit concurrente o un replay posterior
 * recibe 400 sin duplicar recibos. Cuando el backend decore la acción, este método
 * debe enviar `Idempotency-Key` con `newIdempotencyKey()` (ver lib/idempotency.ts).
 */
import { get, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type EstadoProcesoNomina = 'EN_PROCESO' | 'COMPLETADO' | 'APROBADO' | 'CANCELADO';
export type EstadoPeriodoNomina = 'ABIERTO' | 'PROCESANDO' | 'CERRADO' | 'PAGADO';
export type TipoPeriodoNomina = 'SEMANAL' | 'QUINCENAL' | 'MENSUAL' | 'ANUAL';

export interface PeriodoNomina {
  id_periodo_nomina: string;
  id_empresa: string;
  nombre_periodo: string;
  fecha_inicio: string;
  fecha_fin: string;
  fecha_pago: string;
  tipo_periodo: TipoPeriodoNomina | string;
  estado: EstadoPeriodoNomina | string;
  observaciones: string | null;
  activo: boolean;
  fecha_creacion: string;
}

export interface ProcesoNomina {
  id_proceso_nomina: string;
  id_empresa: string;
  id_periodo_nomina: string;
  numero_proceso: string;
  fecha_proceso: string;
  total_empleados: number;
  /** Montos como string decimal (R-CODE-4). */
  total_devengado: string;
  total_deducciones: string;
  total_neto: string;
  estado: EstadoProcesoNomina | string;
  observaciones: string | null;
  fecha_creacion: string;
}

/** Recibo individual (modelo `Nomina`): un empleado dentro de un proceso. */
export interface ReciboNomina {
  id_nomina: string;
  id_proceso_nomina: string;
  id_empleado: number;
  /** Montos como string decimal (R-CODE-4). */
  sueldo_base: string;
  total_devengado: string;
  total_deducciones: string;
  total_neto: string;
  dias_trabajados: number;
  horas_trabajadas: string;
  horas_extras: string;
  estado: 'CALCULADA' | 'APROBADA' | 'PAGADA' | string;
  fecha_calculo: string;
  observaciones: string | null;
}

/**
 * Datos variables por empleado del POST procesar — claves EXACTAS de
 * `_CAMPOS_DATOS_EMPLEADO` en apps/nomina/services.py (una clave desconocida
 * es 400). Montos/horas como string decimal (R-CODE-4).
 */
export interface DatosVariablesEmpleado {
  dias_trabajados?: number;
  horas_extra_diurnas?: string;
  horas_extra_nocturnas?: string;
  /** Horas con recargo de bono nocturno (30%): el "sí" del bono son horas > 0. */
  horas_nocturnas?: string;
  otras_asignaciones?: string;
  otras_deducciones?: string;
  salario_mensual?: string;
}

export interface ProcesarNominaResponse extends ProcesoNomina {
  /** id del asiento contable NOMINA generado, o null (contabilidad inactiva). */
  asiento_contable: string | null;
  /** Presente si el asiento se omitió por falta de mapeo con contabilidad inactiva. */
  advertencia_asiento?: string;
}

export interface CrearProcesoPayload {
  id_empresa: string;
  id_periodo_nomina: string;
  numero_proceso: string;
  /** ISO datetime; al procesar el backend lo sobreescribe con el momento real. */
  fecha_proceso: string;
}

export interface CrearPeriodoPayload {
  id_empresa: string;
  nombre_periodo: string;
  fecha_inicio: string;
  fecha_fin: string;
  fecha_pago: string;
  tipo_periodo: TipoPeriodoNomina;
}

const BASE = '/nomina';

/** Máximo de páginas a recorrer en listas auxiliares (paginado fijo de 20). */
const MAX_PAGINAS = 25;

async function fetchTodas<T>(endpoint: string): Promise<T[]> {
  const sep = endpoint.includes('?') ? '&' : '?';
  const acumulado: T[] = [];
  for (let page = 1; page <= MAX_PAGINAS; page++) {
    const respuesta = await get<PaginatedResponse<T> | T[]>(`${endpoint}${sep}page=${page}`);
    acumulado.push(...toList<T>(respuesta));
    const next = Array.isArray(respuesta) ? null : (respuesta.next ?? null);
    if (!next) break;
  }
  return acumulado;
}

// ── Service ────────────────────────────────────────────────────────────────

export const nominaService = {
  /** Lista paginada de procesos (ordenados por -fecha_proceso en el backend). */
  getProcesosPaginated: async (page = 1): Promise<PaginatedResponse<ProcesoNomina>> => {
    const response = await get<PaginatedResponse<ProcesoNomina> | ProcesoNomina[]>(
      `${BASE}/procesos-nomina/?page=${page}`,
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response;
    }
    const arr = toList<ProcesoNomina>(response);
    return { count: arr.length, next: null, previous: null, results: arr };
  },

  getProceso: async (id: string): Promise<ProcesoNomina> => {
    return get<ProcesoNomina>(`${BASE}/procesos-nomina/${id}/`);
  },

  /** Crea el proceso en estado EN_PROCESO (los totales los calcula procesar). */
  crearProceso: async (payload: CrearProcesoPayload): Promise<ProcesoNomina> => {
    return post<ProcesoNomina>(
      `${BASE}/procesos-nomina/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /**
   * Procesa la nómina LOTTT del proceso (operación de dinero, atómica en el
   * backend). `empleados` mapea String(id_empleado) → datos variables; un mapa
   * vacío procesa a todos los empleados activos con los defaults del motor.
   *
   * Errores esperados: 400 (proceso no EN_PROCESO — recibos inmutables — o
   * datos inválidos) y 422 (contabilidad activa sin mapeo NOMINA). El status
   * llega en `Error.status` (ver services/api.buildError / utils/api.statusDeError).
   * Sin `Idempotency-Key`: la acción no está decorada (gap documentado arriba).
   */
  procesarProceso: async (
    id: string,
    empleados: Record<string, DatosVariablesEmpleado>,
  ): Promise<ProcesarNominaResponse> => {
    return post<ProcesarNominaResponse>(`${BASE}/procesos-nomina/${id}/procesar/`, {
      empleados,
    });
  },

  /** Recibos del proceso (filtro real `?id_proceso_nomina=` del ViewSet). */
  getRecibosProceso: async (procesoId: string): Promise<ReciboNomina[]> => {
    return fetchTodas<ReciboNomina>(
      `${BASE}/nominas/?id_proceso_nomina=${encodeURIComponent(procesoId)}`,
    );
  },

  /** Todos los períodos visibles (para selects y mapa id → nombre). */
  getPeriodos: async (): Promise<PeriodoNomina[]> => {
    return fetchTodas<PeriodoNomina>(`${BASE}/periodos-nomina/`);
  },

  crearPeriodo: async (payload: CrearPeriodoPayload): Promise<PeriodoNomina> => {
    return post<PeriodoNomina>(
      `${BASE}/periodos-nomina/`,
      payload as unknown as Record<string, unknown>,
    );
  },
};
