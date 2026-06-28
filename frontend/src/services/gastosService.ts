import { post, get, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

export type EstadoGasto =
  | 'PENDIENTE_APROBACION'
  | 'APROBADO'
  | 'RECHAZADO'
  | 'REEMBOLSADO'
  | 'CONTABILIZADO';

export type EstadoReembolso = 'PENDIENTE' | 'PAGADO' | 'ANULADO';

/**
 * Categoría de gasto (maestro). El aislamiento multi-tenant lo hace el backend
 * (get_empresas_visible + `?empresa=`). `id_cuenta_contable` es la cuenta de
 * gasto (DEUDORA) por defecto de la categoría.
 */
export interface CategoriaGasto {
  id_categoria_gasto: string;
  id_empresa: string;
  nombre_categoria: string;
  descripcion?: string | null;
  id_cuenta_contable?: string | null;
  requiere_factura?: boolean;
  activo?: boolean;
}

/**
 * Payload de escritura de CategoriaGasto: whitelist explícita de campos
 * editables (CTF-005, defensa en profundidad CWE-915).
 */
export interface CategoriaGastoPayload {
  id_empresa: string;
  nombre_categoria: string;
  descripcion: string | null;
  id_cuenta_contable: string | null;
  requiere_factura: boolean;
  activo: boolean;
}

/** Línea de imputación contable de un gasto (ExpenseLine). */
export interface DetalleGasto {
  id_detalle_gasto: string;
  id_gasto: string;
  id_cuenta_contable: string;
  descripcion?: string | null;
  monto: string;
  monto_iva?: string;
}

export interface DetalleGastoPayload {
  id_gasto: string;
  id_cuenta_contable: string;
  descripcion: string | null;
  monto: string;
  monto_iva: string;
}

/**
 * Gasto. Los montos viajan como string para no perder precisión del
 * DecimalField del backend (R-CODE-4). `estado_gasto` es read-only en el
 * serializer: solo cambia vía las acciones aprobar/rechazar (máquina de estados).
 */
export interface Gasto {
  id_gasto: string;
  id_empresa: string;
  fecha_gasto: string;
  descripcion: string;
  monto: string;
  monto_iva?: string;
  tasa_cambio?: string;
  id_moneda: string;
  id_categoria_gasto: string;
  id_proveedor?: string | null;
  id_producto?: string | null;
  tiene_factura?: boolean;
  numero_factura?: string | null;
  sin_respaldo?: boolean;
  estado_gasto: EstadoGasto;
  estado_gasto_display?: string;
  fecha_creacion?: string;
  detalles?: DetalleGasto[];
}

/**
 * Payload de escritura de Gasto: whitelist de campos editables (CTF-005). Los
 * montos viajan como string (R-CODE-4). `estado_gasto`/`sin_respaldo` NO se
 * envían: son read-only del serializer.
 */
export interface GastoPayload {
  id_empresa: string;
  fecha_gasto: string;
  descripcion: string;
  monto: string;
  monto_iva: string;
  id_moneda: string;
  id_categoria_gasto: string;
  id_proveedor: string | null;
  tiene_factura: boolean;
  numero_factura: string | null;
}

/** Reembolso de un gasto a un empleado. Montos como string (R-CODE-4). */
export interface ReembolsoGasto {
  id_reembolso: string;
  id_empresa: string;
  id_gasto: string;
  id_empleado?: string | null;
  monto_reembolso: string;
  fecha_reembolso: string;
  id_moneda: string;
  id_metodo_pago: string;
  estado_reembolso: EstadoReembolso;
  fecha_creacion?: string;
}

export interface ReembolsoGastoPayload {
  id_empresa: string;
  id_gasto: string;
  monto_reembolso: string;
  fecha_reembolso: string;
  id_moneda: string;
  id_metodo_pago: string;
  estado_reembolso: EstadoReembolso;
}

export interface ResumenCategoria {
  categoria_nombre: string;
  total_gastos: number;
  cantidad_gastos: number;
}

export interface ResumenPorCategoria {
  empresa_id?: string | null;
  resumen_por_categoria: ResumenCategoria[];
  total_general: number;
}

const BASE = '/gastos';

// ── Categorías de gasto (CRUD + activas) ──────────────────────────────────────

export const categoriasGastoService = {
  getAll: async (params?: { empresa?: string; search?: string }): Promise<CategoriaGasto[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<CategoriaGasto> | CategoriaGasto[]>(
      `${BASE}/categorias-gasto/${query ? '?' + query : ''}`,
    );
    return toList<CategoriaGasto>(response);
  },

  getById: async (id: string): Promise<CategoriaGasto> =>
    get<CategoriaGasto>(`${BASE}/categorias-gasto/${id}/`),

  activas: async (): Promise<CategoriaGasto[]> => {
    const response = await get<PaginatedResponse<CategoriaGasto> | CategoriaGasto[]>(
      `${BASE}/categorias-gasto/activas/`,
    );
    return toList<CategoriaGasto>(response);
  },

  create: async (payload: CategoriaGastoPayload): Promise<CategoriaGasto> =>
    post<CategoriaGasto>(
      `${BASE}/categorias-gasto/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: CategoriaGastoPayload): Promise<CategoriaGasto> =>
    patch<CategoriaGasto>(
      `${BASE}/categorias-gasto/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/categorias-gasto/${id}/`);
  },
};

// ── Gastos (CRUD + workflow de aprobación) ────────────────────────────────────

export const gastosService = {
  getAll: async (params?: {
    empresa?: string;
    estado?: string;
    categoria?: string;
    search?: string;
  }): Promise<Gasto[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.estado) qs.set('estado_gasto', params.estado);
    if (params?.categoria) qs.set('id_categoria_gasto', params.categoria);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<Gasto> | Gasto[]>(
      `${BASE}/gastos/${query ? '?' + query : ''}`,
    );
    return toList<Gasto>(response);
  },

  getById: async (id: string): Promise<Gasto> => get<Gasto>(`${BASE}/gastos/${id}/`),

  create: async (payload: GastoPayload): Promise<Gasto> =>
    post<Gasto>(`${BASE}/gastos/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: GastoPayload): Promise<Gasto> =>
    patch<Gasto>(`${BASE}/gastos/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/gastos/${id}/`);
  },

  aprobar: async (id: string): Promise<Gasto> =>
    post<Gasto>(`${BASE}/gastos/${id}/aprobar/`, {}),

  rechazar: async (id: string, motivo?: string): Promise<Gasto> =>
    post<Gasto>(`${BASE}/gastos/${id}/rechazar/`, motivo ? { motivo } : {}),

  resumenPorCategoria: async (empresaId?: string): Promise<ResumenPorCategoria> => {
    const qs = empresaId ? `?empresa_id=${encodeURIComponent(empresaId)}` : '';
    return get<ResumenPorCategoria>(`${BASE}/gastos/resumen_por_categoria/${qs}`);
  },

  pendientesAprobacion: async (): Promise<Gasto[]> => {
    const response = await get<PaginatedResponse<Gasto> | Gasto[]>(
      `${BASE}/gastos/pendientes_aprobacion/`,
    );
    return toList<Gasto>(response);
  },
};

// ── Detalles de gasto (líneas de imputación contable) ─────────────────────────

export const detalleGastoService = {
  getAll: async (params?: { gasto?: string }): Promise<DetalleGasto[]> => {
    const qs = params?.gasto ? `?id_gasto=${encodeURIComponent(params.gasto)}` : '';
    const response = await get<PaginatedResponse<DetalleGasto> | DetalleGasto[]>(
      `${BASE}/detalles-gasto/${qs}`,
    );
    const lista = toList<DetalleGasto>(response);
    return params?.gasto ? lista.filter((d) => d.id_gasto === params.gasto) : lista;
  },

  create: async (payload: DetalleGastoPayload): Promise<DetalleGasto> =>
    post<DetalleGasto>(`${BASE}/detalles-gasto/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: DetalleGastoPayload): Promise<DetalleGasto> =>
    patch<DetalleGasto>(
      `${BASE}/detalles-gasto/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/detalles-gasto/${id}/`);
  },
};

// ── Reembolsos de gasto (CRUD + procesar pago / anular) ───────────────────────

export const reembolsosGastoService = {
  getAll: async (params?: { empresa?: string; estado?: string }): Promise<ReembolsoGasto[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.estado) qs.set('estado_reembolso', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<ReembolsoGasto> | ReembolsoGasto[]>(
      `${BASE}/reembolsos-gasto/${query ? '?' + query : ''}`,
    );
    return toList<ReembolsoGasto>(response);
  },

  getById: async (id: string): Promise<ReembolsoGasto> =>
    get<ReembolsoGasto>(`${BASE}/reembolsos-gasto/${id}/`),

  create: async (payload: ReembolsoGastoPayload): Promise<ReembolsoGasto> =>
    post<ReembolsoGasto>(
      `${BASE}/reembolsos-gasto/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: ReembolsoGastoPayload): Promise<ReembolsoGasto> =>
    patch<ReembolsoGasto>(
      `${BASE}/reembolsos-gasto/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/reembolsos-gasto/${id}/`);
  },

  procesarPago: async (id: string): Promise<ReembolsoGasto> =>
    post<ReembolsoGasto>(`${BASE}/reembolsos-gasto/${id}/procesar_pago/`, {}),

  anular: async (id: string): Promise<ReembolsoGasto> =>
    post<ReembolsoGasto>(`${BASE}/reembolsos-gasto/${id}/anular/`, {}),

  pendientesPago: async (): Promise<ReembolsoGasto[]> => {
    const response = await get<PaginatedResponse<ReembolsoGasto> | ReembolsoGasto[]>(
      `${BASE}/reembolsos-gasto/pendientes_pago/`,
    );
    return toList<ReembolsoGasto>(response);
  },
};
