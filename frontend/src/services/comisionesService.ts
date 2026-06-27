import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ────────────────────────────────────────────────────────────────────

/** Estado de una comisión devengada (ciclo DEVENGADA → LIQUIDADA | ANULADA). */
export type EstadoComision = 'DEVENGADA' | 'LIQUIDADA' | 'ANULADA';

/**
 * Override del porcentaje de un esquema para una categoría de producto. Los
 * porcentajes viajan como string para no perder precisión del DecimalField del
 * backend (R-CODE-4).
 */
export interface EsquemaComisionCategoria {
  id_esquema_comision_categoria: string;
  esquema: string;
  categoria: string;
  categoria_nombre?: string;
  porcentaje: string;
}

/** Payload de escritura de un override por categoría (whitelist; CTF-005). */
export interface EsquemaComisionCategoriaPayload {
  esquema: string;
  categoria: string;
  porcentaje: string;
}

/**
 * Esquema de comisión de un vendedor: porcentaje base sobre el subtotal sin
 * impuestos, con override opcional por categoría y vigencia por fechas.
 * `id_empresa` lo inyecta el backend (H-API-1), por eso no se envía al escribir.
 */
export interface EsquemaComision {
  id_esquema_comision: string;
  id_empresa?: string;
  vendedor: string;
  vendedor_username?: string;
  overrides_categoria?: EsquemaComisionCategoria[];
  porcentaje_base: string;
  vigente_desde: string | null;
  vigente_hasta: string | null;
  activo: boolean;
  fecha_creacion?: string;
}

/** Payload de escritura de un esquema (whitelist; porcentaje string; CTF-005). */
export interface EsquemaComisionPayload {
  vendedor: string;
  porcentaje_base: string;
  vigente_desde: string | null;
  vigente_hasta: string | null;
  activo: boolean;
}

/** Comisión devengada de una venta (solo lectura). Montos como string. */
export interface ComisionVenta {
  id_comision_venta: string;
  id_empresa?: string;
  vendedor: string;
  vendedor_username?: string;
  nota_venta: string;
  numero_nota?: string;
  esquema: string;
  id_moneda: string | null;
  liquidada_por: string | null;
  base_comisionable: string;
  monto: string;
  estado: EstadoComision;
  fecha_devengo: string;
  fecha_liquidacion: string | null;
  detalle_json?: unknown;
  fecha_creacion?: string;
}

/** Una fila del resumen agregado por vendedor (montos como string). */
export interface ResumenComisionVendedor {
  vendedor: string;
  vendedor_username: string;
  devengada: string;
  liquidada: string;
  anulada: string;
  cantidad: number;
}

/** Respuesta de GET /comisiones/resumen/. */
export interface ResumenComisiones {
  resultados: ResumenComisionVendedor[];
}

/** Entrada de POST /comisiones/liquidar/. */
export interface LiquidarComisionesPayload {
  vendedor: string;
  desde: string;
  hasta: string;
}

/** Resultado de POST /comisiones/liquidar/. */
export interface LiquidarComisionesResultado {
  vendedor: string;
  desde: string;
  hasta: string;
  liquidadas: number;
  monto_total: string;
}

// ── Esquemas de comisión (CRUD) ───────────────────────────────────────────────

const BASE_ESQUEMA = '/ventas/esquemas-comision';

export const esquemasComisionService = {
  getAll: async (): Promise<EsquemaComision[]> => {
    const response = await get<PaginatedResponse<EsquemaComision> | EsquemaComision[]>(
      `${BASE_ESQUEMA}/`,
    );
    return toList<EsquemaComision>(response);
  },

  create: async (payload: EsquemaComisionPayload): Promise<EsquemaComision> =>
    post<EsquemaComision>(`${BASE_ESQUEMA}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: EsquemaComisionPayload): Promise<EsquemaComision> =>
    patch<EsquemaComision>(`${BASE_ESQUEMA}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE_ESQUEMA}/${id}/`);
  },
};

// ── Overrides de comisión por categoría (CRUD, filtrable por esquema) ──────────

const BASE_CATEGORIA = '/ventas/esquemas-comision-categorias';

export const esquemasComisionCategoriaService = {
  getAll: async (params?: { esquema?: string }): Promise<EsquemaComisionCategoria[]> => {
    const qs = new URLSearchParams();
    if (params?.esquema) qs.set('esquema', params.esquema);
    const query = qs.toString();
    const response = await get<
      PaginatedResponse<EsquemaComisionCategoria> | EsquemaComisionCategoria[]
    >(`${BASE_CATEGORIA}/${query ? '?' + query : ''}`);
    const lista = toList<EsquemaComisionCategoria>(response);
    // El backend acota por empresa; reforzamos el filtro por esquema en cliente
    // para que cada esquema muestre solo sus propios overrides.
    return params?.esquema ? lista.filter((c) => c.esquema === params.esquema) : lista;
  },

  create: async (payload: EsquemaComisionCategoriaPayload): Promise<EsquemaComisionCategoria> =>
    post<EsquemaComisionCategoria>(
      `${BASE_CATEGORIA}/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: EsquemaComisionCategoriaPayload,
  ): Promise<EsquemaComisionCategoria> =>
    patch<EsquemaComisionCategoria>(
      `${BASE_CATEGORIA}/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE_CATEGORIA}/${id}/`);
  },
};

// ── Comisiones devengadas (solo lectura + resumen + liquidación) ───────────────

const BASE_COMISION = '/ventas/comisiones';

export const comisionesService = {
  getAll: async (params?: {
    vendedor?: string;
    estado?: EstadoComision | '';
    desde?: string;
    hasta?: string;
  }): Promise<ComisionVenta[]> => {
    const qs = new URLSearchParams();
    if (params?.vendedor) qs.set('vendedor', params.vendedor);
    if (params?.estado) qs.set('estado', params.estado);
    if (params?.desde) qs.set('desde', params.desde);
    if (params?.hasta) qs.set('hasta', params.hasta);
    const query = qs.toString();
    const response = await get<PaginatedResponse<ComisionVenta> | ComisionVenta[]>(
      `${BASE_COMISION}/${query ? '?' + query : ''}`,
    );
    return toList<ComisionVenta>(response);
  },

  resumen: async (params?: {
    vendedor?: string;
    estado?: EstadoComision | '';
    desde?: string;
    hasta?: string;
  }): Promise<ResumenComisiones> => {
    const qs = new URLSearchParams();
    if (params?.vendedor) qs.set('vendedor', params.vendedor);
    if (params?.estado) qs.set('estado', params.estado);
    if (params?.desde) qs.set('desde', params.desde);
    if (params?.hasta) qs.set('hasta', params.hasta);
    const query = qs.toString();
    return get<ResumenComisiones>(`${BASE_COMISION}/resumen/${query ? '?' + query : ''}`);
  },

  liquidar: async (payload: LiquidarComisionesPayload): Promise<LiquidarComisionesResultado> =>
    post<LiquidarComisionesResultado>(
      `${BASE_COMISION}/liquidar/`,
      payload as unknown as Record<string, unknown>,
    ),
};
