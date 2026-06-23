import { get, post, del } from './api';
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

/** Forma cruda de cada ítem de `{kardex: [...]}` que devuelve el backend. */
interface KardexItemApi {
  id_movimiento: string;
  fecha_hora: string;
  tipo_movimiento: string;
  cantidad: string;
  delta: string;
  almacen_origen: string | null;
  almacen_destino: string | null;
  costo_unitario: string | null;
  saldo_anterior: string;
  saldo_posterior: string;
  observaciones: string | null;
}

interface KardexResponseApi {
  producto_id: string;
  producto_nombre: string;
  almacen_id: string | null;
  saldo_final: string;
  kardex: KardexItemApi[];
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
    // Gap E2E (PR #76): el backend NO devuelve una lista paginada sino
    // `{kardex: [...]}` con nombres de campo propios; normalizamos aquí a la
    // forma MovimientoInventario que consume la UI (antes siempre quedaba []).
    const response = await get<
      KardexResponseApi | PaginatedResponse<MovimientoInventario> | MovimientoInventario[]
    >(`/inventario/productos/${productoId}/kardex/${query ? '?' + query : ''}`);
    if (response && typeof response === 'object' && 'kardex' in response) {
      return response.kardex.map((item) => ({
        id_movimiento_inventario: item.id_movimiento,
        id_empresa: '',
        fecha_hora_movimiento: item.fecha_hora,
        tipo_movimiento: item.tipo_movimiento,
        id_producto: response.producto_id,
        id_almacen_origen: null,
        id_almacen_destino: null,
        cantidad: item.cantidad,
        costo_unitario_movimiento: item.costo_unitario,
        observaciones: item.observaciones,
        producto_nombre: response.producto_nombre,
        almacen_origen_nombre: item.almacen_origen,
        almacen_destino_nombre: item.almacen_destino,
        fecha_creacion: item.fecha_hora,
      }));
    }
    return toList<MovimientoInventario>(response);
  },
};

// ── Movimientos ────────────────────────────────────────────────────────────

export const movimientoService = {
  registrarAjuste: async (payload: AjusteInventarioPayload): Promise<MovimientoInventario> => {
    return post<MovimientoInventario>('/inventario/movimientos-inventario/', payload as unknown as Record<string, unknown>);
  },
};

// ── Operaciones con stepper (recepciones / entregas) ─────────────────────────

export interface OperacionPaso {
  id_operacion_paso: string;
  secuencia: number;
  nombre_paso: string;
  confirmado: boolean;
  fecha_confirmacion: string | null;
}

export interface OperacionLinea {
  id_linea: string;
  id_producto: string;
  producto_nombre?: string;
  cantidad: string;
  costo_unitario: string | null;
}

export type TipoOperacion = 'RECEPCION' | 'ENTREGA';
export type EstadoOperacion = 'EN_PROCESO' | 'COMPLETADA' | 'CANCELADA';

export interface OperacionInventario {
  id_operacion: string;
  numero: string;
  tipo_operacion: TipoOperacion;
  origen_tipo: string;
  origen_id: string | null;
  id_almacen: string;
  id_almacen_contraparte: string | null;
  estado: EstadoOperacion;
  motivo: string;
  fecha: string;
  pasos: OperacionPaso[];
  lineas: OperacionLinea[];
}

export interface CrearOperacionLinea {
  producto: string;
  variante?: string | null;
  cantidad: string;
  costo_unitario?: string | null;
}

export interface CrearOperacionPayload {
  almacen: string;
  origen_tipo: string;
  origen_id?: string | null;
  almacen_contraparte?: string | null;
  motivo?: string;
  lineas: CrearOperacionLinea[];
}

function operacionService(base: 'recepciones' | 'entregas') {
  return {
    list: async (): Promise<OperacionInventario[]> => {
      const r = await get<PaginatedResponse<OperacionInventario> | OperacionInventario[]>(
        `/inventario/${base}/`,
      );
      return toList(r);
    },
    create: async (payload: CrearOperacionPayload): Promise<OperacionInventario> =>
      post<OperacionInventario>(`/inventario/${base}/`, payload as unknown as Record<string, unknown>),
    confirmStep: async (opId: string, stepId: string): Promise<OperacionInventario> =>
      post<OperacionInventario>(`/inventario/${base}/${opId}/step/${stepId}/confirm/`, {}),
  };
}

export const recepcionesService = operacionService('recepciones');
export const entregasService = operacionService('entregas');

// ── Pasos de operación (configuración por almacén) ───────────────────────────

export interface PasoOperacion {
  id_paso_operacion: string;
  id_empresa: string;
  id_almacen: string;
  tipo_operacion: TipoOperacion;
  nombre_paso: string;
  secuencia: number;
  activo: boolean;
}

export interface CrearPasoPayload {
  id_empresa: string;
  id_almacen: string;
  tipo_operacion: TipoOperacion;
  nombre_paso: string;
  secuencia: number;
}

export const pasosOperacionService = {
  list: async (almacen: string, tipo: TipoOperacion): Promise<PasoOperacion[]> => {
    const r = await get<PaginatedResponse<PasoOperacion> | PasoOperacion[]>(
      `/inventario/pasos-operacion/?almacen=${almacen}&tipo_operacion=${tipo}`,
    );
    return toList(r);
  },
  create: async (payload: CrearPasoPayload): Promise<PasoOperacion> =>
    post<PasoOperacion>('/inventario/pasos-operacion/', payload as unknown as Record<string, unknown>),
  remove: async (id: string): Promise<void> => {
    await del<void>(`/inventario/pasos-operacion/${id}/`);
  },
};

// ── Reporte de valoración ────────────────────────────────────────────────────

export interface ValoracionFila {
  producto_id: string;
  producto: string;
  almacen_id: string;
  almacen: string;
  metodo: string;
  cantidad: string;
  valor_total: string;
  costo_promedio: string;
}

export const reportesInventarioService = {
  valoracion: async (params?: { producto?: string; almacen?: string }): Promise<ValoracionFila[]> => {
    const qs = new URLSearchParams();
    if (params?.producto) qs.set('producto', params.producto);
    if (params?.almacen) qs.set('almacen', params.almacen);
    const q = qs.toString();
    const r = await get<{ valoracion: ValoracionFila[] }>(
      `/inventario/reportes/valoracion/${q ? `?${q}` : ''}`,
    );
    return r.valoracion ?? [];
  },
};
