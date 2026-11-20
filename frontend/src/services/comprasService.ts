/**
 * Servicio de Compras — órdenes de compra, recepción de mercancía, factura
 * de proveedor y flujo transaccional Source-to-PO.
 *
 * Endpoints del backend (`apps/compras`, base /api/compras/):
 *   GET  /compras/ordenes-compra/                             — lista paginada de OC
 *   GET  /compras/ordenes-compra/{id}/                        — detalle de OC
 *   POST /compras/ordenes-compra/                             — crea OC (id_empresa lo inyecta el backend, H-API-2)
 *   POST /compras/ordenes-compra/{id}/aprobar/                — BORRADOR/ENVIADA → APROBADA (400 si no aplica)
 *   POST /compras/requisiciones-compra/{id}/enviar-aprobacion/    — BORRADOR → PENDIENTE | APROBADA
 *   POST /compras/requisiciones-compra/{id}/confirmar-aprobacion/ — PENDIENTE → APROBADA
 *   POST /compras/solicitudes-cotizacion/desde-requisiciones/     — consolida requisiciones APROBADA en RFQ
 *   GET  /compras/solicitudes-cotizacion/{id}/comparar-ofertas/   — comparativo lado a lado (Decimal)
 *   POST /compras/ofertas-proveedor/{id}/adjudicar/               — adjudica total/parcial → OrdenCompra BORRADOR
 *   GET  /compras/detalles-orden-compra/                      — líneas (sin filtro por OC: se filtra client-side)
 *   POST /compras/detalles-orden-compra/                      — crea línea de OC
 *   GET  /compras/recepciones-mercancia/                      — recepciones (filtro client-side por OC)
 *   POST /compras/recepciones-mercancia/recepcionar/          — registra recepción (entrada de inventario + CxP)
 *   POST /compras/facturas-compra/facturar/                   — registra factura del proveedor sobre una recepción
 *   GET  /proveedores/proveedores/                            — catálogo de proveedores visibles
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { get, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';
import type { RequisicionCompra, SolicitudCotizacion } from './aprovisionamientoService';

// ── Types ──────────────────────────────────────────────────────────────────

export type EstadoOrdenCompra =
  | 'BORRADOR'
  | 'ENVIADA'
  | 'APROBADA'
  | 'RECHAZADA'
  | 'CERRADA'
  | 'ANULADA';

export interface OrdenCompra {
  id_orden_compra: string;
  id_empresa: string;
  id_proveedor: string;
  id_oferta_origen?: string | null;
  id_almacen_destino?: string | null;
  tipo_operacion: string | null;
  fecha_cierre_estimada: string | null;
  numero_orden: string;
  fecha_orden: string;
  estado: EstadoOrdenCompra | string;
  observaciones: string | null;
  activo: boolean;
  fecha_creacion: string;
}

export interface DetalleOrdenCompra {
  id_detalle_orden_compra: string;
  id_orden_compra: string;
  id_producto: string;
  /** Montos como string decimal (R-CODE-4). */
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  observaciones: string | null;
}

export interface RecepcionMercancia {
  id_recepcion: string;
  id_empresa: string;
  id_orden_compra: string;
  fecha_recepcion: string;
  /** String decimal (R-CODE-4). */
  monto_total: string;
  observaciones: string | null;
  activo: boolean;
  fecha_creacion: string;
}

export interface Proveedor {
  id_proveedor: string;
  razon_social: string;
  rif?: string | null;
}

export interface CrearOrdenCompraPayload {
  id_proveedor: string;
  numero_orden: string;
  fecha_orden: string;
  observaciones?: string;
}

export interface CrearDetalleOrdenPayload {
  id_orden_compra: string;
  id_producto: string;
  /** Strings decimales (R-CODE-4); el subtotal se calcula con decimal.js en la UI. */
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
}

export interface RecepcionItemPayload {
  producto_id: string;
  /** Strings decimales (R-CODE-4). */
  cantidad: string;
  costo_unitario: string;
}

export interface RecepcionarPayload {
  orden_compra_id: string;
  almacen_id: string;
  items: RecepcionItemPayload[];
}

export interface RecepcionarResponse {
  recepcion_id: string;
  movimientos: number;
  cxp_id: string | null;
  /** String decimal (R-CODE-4). */
  monto_total: string;
}

export interface FacturarPayload {
  recepcion_id: string;
  numero_factura: string;
  fecha_emision?: string;
}

export interface FacturarResponse {
  factura_id: string;
  numero_factura: string;
  /** String decimal (R-CODE-4). */
  monto_total: string;
}

// ── Types Source-to-PO ─────────────────────────────────────────────────────

export interface CrearRfqDesdeRequisicionesPayload {
  requisicion_ids: string[];
  proveedores_ids: string[];
  fecha_vencimiento: string;
  numero_solicitud?: string;
  observaciones?: string;
}

export interface OfertaResumenComparativo {
  id_oferta: string;
  numero_oferta: string;
  id_proveedor: string;
  proveedor_nombre: string;
  estado: string;
  monto_total: string;
  tiempo_entrega: string;
  condiciones_pago: string;
  es_mejor_total: boolean;
}

export interface CotizacionComparada {
  id_oferta: string;
  id_proveedor: string;
  proveedor_nombre: string;
  cantidad: string | null;
  precio_unitario: string | null;
  subtotal: string | null;
  tiempo_entrega: string | null;
  es_mejor_precio: boolean;
}

export interface ProductoComparado {
  id_producto: string;
  producto_nombre: string;
  sku: string;
  cantidad_solicitada: string;
  especificaciones: string;
  mejor_precio_unitario: string | null;
  cotizaciones: CotizacionComparada[];
}

export interface ComparativoOfertasRfq {
  rfq_id: string;
  numero_solicitud: string;
  estado: string;
  fecha_solicitud: string;
  fecha_vencimiento: string;
  mejor_oferta_id: string | null;
  ofertas: OfertaResumenComparativo[];
  productos: ProductoComparado[];
}

export interface AdjudicacionParcialItem {
  id_producto: string;
  cantidad: string;
}

export interface AdjudicarOfertaPayload {
  id_almacen_destino: string;
  rechazar_competidoras?: boolean;
  adjudicacion_parcial?: AdjudicacionParcialItem[] | null;
}

export interface AdjudicarOfertaResponse {
  id_orden_compra: string;
  numero_orden: string;
  estado_orden: string;
  monto_total: string;
  oferta_id: string;
  oferta_estado: string;
  rfq_id: string;
  rfq_estado: string;
  lineas: number;
}

const BASE = '/compras';

/** Máximo de páginas a recorrer al filtrar client-side (gap: el backend aún no filtra por OC). */
const MAX_PAGINAS_FILTRO = 20;

/**
 * Recorre la lista paginada acumulando los elementos que pasan el filtro.
 * Necesario porque `detalles-orden-compra` y `recepciones-mercancia` no
 * exponen (aún) filtro por `id_orden_compra` en querystring.
 */
async function fetchFiltrado<T>(endpoint: string, match: (item: T) => boolean): Promise<T[]> {
  const acumulado: T[] = [];
  for (let page = 1; page <= MAX_PAGINAS_FILTRO; page++) {
    const respuesta = await get<PaginatedResponse<T> | T[]>(`${endpoint}?page=${page}`);
    const items = toList<T>(respuesta);
    acumulado.push(...items.filter(match));
    const next = Array.isArray(respuesta) ? null : (respuesta.next ?? null);
    if (!next) break;
  }
  return acumulado;
}

// ── Service ────────────────────────────────────────────────────────────────

export const comprasService = {
  /** Lista paginada de órdenes de compra (normaliza lista directa o DRF paginada). */
  getOrdenesPaginated: async (page = 1, pageSize = 20): Promise<PaginatedResponse<OrdenCompra>> => {
    const response = await get<PaginatedResponse<OrdenCompra> | OrdenCompra[]>(
      `${BASE}/ordenes-compra/?page=${page}&page_size=${pageSize}`,
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response;
    }
    const arr = toList<OrdenCompra>(response);
    return { count: arr.length, next: null, previous: null, results: arr };
  },

  getOrden: async (id: string): Promise<OrdenCompra> => {
    return get<OrdenCompra>(`${BASE}/ordenes-compra/${id}/`);
  },

  /** Líneas de la OC (filtro client-side; el backend no expone ?id_orden_compra). */
  getDetallesOrden: async (ordenId: string): Promise<DetalleOrdenCompra[]> => {
    return fetchFiltrado<DetalleOrdenCompra>(
      `${BASE}/detalles-orden-compra/`,
      (d) => d.id_orden_compra === ordenId,
    );
  },

  /** Recepciones registradas contra la OC (filtro client-side). */
  getRecepcionesOrden: async (ordenId: string): Promise<RecepcionMercancia[]> => {
    return fetchFiltrado<RecepcionMercancia>(
      `${BASE}/recepciones-mercancia/`,
      (r) => r.id_orden_compra === ordenId,
    );
  },

  /** Crea la cabecera de la OC; `id_empresa` lo inyecta el backend (H-API-2). */
  crearOrden: async (payload: CrearOrdenCompraPayload): Promise<OrdenCompra> => {
    return post<OrdenCompra>(
      `${BASE}/ordenes-compra/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Crea una línea de OC; el subtotal ya viene calculado con decimal.js. */
  crearDetalle: async (payload: CrearDetalleOrdenPayload): Promise<DetalleOrdenCompra> => {
    return post<DetalleOrdenCompra>(
      `${BASE}/detalles-orden-compra/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Aprueba la OC (400 del backend si el estado no lo permite). */
  aprobarOrden: async (id: string): Promise<{ detail: string; estado: string }> => {
    return post<{ detail: string; estado: string }>(`${BASE}/ordenes-compra/${id}/aprobar/`, {});
  },

  /**
   * Registra la recepción de mercancía: entrada de inventario + CxP.
   * El backend responde 400 con `detail` si falta mapeo contable, la OC no
   * está aprobada o un producto no es visible.
   */
  recepcionar: async (payload: RecepcionarPayload): Promise<RecepcionarResponse> => {
    return post<RecepcionarResponse>(
      `${BASE}/recepciones-mercancia/recepcionar/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Registra la factura del proveedor sobre una recepción (400 con `detail` si falla). */
  facturar: async (payload: FacturarPayload): Promise<FacturarResponse> => {
    return post<FacturarResponse>(
      `${BASE}/facturas-compra/facturar/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Proveedores visibles del usuario (el backend filtra por empresas, R-CODE-1). */
  getProveedores: async (): Promise<Proveedor[]> => {
    const response = await get<PaginatedResponse<Proveedor> | Proveedor[]>(
      '/proveedores/proveedores/?page_size=200',
    );
    return toList<Proveedor>(response);
  },

  /** Envía una requisición BORRADOR a aprobación departamental/general (o aprueba directo si no aplica). */
  enviarAprobacionRequisicion: async (id: string): Promise<RequisicionCompra> => {
    return post<RequisicionCompra>(`${BASE}/requisiciones-compra/${id}/enviar-aprobacion/`, {});
  },

  /** Confirma aprobación de una requisición PENDIENTE tras aprobarse su SolicitudAprobacion. */
  confirmarAprobacionRequisicion: async (id: string): Promise<RequisicionCompra> => {
    return post<RequisicionCompra>(`${BASE}/requisiciones-compra/${id}/confirmar-aprobacion/`, {});
  },

  /** Consolida 1..N requisiciones APROBADA en una SolicitudCotizacion (RFQ) ENVIADA. */
  crearRfqDesdeRequisiciones: async (
    payload: CrearRfqDesdeRequisicionesPayload,
  ): Promise<SolicitudCotizacion> => {
    return post<SolicitudCotizacion>(
      `${BASE}/solicitudes-cotizacion/desde-requisiciones/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  /** Matriz comparativa lado a lado de todas las ofertas de una RFQ (Decimal → str). */
  compararOfertasRfq: async (rfqId: string): Promise<ComparativoOfertasRfq> => {
    return get<ComparativoOfertasRfq>(`${BASE}/solicitudes-cotizacion/${rfqId}/comparar-ofertas/`);
  },

  /** Adjudica una oferta (total o parcial) generando una OrdenCompra en BORRADOR. */
  adjudicarOferta: async (
    ofertaId: string,
    payload: AdjudicarOfertaPayload,
  ): Promise<AdjudicarOfertaResponse> => {
    return post<AdjudicarOfertaResponse>(
      `${BASE}/ofertas-proveedor/${ofertaId}/adjudicar/`,
      payload as unknown as Record<string, unknown>,
    );
  },
};
