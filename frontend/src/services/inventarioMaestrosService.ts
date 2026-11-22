/**
 * Servicio de Datos Maestros de Inventario — CRUD de los catálogos auxiliares
 * que no tenían pantalla de gestión:
 *   - Variantes de Producto      (variante de un producto base: SKU + atributos)
 *   - Conversiones de Unidad     (factor entre dos unidades de medida de un producto)
 *   - Stock en Consignación a Cliente / de Proveedor (saldos de mercancía en consigna)
 *
 * Backend `apps/inventario` (prefijo /api/inventario/):
 *   variantes-producto/
 *   conversiones-unidad-medida/
 *   stock-consignacion-cliente/
 *   stock-consignacion-proveedor/
 *
 * Las cuatro entidades son CRUD completo (BaseModelViewSet). `id_empresa` lo
 * inyecta/scoping el backend (CTF-004/SEC) — no se envía en variantes; en las
 * demás el serializer expone `id_empresa` writable, así que la UI lo manda.
 * Todas las cantidades/montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Variante de Producto ─────────────────────────────────────────────────────

/** Variante de un producto base: su SKU/código propio y atributos (talla, color…). */
export interface VarianteProducto {
  id_variante: string;
  id_producto: string;
  codigo_variante: string | null;
  sku: string | null;
  atributos_json: Record<string, unknown>;
  activo: boolean;
  fecha_creacion?: string;
}

/** Payload de escritura de VarianteProducto (whitelist; empresa la deriva el backend del producto). */
export interface VarianteProductoPayload {
  id_producto: string;
  codigo_variante: string | null;
  sku: string | null;
  atributos_json: Record<string, unknown>;
}

// ── Conversión de Unidad de Medida ───────────────────────────────────────────

/** Factor de conversión entre dos unidades de medida de un producto (origen → destino). */
export interface ConversionUnidad {
  id_conversion: string;
  id_empresa?: string;
  id_producto: string;
  id_unidad_origen: string;
  id_unidad_destino: string;
  factor_conversion: string;
  activo: boolean;
  fecha_creacion?: string;
}

/** Payload de escritura de ConversionUnidad (factor como string, R-CODE-4). */
export interface ConversionUnidadPayload {
  id_empresa: string;
  id_producto: string;
  id_unidad_origen: string;
  id_unidad_destino: string;
  factor_conversion: string;
}

export type EstadoConsignacion = 'ACTIVA' | 'VENCIDA' | 'CERRADA' | 'CANCELADA';

// ── Stock en Consignación a Cliente ──────────────────────────────────────────

/** Mercancía entregada en consignación a un cliente (cantidades en string). */
export interface StockConsignacionCliente {
  id_stock_consignacion: string;
  id_empresa?: string;
  id_cliente: string;
  id_producto: string;
  id_variante: string | null;
  cantidad_consignada: string;
  cantidad_vendida: string;
  cantidad_devuelta: string;
  fecha_consignacion: string;
  fecha_vencimiento: string | null;
  precio_unitario_consignacion: string;
  id_moneda: string;
  estado: EstadoConsignacion;
  fecha_creacion?: string;
}

/** Payload de escritura de StockConsignacionCliente (montos string; fechas YYYY-MM-DD). */
export interface StockConsignacionClientePayload {
  id_empresa: string;
  id_cliente: string;
  id_producto: string;
  id_variante: string | null;
  cantidad_consignada: string;
  cantidad_vendida: string;
  cantidad_devuelta: string;
  fecha_consignacion: string;
  fecha_vencimiento: string | null;
  precio_unitario_consignacion: string;
  id_moneda: string;
  estado: EstadoConsignacion;
}

// ── Stock en Consignación de Proveedor ───────────────────────────────────────

/** Mercancía recibida en consignación de un proveedor (cantidades en string). */
export interface StockConsignacionProveedor {
  id_stock_consignacion: string;
  id_empresa?: string;
  id_proveedor: string;
  id_producto: string;
  id_variante: string | null;
  cantidad_recibida: string;
  cantidad_consumida: string;
  cantidad_devuelta: string;
  fecha_recepcion: string;
  fecha_vencimiento: string | null;
  costo_unitario_consignacion: string;
  id_moneda: string;
  estado: EstadoConsignacion;
  fecha_creacion?: string;
}

/** Payload de escritura de StockConsignacionProveedor (montos string; fechas YYYY-MM-DD). */
export interface StockConsignacionProveedorPayload {
  id_empresa: string;
  id_proveedor: string;
  id_producto: string;
  id_variante: string | null;
  cantidad_recibida: string;
  cantidad_consumida: string;
  cantidad_devuelta: string;
  fecha_recepcion: string;
  fecha_vencimiento: string | null;
  costo_unitario_consignacion: string;
  id_moneda: string;
  estado: EstadoConsignacion;
}

// ── Endpoints ────────────────────────────────────────────────────────────────

const VARIANTES = '/inventario/variantes-producto';
const CONVERSIONES = '/inventario/conversiones-unidad-medida';
const CONS_CLIENTE = '/inventario/stock-consignacion-cliente';
const CONS_PROVEEDOR = '/inventario/stock-consignacion-proveedor';
const REGLAS_REABAST = '/inventario/reglas-reabastecimiento';
const LOTES_PRODUCTO = '/inventario/lotes-producto';

// ── Reglas de Reabastecimiento & Lotes ───────────────────────────────────────

export type RutaReabastecimiento = 'COMPRA' | 'MANUFACTURA' | 'TRANSFERENCIA';

export interface ReglaReabastecimiento {
  id_regla: string;
  id_empresa?: string;
  id_producto: string;
  producto_nombre?: string;
  producto_sku?: string | null;
  id_variante: string | null;
  id_almacen: string;
  almacen_nombre?: string;
  stock_minimo: string;
  stock_maximo: string;
  cantidad_multiplo: string;
  ruta: RutaReabastecimiento;
  id_proveedor_preferido: string | null;
  proveedor_nombre?: string | null;
  id_almacen_origen: string | null;
  almacen_origen_nombre?: string | null;
  activo: boolean;
  fecha_creacion?: string;
  fecha_actualizacion?: string;
}

export interface ReglaReabastecimientoPayload {
  id_producto: string;
  id_variante?: string | null;
  id_almacen: string;
  stock_minimo: string;
  stock_maximo: string;
  cantidad_multiplo: string;
  ruta: RutaReabastecimiento;
  id_proveedor_preferido?: string | null;
  id_almacen_origen?: string | null;
  activo?: boolean;
}

export interface EvaluacionReabastecimientoItem {
  id_regla: string;
  id_producto: string;
  producto_nombre: string;
  producto_sku: string;
  id_variante: string | null;
  id_almacen: string;
  almacen_nombre: string;
  ruta: RutaReabastecimiento;
  id_proveedor_preferido: string | null;
  id_almacen_origen: string | null;
  stock_disponible: string;
  cantidad_comprometida: string;
  cantidad_en_transito: string;
  stock_libre: string;
  stock_proyectado: string;
  stock_minimo: string;
  stock_maximo: string;
  cantidad_multiplo: string;
  requiere_reabastecimiento: boolean;
  deficit: string;
  cantidad_sugerida: string;
}

export interface GenerarBorradorPayload {
  cantidad?: string;
  fecha_necesidad?: string;
}

export interface GenerarBorradorResponse {
  ruta: RutaReabastecimiento;
  tipo_documento: string;
  id_documento: string;
  numero: string;
  estado: string;
  cantidad: string;
  lista_materiales_id?: string | null;
}

export interface LoteProducto {
  id_lote: string;
  id_empresa?: string;
  id_producto: string;
  producto_nombre?: string;
  producto_sku?: string | null;
  id_variante: string | null;
  id_almacen: string;
  almacen_nombre?: string;
  numero_lote: string;
  fecha_fabricacion: string | null;
  fecha_vencimiento: string | null;
  cantidad_disponible: string;
  cantidad_reservada: string;
  cantidad_libre?: string;
  activo: boolean;
  fecha_creacion?: string;
  fecha_actualizacion?: string;
}

export interface LoteProductoPayload {
  id_producto: string;
  id_variante?: string | null;
  id_almacen: string;
  numero_lote: string;
  fecha_fabricacion?: string | null;
  fecha_vencimiento?: string | null;
  activo?: boolean;
}

// ── Variantes de Producto ────────────────────────────────────────────────────

export const variantesProductoService = {
  /** Lista las variantes; filtra por producto en el cliente (el backend acota por empresa). */
  getAll: async (params?: { producto?: string }): Promise<VarianteProducto[]> => {
    const r = await get<PaginatedResponse<VarianteProducto> | VarianteProducto[]>(`${VARIANTES}/`);
    const lista = toList<VarianteProducto>(r);
    return params?.producto ? lista.filter((v) => v.id_producto === params.producto) : lista;
  },

  create: async (payload: VarianteProductoPayload): Promise<VarianteProducto> =>
    post<VarianteProducto>(`${VARIANTES}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: VarianteProductoPayload): Promise<VarianteProducto> =>
    patch<VarianteProducto>(`${VARIANTES}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${VARIANTES}/${id}/`);
  },
};

// ── Conversiones de Unidad de Medida ─────────────────────────────────────────

export const conversionesUnidadService = {
  /** Lista las conversiones; filtra por producto en el cliente. */
  getAll: async (params?: { producto?: string }): Promise<ConversionUnidad[]> => {
    const r = await get<PaginatedResponse<ConversionUnidad> | ConversionUnidad[]>(`${CONVERSIONES}/`);
    const lista = toList<ConversionUnidad>(r);
    return params?.producto ? lista.filter((c) => c.id_producto === params.producto) : lista;
  },

  create: async (payload: ConversionUnidadPayload): Promise<ConversionUnidad> =>
    post<ConversionUnidad>(`${CONVERSIONES}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ConversionUnidadPayload): Promise<ConversionUnidad> =>
    patch<ConversionUnidad>(`${CONVERSIONES}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${CONVERSIONES}/${id}/`);
  },
};

// ── Stock en Consignación a Cliente ──────────────────────────────────────────

export const stockConsignacionClienteService = {
  /** Lista los saldos en consignación a clientes; filtra por cliente/estado en el cliente. */
  getAll: async (params?: { cliente?: string; estado?: string }): Promise<StockConsignacionCliente[]> => {
    const r = await get<PaginatedResponse<StockConsignacionCliente> | StockConsignacionCliente[]>(
      `${CONS_CLIENTE}/`,
    );
    let lista = toList<StockConsignacionCliente>(r);
    if (params?.cliente) lista = lista.filter((s) => s.id_cliente === params.cliente);
    if (params?.estado) lista = lista.filter((s) => s.estado === params.estado);
    return lista;
  },

  create: async (payload: StockConsignacionClientePayload): Promise<StockConsignacionCliente> =>
    post<StockConsignacionCliente>(`${CONS_CLIENTE}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: StockConsignacionClientePayload): Promise<StockConsignacionCliente> =>
    patch<StockConsignacionCliente>(`${CONS_CLIENTE}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${CONS_CLIENTE}/${id}/`);
  },
};

// ── Stock en Consignación de Proveedor ───────────────────────────────────────

export const stockConsignacionProveedorService = {
  /** Lista los saldos en consignación de proveedores; filtra por proveedor/estado en el cliente. */
  getAll: async (params?: { proveedor?: string; estado?: string }): Promise<StockConsignacionProveedor[]> => {
    const r = await get<PaginatedResponse<StockConsignacionProveedor> | StockConsignacionProveedor[]>(
      `${CONS_PROVEEDOR}/`,
    );
    let lista = toList<StockConsignacionProveedor>(r);
    if (params?.proveedor) lista = lista.filter((s) => s.id_proveedor === params.proveedor);
    if (params?.estado) lista = lista.filter((s) => s.estado === params.estado);
    return lista;
  },

  create: async (payload: StockConsignacionProveedorPayload): Promise<StockConsignacionProveedor> =>
    post<StockConsignacionProveedor>(`${CONS_PROVEEDOR}/`, payload as unknown as Record<string, unknown>),

  update: async (
    id: string,
    payload: StockConsignacionProveedorPayload,
  ): Promise<StockConsignacionProveedor> =>
    patch<StockConsignacionProveedor>(`${CONS_PROVEEDOR}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${CONS_PROVEEDOR}/${id}/`);
  },
};

// ── Reglas de Reabastecimiento ───────────────────────────────────────────────

export const reglasReabastecimientoService = {
  getAll: async (params?: { almacen?: string; producto?: string }): Promise<ReglaReabastecimiento[]> => {
    const qs = new URLSearchParams();
    if (params?.almacen) qs.set('almacen', params.almacen);
    if (params?.producto) qs.set('producto', params.producto);
    const query = qs.toString();
    const r = await get<PaginatedResponse<ReglaReabastecimiento> | ReglaReabastecimiento[]>(
      `${REGLAS_REABAST}/${query ? `?${query}` : ''}`,
    );
    return toList<ReglaReabastecimiento>(r);
  },

  create: async (payload: ReglaReabastecimientoPayload): Promise<ReglaReabastecimiento> =>
    post<ReglaReabastecimiento>(`${REGLAS_REABAST}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: Partial<ReglaReabastecimientoPayload>): Promise<ReglaReabastecimiento> =>
    patch<ReglaReabastecimiento>(`${REGLAS_REABAST}/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${REGLAS_REABAST}/${id}/`);
  },

  evaluar: async (params?: { almacen?: string; incluir_ok?: boolean }): Promise<EvaluacionReabastecimientoItem[]> => {
    const body: Record<string, unknown> = { incluir_ok: params?.incluir_ok ?? false };
    if (params?.almacen) body.almacen = params.almacen;
    const r = await post<{ resultados: EvaluacionReabastecimientoItem[] }>(`${REGLAS_REABAST}/evaluar/`, body);
    return r.resultados ?? [];
  },

  generarBorrador: async (
    idRegla: string,
    payload?: GenerarBorradorPayload,
  ): Promise<GenerarBorradorResponse> =>
    post<GenerarBorradorResponse>(
      `${REGLAS_REABAST}/${idRegla}/generar-borrador/`,
      (payload ?? {}) as Record<string, unknown>,
    ),
};

// ── Lotes de Producto ────────────────────────────────────────────────────────

export const lotesProductoService = {
  getAll: async (params?: {
    almacen?: string;
    producto?: string;
    por_vencer_dias?: number;
    solo_con_stock?: boolean;
  }): Promise<LoteProducto[]> => {
    const qs = new URLSearchParams();
    if (params?.almacen) qs.set('almacen', params.almacen);
    if (params?.producto) qs.set('producto', params.producto);
    if (params?.por_vencer_dias !== undefined) qs.set('por_vencer_dias', String(params.por_vencer_dias));
    if (params?.solo_con_stock !== undefined) qs.set('solo_con_stock', String(params.solo_con_stock));
    const query = qs.toString();
    const r = await get<PaginatedResponse<LoteProducto> | LoteProducto[]>(
      `${LOTES_PRODUCTO}/${query ? `?${query}` : ''}`,
    );
    return toList<LoteProducto>(r);
  },

  create: async (payload: LoteProductoPayload): Promise<LoteProducto> =>
    post<LoteProducto>(`${LOTES_PRODUCTO}/`, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: Partial<LoteProductoPayload>): Promise<LoteProducto> =>
    patch<LoteProducto>(`${LOTES_PRODUCTO}/${id}/`, payload as unknown as Record<string, unknown>),
};
