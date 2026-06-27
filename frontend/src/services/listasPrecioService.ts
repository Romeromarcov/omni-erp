import { get, post, patch, del, postForm } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

/**
 * Lista de precios de ventas. Cabecera con su moneda; los precios concretos por
 * producto viven en DetallePrecio. La lista con `es_referencia=true` es la
 * "Lista 1": precio base visible en todos los documentos CxC.
 */
export interface ListaPrecio {
  id_lista: string;
  id_empresa?: string;
  id_moneda: string;
  nombre: string;
  codigo: string;
  es_referencia: boolean;
  activo: boolean;
  fecha_creacion?: string;
}

/**
 * Payload de escritura de ListaPrecio: whitelist explícita de campos editables
 * (CTF-005, defensa en profundidad CWE-915). `id_empresa` lo inyecta el backend
 * (H-API-1), por eso no se envía.
 */
export interface ListaPrecioPayload {
  id_moneda: string;
  nombre: string;
  codigo: string;
  es_referencia: boolean;
  activo: boolean;
}

/**
 * Precio de un producto dentro de una lista. Los montos viajan como string para
 * no perder precisión del DecimalField del backend (R-CODE-4).
 */
export interface DetallePrecio {
  id_detalle: string;
  id_lista: string;
  id_producto: string;
  precio: string;
  precio_minimo: string;
  vigente_desde: string | null;
  vigente_hasta: string | null;
  activo: boolean;
}

/** Payload de escritura de DetallePrecio (whitelist; precios como string). */
export interface DetallePrecioPayload {
  id_lista: string;
  id_producto: string;
  precio: string;
  precio_minimo: string;
  vigente_desde: string | null;
  vigente_hasta: string | null;
  activo: boolean;
}

/** Resultado de la importación masiva de precios desde CSV. */
export interface ImportarMasivoResultado {
  lista: string;
  creados: number;
  actualizados: number;
  errores: { fila: number; error: string }[];
  total_errores: number;
}

// ── Listas de precio (CRUD + importación masiva CSV) ─────────────────────────

const BASE = '/ventas/listas-precio';

export const listasPrecioService = {
  getAll: async (params?: { activo?: boolean; search?: string }): Promise<ListaPrecio[]> => {
    const qs = new URLSearchParams();
    if (params?.activo !== undefined) qs.set('activo', String(params.activo));
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<ListaPrecio> | ListaPrecio[]>(
      `${BASE}/${query ? '?' + query : ''}`,
    );
    return toList<ListaPrecio>(response);
  },

  getById: async (id: string): Promise<ListaPrecio> => {
    return get<ListaPrecio>(`${BASE}/${id}/`);
  },

  create: async (payload: ListaPrecioPayload): Promise<ListaPrecio> =>
    post<ListaPrecio>(`${BASE}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ListaPrecioPayload): Promise<ListaPrecio> =>
    patch<ListaPrecio>(`${BASE}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/${id}/`);
  },

  /**
   * Importa precios masivamente desde un CSV. El backend espera el archivo en el
   * campo `archivo` (multipart). Formato del CSV:
   *   codigo_producto,precio,precio_minimo,vigente_desde,vigente_hasta
   */
  importarMasivo: async (id: string, file: File): Promise<ImportarMasivoResultado> => {
    const form = new FormData();
    form.append('archivo', file);
    return postForm<ImportarMasivoResultado>(`${BASE}/${id}/importar-masivo/`, form);
  },
};

// ── Detalles de precio (precios por producto dentro de una lista) ────────────

const BASE_DET = '/ventas/detalles-precio';

export const detallesPrecioService = {
  getAll: async (params?: { lista?: string; activo?: boolean }): Promise<DetallePrecio[]> => {
    const qs = new URLSearchParams();
    if (params?.lista) qs.set('id_lista', params.lista);
    if (params?.activo !== undefined) qs.set('activo', String(params.activo));
    const query = qs.toString();
    const response = await get<PaginatedResponse<DetallePrecio> | DetallePrecio[]>(
      `${BASE_DET}/${query ? '?' + query : ''}`,
    );
    const lista = toList<DetallePrecio>(response);
    // El backend filtra por empresa; reforzamos el filtro por lista en el cliente
    // para que cada lista muestre solo sus propios precios.
    return params?.lista ? lista.filter((d) => d.id_lista === params.lista) : lista;
  },

  create: async (payload: DetallePrecioPayload): Promise<DetallePrecio> =>
    post<DetallePrecio>(`${BASE_DET}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: DetallePrecioPayload): Promise<DetallePrecio> =>
    patch<DetallePrecio>(`${BASE_DET}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE_DET}/${id}/`);
  },
};
