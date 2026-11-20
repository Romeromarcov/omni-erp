import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

export interface Almacen {
  id_almacen: string;
  nombre_almacen: string;
  codigo_almacen?: string | null;
  direccion?: string | null;
  usa_ubicaciones?: boolean;
  activo?: boolean;
  id_empresa: string;
}

/**
 * Payload de escritura de Almacén: whitelist explícita de campos editables
 * (CTF-005, defensa en profundidad CWE-915).
 */
export interface AlmacenPayload {
  id_empresa: string;
  nombre_almacen: string;
  codigo_almacen: string;
  direccion: string | null;
  usa_ubicaciones?: boolean;
}

export interface StockUbicacion {
  id_stock_ubicacion: string;
  id_empresa: string;
  id_almacen: string;
  almacen_nombre?: string;
  id_ubicacion: string;
  ubicacion_codigo?: string;
  ubicacion_nombre?: string;
  requiere_autorizacion?: boolean;
  id_producto: string;
  producto_nombre?: string;
  producto_sku?: string | null;
  id_variante: string | null;
  cantidad_disponible: string;
  cantidad_reservada: string;
  cantidad_libre?: string;
  activo: boolean;
  fecha_creacion?: string;
  fecha_actualizacion?: string;
}

export interface StockUbicacionPayload {
  id_almacen: string;
  id_ubicacion: string;
  id_producto: string;
  id_variante?: string | null;
  cantidad_disponible: string;
}

export interface TransferirUbicacionPayload {
  id_almacen: string;
  id_ubicacion_origen: string;
  id_ubicacion_destino: string;
  id_producto: string;
  id_variante?: string | null;
  cantidad: string;
  observaciones?: string;
}

export interface TransferirUbicacionResponse {
  origen: StockUbicacion;
  destino: StockUbicacion;
  id_movimiento: string;
  tipo_movimiento: string;
}

export interface ReservarUbicacionPayload {
  id_almacen: string;
  id_ubicacion: string;
  id_producto: string;
  id_variante?: string | null;
  cantidad: string;
  liberar?: boolean;
}

export const almacenesService = {
  /** Almacenes visibles del usuario (el backend ya filtra por empresas, R-CODE-1).
   * Recorre todas las páginas: los selectores de almacén necesitan el catálogo
   * completo, no sólo los 20 primeros. */
  getAll: async (): Promise<Almacen[]> => {
    const acumulado: Almacen[] = [];
    for (let page = 1; page <= 50; page++) {
      const response = await get<PaginatedResponse<Almacen> | Almacen[]>(
        `/almacenes/almacenes/?page=${page}`,
      );
      acumulado.push(...toList<Almacen>(response));
      const next = Array.isArray(response) ? null : (response.next ?? null);
      if (!next) break;
    }
    return acumulado;
  },

  create: async (payload: AlmacenPayload): Promise<Almacen> =>
    post<Almacen>('/almacenes/almacenes/', payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: AlmacenPayload): Promise<Almacen> =>
    patch<Almacen>(`/almacenes/almacenes/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/almacenes/almacenes/${id}/`);
  },
};

const BASE_STOCK_UBIC = '/almacenes/stock-ubicaciones/';

export const stockUbicacionesService = {
  getAll: async (params?: { almacen?: string; ubicacion?: string; producto?: string }): Promise<StockUbicacion[]> => {
    const qs = new URLSearchParams();
    if (params?.almacen) qs.set('almacen', params.almacen);
    if (params?.ubicacion) qs.set('ubicacion', params.ubicacion);
    if (params?.producto) qs.set('producto', params.producto);
    const query = qs.toString();
    const response = await get<PaginatedResponse<StockUbicacion> | StockUbicacion[]>(
      `${BASE_STOCK_UBIC}${query ? `?${query}` : ''}`,
    );
    return toList<StockUbicacion>(response);
  },

  create: async (payload: StockUbicacionPayload): Promise<StockUbicacion> =>
    post<StockUbicacion>(BASE_STOCK_UBIC, payload as unknown as Record<string, unknown>),

  transferir: async (payload: TransferirUbicacionPayload): Promise<TransferirUbicacionResponse> =>
    post<TransferirUbicacionResponse>(
      `${BASE_STOCK_UBIC}transferir/`,
      payload as unknown as Record<string, unknown>,
    ),

  reservar: async (payload: ReservarUbicacionPayload): Promise<StockUbicacion> =>
    post<StockUbicacion>(
      `${BASE_STOCK_UBIC}reservar/`,
      payload as unknown as Record<string, unknown>,
    ),
};
