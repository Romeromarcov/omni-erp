/**
 * Servicio de Contabilidad (workstream F) — plan de cuentas, libro de asientos
 * y mapeos contables (tipo de asiento automático → cuentas debe/haber).
 *
 * Endpoints del backend (`apps/contabilidad`):
 *   GET/POST /contabilidad/plan-cuentas/
 *   GET      /contabilidad/asientos-contables/?estado_asiento=&fecha_asiento=
 *   GET      /contabilidad/asientos-contables/{id}/
 *   GET      /contabilidad/detalles-asiento/?id_asiento=
 *   GET/POST /contabilidad/mapeos-contables/  ·  PATCH /{id}/
 *   GET      /contabilidad/mapeos-contables/tipos-asiento/
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { get, patch, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type TipoCuenta = 'ACTIVO' | 'PASIVO' | 'PATRIMONIO' | 'INGRESO' | 'GASTO' | 'COSTO';
export type Naturaleza = 'DEUDORA' | 'ACREEDORA';
export type EstadoAsiento = 'BORRADOR' | 'APROBADO' | 'ANULADO';

export interface CuentaContable {
  id_cuenta_contable: string;
  id_empresa: string;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: TipoCuenta | string;
  naturaleza: Naturaleza | string;
  id_cuenta_padre: string | null;
  nivel: number;
  activo: boolean;
  fecha_creacion: string;
}

export interface CrearCuentaPayload {
  id_empresa: string;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: string;
  naturaleza: string;
  id_cuenta_padre?: string | null;
  nivel: number;
}

export interface DetalleAsiento {
  id_detalle_asiento: string;
  id_asiento: string;
  id_cuenta_contable: string;
  /** Montos como string decimal (R-CODE-4). */
  debe: string;
  haber: string;
  descripcion_detalle: string | null;
  fecha_creacion: string;
}

export interface AsientoContable {
  id_asiento: string;
  id_empresa: string;
  fecha_asiento: string;
  numero_asiento: string;
  descripcion: string;
  id_documento_origen: string | null;
  nombre_modelo_origen: string | null;
  estado_asiento: EstadoAsiento | string;
  fecha_creacion: string;
  /** Líneas embebidas en el detalle del asiento. */
  detalles?: DetalleAsiento[];
}

export interface MapeoContable {
  id_mapeo: string;
  id_empresa: string;
  tipo_asiento: string;
  tipo_asiento_display?: string;
  cuenta_debe: string;
  cuenta_debe_nombre?: string;
  cuenta_haber: string;
  cuenta_haber_nombre?: string;
  descripcion_plantilla: string;
  activo: boolean;
  fecha_creacion: string;
}

export interface MapeoContablePayload {
  id_empresa: string;
  tipo_asiento: string;
  cuenta_debe: string;
  cuenta_haber: string;
  descripcion_plantilla?: string;
  activo?: boolean;
}

export interface TipoAsientoChoice {
  value: string;
  label: string;
}

export interface AsientosFiltros {
  estado?: string;
  fechaDesde?: string;
  fechaHasta?: string;
}

const BASE = '/contabilidad';

function paginada<T>(response: PaginatedResponse<T> | T[]): PaginatedResponse<T> {
  if (response && typeof response === 'object' && 'results' in response) return response;
  const arr = toList<T>(response);
  return { count: arr.length, next: null, previous: null, results: arr };
}

// ── Service ────────────────────────────────────────────────────────────────

export const contabilidadService = {
  /** Plan de cuentas completo (orden por código → permite armar la jerarquía). */
  getPlanCuentas: async (): Promise<CuentaContable[]> => {
    const response = await get<CuentaContable[] | PaginatedResponse<CuentaContable>>(
      `${BASE}/plan-cuentas/?page_size=1000`,
    );
    return toList<CuentaContable>(response);
  },

  crearCuenta: async (payload: CrearCuentaPayload): Promise<CuentaContable> => {
    return post<CuentaContable>(`${BASE}/plan-cuentas/`, payload as unknown as Record<string, unknown>);
  },

  /** Libro de asientos paginado con filtros por estado y rango de fechas. */
  getAsientosPaginated: async (
    page = 1,
    pageSize = 20,
    filtros: AsientosFiltros = {},
  ): Promise<PaginatedResponse<AsientoContable>> => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filtros.estado) params.set('estado_asiento', filtros.estado);
    if (filtros.fechaDesde) params.set('fecha_asiento__gte', filtros.fechaDesde);
    if (filtros.fechaHasta) params.set('fecha_asiento__lte', filtros.fechaHasta);
    const response = await get<PaginatedResponse<AsientoContable> | AsientoContable[]>(
      `${BASE}/asientos-contables/?${params.toString()}`,
    );
    return paginada(response);
  },

  getAsiento: async (id: string): Promise<AsientoContable> => {
    return get<AsientoContable>(`${BASE}/asientos-contables/${id}/`);
  },

  /** Líneas debe/haber de un asiento (fallback si el detalle no las embebe). */
  getDetallesAsiento: async (asientoId: string): Promise<DetalleAsiento[]> => {
    const response = await get<DetalleAsiento[] | PaginatedResponse<DetalleAsiento>>(
      `${BASE}/detalles-asiento/?id_asiento=${asientoId}`,
    );
    return toList<DetalleAsiento>(response);
  },

  // ── Mapeos contables ─────────────────────────────────────────────────────

  getMapeos: async (): Promise<MapeoContable[]> => {
    const response = await get<MapeoContable[] | PaginatedResponse<MapeoContable>>(
      `${BASE}/mapeos-contables/`,
    );
    return toList<MapeoContable>(response);
  },

  getTiposAsiento: async (): Promise<TipoAsientoChoice[]> => {
    const response = await get<TipoAsientoChoice[]>(`${BASE}/mapeos-contables/tipos-asiento/`);
    return toList<TipoAsientoChoice>(response);
  },

  crearMapeo: async (payload: MapeoContablePayload): Promise<MapeoContable> => {
    return post<MapeoContable>(`${BASE}/mapeos-contables/`, payload as unknown as Record<string, unknown>);
  },

  actualizarMapeo: async (id: string, payload: Partial<MapeoContablePayload>): Promise<MapeoContable> => {
    return patch<MapeoContable>(`${BASE}/mapeos-contables/${id}/`, payload as Record<string, unknown>);
  },
};
