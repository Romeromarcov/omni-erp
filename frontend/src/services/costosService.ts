/**
 * Servicio de Costos (costeo de producción) — complementa a Manufactura.
 *
 * Endpoints del backend (`apps/costos`, prefijo `/api/costos/`):
 *   /costos/costos-produccion/          — costo real por orden de producción
 *   /costos/costos-estandar-producto/   — costo estándar por producto
 *   /costos/analisis-variacion-costo/   — variación real vs estándar
 *
 * CRUD estándar (sin acciones custom). El aislamiento multi-tenant lo hace el
 * backend (get_empresas_visible + `?empresa=`). Todos los montos viajan como
 * STRING decimal (R-CODE-4) — nunca number — para no perder precisión del
 * DecimalField. Los payloads son whitelist explícita de campos editables
 * (CTF-005, defensa en profundidad CWE-915).
 */
import { post, get, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos comunes ──────────────────────────────────────────────────────────

/** Tipo de costo (común a las tres entidades). */
export type TipoCosto =
  | 'MATERIAL_DIRECTO'
  | 'MANO_OBRA_DIRECTA'
  | 'COSTOS_INDIRECTOS'
  | 'OVERHEAD';

/** Resultado del análisis de variación. */
export type TipoVariacion = 'FAVORABLE' | 'DESFAVORABLE' | 'NEUTRO';

// ── Costo de producción (costo real) ─────────────────────────────────────────

export interface CostoProduccion {
  id_costo_produccion: string;
  id_empresa: string;
  id_orden_produccion: string;
  tipo_costo: TipoCosto;
  costo_unitario: string;
  cantidad: string;
  costo_total: string;
  id_moneda: string;
  fecha_calculo: string;
  observaciones?: string | null;
  activo?: boolean;
  fecha_creacion?: string;
}

export interface CostoProduccionPayload {
  id_empresa: string;
  id_orden_produccion: string;
  tipo_costo: TipoCosto;
  costo_unitario: string;
  cantidad: string;
  costo_total: string;
  id_moneda: string;
  fecha_calculo: string;
  observaciones: string | null;
  activo: boolean;
}

// ── Costo estándar de producto ───────────────────────────────────────────────

export interface CostoEstandarProducto {
  id_costo_estandar: string;
  id_empresa: string;
  id_producto: string;
  tipo_costo: TipoCosto;
  costo_unitario_estandar: string;
  id_moneda: string;
  fecha_vigencia_desde: string;
  fecha_vigencia_hasta?: string | null;
  activo?: boolean;
  fecha_creacion?: string;
}

export interface CostoEstandarProductoPayload {
  id_empresa: string;
  id_producto: string;
  tipo_costo: TipoCosto;
  costo_unitario_estandar: string;
  id_moneda: string;
  fecha_vigencia_desde: string;
  fecha_vigencia_hasta: string | null;
  activo: boolean;
}

// ── Análisis de variación de costo ───────────────────────────────────────────

export interface AnalisisVariacionCosto {
  id_analisis_variacion: string;
  id_empresa: string;
  id_orden_produccion: string;
  id_producto: string;
  tipo_costo: TipoCosto;
  costo_estandar: string;
  costo_real: string;
  variacion_cantidad: string;
  variacion_precio: string;
  variacion_total: string;
  porcentaje_variacion: string;
  tipo_variacion: TipoVariacion;
  fecha_analisis: string;
  observaciones?: string | null;
  activo?: boolean;
  fecha_creacion?: string;
}

export interface AnalisisVariacionCostoPayload {
  id_empresa: string;
  id_orden_produccion: string;
  id_producto: string;
  tipo_costo: TipoCosto;
  costo_estandar: string;
  costo_real: string;
  variacion_cantidad: string;
  variacion_precio: string;
  variacion_total: string;
  porcentaje_variacion: string;
  tipo_variacion: TipoVariacion;
  fecha_analisis: string;
  observaciones: string | null;
  activo: boolean;
}

const BASE = '/costos';

// ── Costo de producción (CRUD) ───────────────────────────────────────────────

export const costosProduccionService = {
  getAll: async (params?: {
    empresa?: string;
    orden?: string;
  }): Promise<CostoProduccion[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.orden) qs.set('id_orden_produccion', params.orden);
    const query = qs.toString();
    const response = await get<PaginatedResponse<CostoProduccion> | CostoProduccion[]>(
      `${BASE}/costos-produccion/${query ? '?' + query : ''}`,
    );
    return toList<CostoProduccion>(response);
  },

  getById: async (id: string): Promise<CostoProduccion> =>
    get<CostoProduccion>(`${BASE}/costos-produccion/${id}/`),

  create: async (payload: CostoProduccionPayload): Promise<CostoProduccion> =>
    post<CostoProduccion>(
      `${BASE}/costos-produccion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: CostoProduccionPayload): Promise<CostoProduccion> =>
    patch<CostoProduccion>(
      `${BASE}/costos-produccion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/costos-produccion/${id}/`);
  },
};

// ── Costo estándar de producto (CRUD) ────────────────────────────────────────

export const costosEstandarProductoService = {
  getAll: async (params?: {
    empresa?: string;
    producto?: string;
  }): Promise<CostoEstandarProducto[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.producto) qs.set('id_producto', params.producto);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<CostoEstandarProducto> | CostoEstandarProducto[]
    >(`${BASE}/costos-estandar-producto/${query ? '?' + query : ''}`);
    return toList<CostoEstandarProducto>(response);
  },

  getById: async (id: string): Promise<CostoEstandarProducto> =>
    get<CostoEstandarProducto>(`${BASE}/costos-estandar-producto/${id}/`),

  create: async (payload: CostoEstandarProductoPayload): Promise<CostoEstandarProducto> =>
    post<CostoEstandarProducto>(
      `${BASE}/costos-estandar-producto/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: CostoEstandarProductoPayload,
  ): Promise<CostoEstandarProducto> =>
    patch<CostoEstandarProducto>(
      `${BASE}/costos-estandar-producto/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/costos-estandar-producto/${id}/`);
  },
};

// ── Análisis de variación de costo (CRUD) ────────────────────────────────────

export const analisisVariacionService = {
  getAll: async (params?: {
    empresa?: string;
    producto?: string;
    orden?: string;
  }): Promise<AnalisisVariacionCosto[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.producto) qs.set('id_producto', params.producto);
    if (params?.orden) qs.set('id_orden_produccion', params.orden);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<AnalisisVariacionCosto> | AnalisisVariacionCosto[]
    >(`${BASE}/analisis-variacion-costo/${query ? '?' + query : ''}`);
    return toList<AnalisisVariacionCosto>(response);
  },

  getById: async (id: string): Promise<AnalisisVariacionCosto> =>
    get<AnalisisVariacionCosto>(`${BASE}/analisis-variacion-costo/${id}/`),

  create: async (payload: AnalisisVariacionCostoPayload): Promise<AnalisisVariacionCosto> =>
    post<AnalisisVariacionCosto>(
      `${BASE}/analisis-variacion-costo/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: AnalisisVariacionCostoPayload,
  ): Promise<AnalisisVariacionCosto> =>
    patch<AnalisisVariacionCosto>(
      `${BASE}/analisis-variacion-costo/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/analisis-variacion-costo/${id}/`);
  },
};
