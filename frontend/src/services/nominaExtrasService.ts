/**
 * Servicio de Nómina — Conceptos (catálogo) y Nómina Extrasalarial (workstream F).
 *
 * Cubre los recursos de `apps/nomina` que hoy NO tienen pantalla (los procesos
 * de nómina regulares ya están en `nominaService.ts`):
 *
 * Backend `apps/nomina` (prefijo /api/nomina/):
 *   conceptos-nomina/                       — catálogo de devengados/deducciones (CRUD)
 *     GET conceptos-nomina/por_tipo/?tipo=  — conceptos activos de un tipo
 *     GET conceptos-nomina/devengados/      — conceptos DEVENGADO activos
 *     GET conceptos-nomina/deducciones/     — conceptos DEDUCCION activos
 *   procesos-nomina-extrasalarial/          — proceso de pagos no salariales (CRUD)
 *     POST .../{id}/procesar/               — EN_PROCESO → COMPLETADO
 *     POST .../{id}/aprobar/                — COMPLETADO → APROBADO (recibos CALCULADA → APROBADA)
 *   nominas-extrasalarial/                  — recibos extrasalariales (lista + acciones)
 *     POST .../{id}/aprobar/                — CALCULADA → APROBADA
 *     POST .../{id}/marcar_pagada/          — APROBADA → PAGADA
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 * Cada payload de escritura es una whitelist explícita (CWE-915, igual que el
 * serializer del backend).
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos: Conceptos de Nómina ───────────────────────────────────────────────

export type TipoConcepto = 'DEVENGADO' | 'DEDUCCION' | 'APORTE_PATRONAL';
export type CategoriaConcepto =
  | 'SUELDO_BASE'
  | 'HORAS_EXTRAS'
  | 'COMISION'
  | 'BONO'
  | 'VACACIONES'
  | 'PRESTACIONES'
  | 'SEGURO_SOCIAL'
  | 'IMPUESTO_RENTA'
  | 'OTROS';

/** Concepto del catálogo de nómina (un devengado/deducción/aporte configurable). */
export interface ConceptoNomina {
  id_concepto_nomina: string;
  id_empresa?: string;
  codigo_concepto: string;
  nombre_concepto: string;
  tipo_concepto: TipoConcepto | string;
  categoria: CategoriaConcepto | string;
  formula_calculo: string | null;
  es_fijo: boolean;
  /** Monto fijo como string decimal (R-CODE-4), o null si no aplica. */
  monto_fijo: string | null;
  es_porcentaje: boolean;
  /** Porcentaje como string decimal (R-CODE-4), o null si no aplica. */
  porcentaje: string | null;
  activo: boolean;
  fecha_creacion?: string;
}

/** Payload de escritura de un concepto (whitelist; id_empresa requerido al crear). */
export interface ConceptoNominaPayload {
  id_empresa: string;
  codigo_concepto: string;
  nombre_concepto: string;
  tipo_concepto: TipoConcepto | string;
  categoria: CategoriaConcepto | string;
  formula_calculo: string | null;
  es_fijo: boolean;
  monto_fijo: string | null;
  es_porcentaje: boolean;
  porcentaje: string | null;
  activo: boolean;
}

// ── Tipos: Proceso de Nómina Extrasalarial ───────────────────────────────────

export type TipoProcesoExtra =
  | 'AGUINALDO'
  | 'VACACIONES'
  | 'PRESTACIONES'
  | 'LIQUIDACION'
  | 'BONO_ESPECIAL';
export type EstadoProcesoExtra =
  | 'EN_PROCESO'
  | 'COMPLETADO'
  | 'APROBADO'
  | 'PAGADO'
  | 'CANCELADO';

/** Proceso de pagos extrasalariales (utilidades, bono vacacional, liquidación…). */
export interface ProcesoNominaExtrasalarial {
  id_proceso_extrasalarial: string;
  id_empresa?: string;
  numero_proceso: string;
  tipo_proceso: TipoProcesoExtra | string;
  fecha_proceso: string;
  fecha_corte: string;
  total_empleados: number;
  /** Monto total como string decimal (R-CODE-4). */
  total_monto: string;
  estado: EstadoProcesoExtra | string;
  observaciones: string | null;
  fecha_creacion?: string;
}

/** Payload de escritura del proceso (whitelist; id_empresa requerido al crear). */
export interface ProcesoNominaExtrasalarialPayload {
  id_empresa: string;
  numero_proceso: string;
  tipo_proceso: TipoProcesoExtra | string;
  fecha_proceso: string;
  fecha_corte: string;
  observaciones: string | null;
}

// ── Tipos: Recibo Extrasalarial ──────────────────────────────────────────────

export type EstadoNominaExtra = 'CALCULADA' | 'APROBADA' | 'PAGADA';

/** Recibo extrasalarial individual (un empleado dentro de un proceso extra). */
export interface NominaExtrasalarial {
  id_nomina_extrasalarial: string;
  id_proceso_extrasalarial: string;
  id_empleado: number;
  periodo_inicio: string;
  periodo_fin: string;
  /** Montos como string decimal (R-CODE-4). */
  salario_promedio: string;
  dias_laborados: number;
  monto_calculado: string;
  deducciones: string;
  monto_neto: string;
  estado: EstadoNominaExtra | string;
  fecha_calculo: string;
  observaciones: string | null;
}

const BASE = '/nomina';
const CONCEPTOS = `${BASE}/conceptos-nomina`;
const PROCESOS = `${BASE}/procesos-nomina-extrasalarial`;
const RECIBOS = `${BASE}/nominas-extrasalarial`;

// ── Conceptos de Nómina (catálogo, CRUD) ─────────────────────────────────────

export const conceptosNominaService = {
  /** Lista todos los conceptos (normaliza lista directa o DRF paginada). */
  getAll: async (): Promise<ConceptoNomina[]> => {
    const r = await get<PaginatedResponse<ConceptoNomina> | ConceptoNomina[]>(`${CONCEPTOS}/`);
    return toList<ConceptoNomina>(r);
  },

  /** Conceptos activos filtrados por tipo (acción `por_tipo` del backend). */
  porTipo: async (tipo: string): Promise<ConceptoNomina[]> => {
    const r = await get<PaginatedResponse<ConceptoNomina> | ConceptoNomina[]>(
      `${CONCEPTOS}/por_tipo/?tipo=${encodeURIComponent(tipo)}`,
    );
    return toList<ConceptoNomina>(r);
  },

  /** Conceptos DEVENGADO activos (acción `devengados` del backend). */
  devengados: async (): Promise<ConceptoNomina[]> => {
    const r = await get<PaginatedResponse<ConceptoNomina> | ConceptoNomina[]>(
      `${CONCEPTOS}/devengados/`,
    );
    return toList<ConceptoNomina>(r);
  },

  /** Conceptos DEDUCCION activos (acción `deducciones` del backend). */
  deducciones: async (): Promise<ConceptoNomina[]> => {
    const r = await get<PaginatedResponse<ConceptoNomina> | ConceptoNomina[]>(
      `${CONCEPTOS}/deducciones/`,
    );
    return toList<ConceptoNomina>(r);
  },

  getById: async (id: string): Promise<ConceptoNomina> =>
    get<ConceptoNomina>(`${CONCEPTOS}/${id}/`),

  create: async (payload: ConceptoNominaPayload): Promise<ConceptoNomina> =>
    post<ConceptoNomina>(`${CONCEPTOS}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ConceptoNominaPayload): Promise<ConceptoNomina> =>
    patch<ConceptoNomina>(`${CONCEPTOS}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${CONCEPTOS}/${id}/`);
  },
};

// ── Procesos de Nómina Extrasalarial (CRUD + workflow) ───────────────────────

export const procesosNominaExtrasalarialService = {
  /** Lista todos los procesos (normaliza lista directa o DRF paginada). */
  getAll: async (): Promise<ProcesoNominaExtrasalarial[]> => {
    const r = await get<PaginatedResponse<ProcesoNominaExtrasalarial> | ProcesoNominaExtrasalarial[]>(
      `${PROCESOS}/`,
    );
    return toList<ProcesoNominaExtrasalarial>(r);
  },

  getById: async (id: string): Promise<ProcesoNominaExtrasalarial> =>
    get<ProcesoNominaExtrasalarial>(`${PROCESOS}/${id}/`),

  create: async (
    payload: ProcesoNominaExtrasalarialPayload,
  ): Promise<ProcesoNominaExtrasalarial> =>
    post<ProcesoNominaExtrasalarial>(`${PROCESOS}/`, payload as unknown as Record<string, unknown>),

  update: async (
    id: string,
    payload: ProcesoNominaExtrasalarialPayload,
  ): Promise<ProcesoNominaExtrasalarial> =>
    patch<ProcesoNominaExtrasalarial>(
      `${PROCESOS}/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${PROCESOS}/${id}/`);
  },

  /** Procesa el proceso (POST .../procesar/): EN_PROCESO → COMPLETADO. 400 en otro estado. */
  procesar: async (id: string): Promise<ProcesoNominaExtrasalarial> =>
    post<ProcesoNominaExtrasalarial>(`${PROCESOS}/${id}/procesar/`, {}),

  /** Aprueba el proceso (POST .../aprobar/): COMPLETADO → APROBADO. 400 en otro estado. */
  aprobar: async (id: string): Promise<ProcesoNominaExtrasalarial> =>
    post<ProcesoNominaExtrasalarial>(`${PROCESOS}/${id}/aprobar/`, {}),
};

// ── Recibos Extrasalariales (lista + acciones) ───────────────────────────────

export const nominasExtrasalarialService = {
  /**
   * Recibos extrasalariales, opcionalmente filtrados por proceso (filtro real
   * `?id_proceso_extrasalarial=` del ViewSet). Normaliza lista directa/paginada.
   */
  getAll: async (params?: { proceso?: string }): Promise<NominaExtrasalarial[]> => {
    const qs = params?.proceso
      ? `?id_proceso_extrasalarial=${encodeURIComponent(params.proceso)}`
      : '';
    const r = await get<PaginatedResponse<NominaExtrasalarial> | NominaExtrasalarial[]>(
      `${RECIBOS}/${qs}`,
    );
    return toList<NominaExtrasalarial>(r);
  },

  /** Aprueba un recibo (POST .../aprobar/): CALCULADA → APROBADA. 400 en otro estado. */
  aprobar: async (id: string): Promise<NominaExtrasalarial> =>
    post<NominaExtrasalarial>(`${RECIBOS}/${id}/aprobar/`, {}),

  /** Marca un recibo como pagado (POST .../marcar_pagada/): APROBADA → PAGADA. 400 en otro estado. */
  marcarPagada: async (id: string): Promise<NominaExtrasalarial> =>
    post<NominaExtrasalarial>(`${RECIBOS}/${id}/marcar_pagada/`, {}),
};
