import { get, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export interface Producto {
  id_producto: string;
  nombre_producto: string;
  sku: string | null;
  descripcion: string | null;
  tipo_producto: string;
  costo_promedio: string;
  precio_venta_sugerido: string;
  nombre_categoria: string | null;
  nombre_unidad_medida: string | null;
  activo: boolean;
}

export interface StockActual {
  id_stock_actual: string;
  id_empresa: string;
  id_producto: string;
  id_almacen: string;
  cantidad_disponible: string;
  cantidad_comprometida: string;
  cantidad_en_transito: string;
  cantidad_minima: string;
  cantidad_maxima: string;
  fecha_ultima_actualizacion: string;
  producto_nombre: string | null;
  almacen_nombre: string | null;
}

export interface MovimientoInventario {
  id_movimiento_inventario: string;
  id_empresa: string;
  fecha_hora_movimiento: string;
  tipo_movimiento: string;
  id_producto: string;
  id_almacen_origen: string | null;
  id_almacen_destino: string | null;
  cantidad: string;
  costo_unitario_movimiento: string | null;
  observaciones: string | null;
  producto_nombre: string | null;
  almacen_origen_nombre: string | null;
  almacen_destino_nombre: string | null;
  fecha_creacion: string;
}

export interface KardexEntry {
  fecha_hora_movimiento: string;
  tipo_movimiento: string;
  cantidad: string;
  costo_unitario_movimiento: string | null;
  observaciones: string | null;
  almacen_origen_nombre: string | null;
  almacen_destino_nombre: string | null;
}

export interface AjusteInventarioPayload {
  id_empresa: string;
  id_producto: string;
  id_almacen_destino?: string;
  id_almacen_origen?: string;
  tipo_movimiento: 'AJUSTE';
  cantidad: number;
  fecha_hora_movimiento: string;
  observaciones?: string;
  costo_unitario_movimiento?: number;
}

// Normalización de respuestas paginadas: ver `toList` en utils/api.

// ── Stock Actual ───────────────────────────────────────────────────────────

export const stockActualService = {
  getAll: async (params?: { empresa?: string; producto?: string; almacen?: string }): Promise<StockActual[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.producto) qs.set('producto', params.producto);
    if (params?.almacen) qs.set('almacen', params.almacen);
    const query = qs.toString();
    const response = await get<PaginatedResponse<StockActual> | StockActual[]>(
      `/inventario/stock-actual/${query ? '?' + query : ''}`
    );
    return toList<StockActual>(response);
  },

  /** Stock por debajo de la cantidad mínima (alertas) */
  getBajoMinimo: async (empresaId?: string): Promise<StockActual[]> => {
    const all = await stockActualService.getAll(empresaId ? { empresa: empresaId } : undefined);
    return all.filter(
      (s) => parseFloat(s.cantidad_disponible) < parseFloat(s.cantidad_minima) && parseFloat(s.cantidad_minima) > 0
    );
  },
};

// ── Productos ──────────────────────────────────────────────────────────────

export const productoInventarioService = {
  getAll: async (params?: { empresa?: string }): Promise<Producto[]> => {
    const qs = params?.empresa ? `?empresa=${params.empresa}` : '';
    const response = await get<PaginatedResponse<Producto> | Producto[]>(`/inventario/productos/${qs}`);
    return toList<Producto>(response);
  },

  getById: async (id: string): Promise<Producto> => {
    return get<Producto>(`/inventario/productos/${id}/`);
  },

  getKardex: async (
    productoId: string,
    params?: { almacen?: string; fecha_desde?: string; fecha_hasta?: string }
  ): Promise<MovimientoInventario[]> => {
    const qs = new URLSearchParams();
    if (params?.almacen) qs.set('almacen', params.almacen);
    if (params?.fecha_desde) qs.set('fecha_desde', params.fecha_desde);
    if (params?.fecha_hasta) qs.set('fecha_hasta', params.fecha_hasta);
    const query = qs.toString();
    const response = await get<PaginatedResponse<MovimientoInventario> | MovimientoInventario[]>(
      `/inventario/productos/${productoId}/kardex/${query ? '?' + query : ''}`
    );
    return toList<MovimientoInventario>(response);
  },
};

// ── Movimientos ────────────────────────────────────────────────────────────

export const movimientoService = {
  registrarAjuste: async (payload: AjusteInventarioPayload): Promise<MovimientoInventario> => {
    return post<MovimientoInventario>('/inventario/movimientos-inventario/', payload as unknown as Record<string, unknown>);
  },
};
