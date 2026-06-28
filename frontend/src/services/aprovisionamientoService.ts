/**
 * Servicio de Aprovisionamiento de Compras (source-to-PO) — el front que precede
 * a la Orden de Compra: Requisiciones → Solicitudes de Cotización (RFQ) → Ofertas
 * de Proveedor. El backend (apps/compras, base /api/compras/) ya está 100 %.
 *
 * Endpoints (todos CRUD, `id_empresa` lo inyecta el backend vía EmpresaInjectMixin
 * cuando aplica, H-API-2):
 *   /compras/requisiciones-compra/            (RequisicionCompraViewSet)
 *   /compras/detalles-requisicion-compra/     (líneas de requisición)
 *   /compras/solicitudes-cotizacion/          (SolicitudCotizacionViewSet)
 *   /compras/detalles-solicitud-cotizacion/   (líneas de solicitud)
 *   /compras/ofertas-proveedor/               (OfertaProveedorViewSet)
 *   /compras/detalles-oferta-proveedor/       (líneas de oferta)
 *
 * Los detalles NO exponen filtro por padre en querystring; se filtra client-side
 * (igual que comprasService con sus líneas de OC). Todos los montos viajan como
 * STRING decimal (R-CODE-4) — nunca number.
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos: Requisición ──────────────────────────────────────────────────────

export type EstadoRequisicion =
  | 'BORRADOR'
  | 'PENDIENTE'
  | 'APROBADA'
  | 'RECHAZADA'
  | 'PROCESADA'
  | 'ANULADA';

export type PrioridadRequisicion = 'BAJA' | 'MEDIA' | 'ALTA' | 'URGENTE';

export interface RequisicionCompra {
  id_requisicion: string;
  id_empresa?: string;
  id_solicitante: string;
  id_departamento: string | null;
  numero_requisicion: string;
  fecha_requisicion: string;
  estado: EstadoRequisicion | string;
  prioridad: PrioridadRequisicion | string;
  fecha_necesidad: string;
  justificacion: string;
  observaciones: string | null;
  fecha_creacion?: string;
}

/** Payload de escritura (whitelist; `id_empresa` lo inyecta el backend, H-API-2). */
export interface RequisicionCompraPayload {
  id_solicitante: string;
  id_departamento: string | null;
  numero_requisicion: string;
  fecha_requisicion: string;
  estado: string;
  prioridad: string;
  fecha_necesidad: string;
  justificacion: string;
  observaciones: string | null;
}

export interface DetalleRequisicion {
  id_detalle_requisicion: string;
  id_requisicion: string;
  id_producto: string;
  /** Montos como string decimal (R-CODE-4). */
  cantidad_solicitada: string;
  precio_estimado: string | null;
  justificacion: string | null;
  observaciones: string | null;
}

export interface DetalleRequisicionPayload {
  id_requisicion: string;
  id_producto: string;
  cantidad_solicitada: string;
  precio_estimado: string | null;
  justificacion: string | null;
  observaciones: string | null;
}

// ── Tipos: Solicitud de Cotización (RFQ) ────────────────────────────────────

export type EstadoSolicitud = 'BORRADOR' | 'ENVIADA' | 'RESPONDIDA' | 'VENCIDA' | 'ANULADA';

export interface SolicitudCotizacion {
  id_solicitud_cotizacion: string;
  id_empresa?: string;
  numero_solicitud: string;
  fecha_solicitud: string;
  fecha_vencimiento: string;
  estado: EstadoSolicitud | string;
  observaciones: string | null;
  fecha_creacion?: string;
}

export interface SolicitudCotizacionPayload {
  numero_solicitud: string;
  fecha_solicitud: string;
  fecha_vencimiento: string;
  estado: string;
  observaciones: string | null;
}

export interface DetalleSolicitud {
  id_detalle_solicitud: string;
  id_solicitud_cotizacion: string;
  id_producto: string;
  /** Cantidad como string decimal (R-CODE-4). */
  cantidad: string;
  especificaciones: string | null;
  observaciones: string | null;
}

export interface DetalleSolicitudPayload {
  id_solicitud_cotizacion: string;
  id_producto: string;
  cantidad: string;
  especificaciones: string | null;
  observaciones: string | null;
}

// ── Tipos: Oferta de Proveedor ──────────────────────────────────────────────

export type EstadoOferta = 'RECIBIDA' | 'EVALUADA' | 'ACEPTADA' | 'RECHAZADA' | 'VENCIDA';

export interface OfertaProveedor {
  id_oferta: string;
  id_solicitud_cotizacion: string;
  id_proveedor: string;
  numero_oferta: string;
  fecha_oferta: string;
  fecha_vencimiento: string;
  estado: EstadoOferta | string;
  /** Monto como string decimal (R-CODE-4). */
  monto_total: string;
  condiciones_pago: string | null;
  tiempo_entrega: string | null;
  observaciones: string | null;
  fecha_creacion?: string;
}

export interface OfertaProveedorPayload {
  id_solicitud_cotizacion: string;
  id_proveedor: string;
  numero_oferta: string;
  fecha_oferta: string;
  fecha_vencimiento: string;
  estado: string;
  monto_total: string;
  condiciones_pago: string | null;
  tiempo_entrega: string | null;
  observaciones: string | null;
}

export interface DetalleOferta {
  id_detalle_oferta: string;
  id_oferta: string;
  id_producto: string;
  /** Montos como string decimal (R-CODE-4). */
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  tiempo_entrega: string | null;
  observaciones: string | null;
}

export interface DetalleOfertaPayload {
  id_oferta: string;
  id_producto: string;
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  tiempo_entrega: string | null;
  observaciones: string | null;
}

const BASE = '/compras';

// ── Requisiciones ───────────────────────────────────────────────────────────

export const requisicionesService = {
  getAll: async (params?: { estado?: string }): Promise<RequisicionCompra[]> => {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set('estado', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<RequisicionCompra> | RequisicionCompra[]>(
      `${BASE}/requisiciones-compra/${query ? '?' + query : ''}`,
    );
    return toList<RequisicionCompra>(response);
  },

  getById: async (id: string): Promise<RequisicionCompra> =>
    get<RequisicionCompra>(`${BASE}/requisiciones-compra/${id}/`),

  create: async (payload: RequisicionCompraPayload): Promise<RequisicionCompra> =>
    post<RequisicionCompra>(
      `${BASE}/requisiciones-compra/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: RequisicionCompraPayload): Promise<RequisicionCompra> =>
    patch<RequisicionCompra>(
      `${BASE}/requisiciones-compra/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/requisiciones-compra/${id}/`);
  },
};

export const detallesRequisicionService = {
  /** Líneas de la requisición (filtro client-side; el backend no expone ?id_requisicion). */
  getAll: async (params?: { requisicion?: string }): Promise<DetalleRequisicion[]> => {
    const response = await get<PaginatedResponse<DetalleRequisicion> | DetalleRequisicion[]>(
      `${BASE}/detalles-requisicion-compra/`,
    );
    const lista = toList<DetalleRequisicion>(response);
    return params?.requisicion
      ? lista.filter((d) => d.id_requisicion === params.requisicion)
      : lista;
  },

  create: async (payload: DetalleRequisicionPayload): Promise<DetalleRequisicion> =>
    post<DetalleRequisicion>(
      `${BASE}/detalles-requisicion-compra/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: DetalleRequisicionPayload): Promise<DetalleRequisicion> =>
    patch<DetalleRequisicion>(
      `${BASE}/detalles-requisicion-compra/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/detalles-requisicion-compra/${id}/`);
  },
};

// ── Solicitudes de Cotización (RFQ) ─────────────────────────────────────────

export const solicitudesCotizacionService = {
  getAll: async (params?: { estado?: string }): Promise<SolicitudCotizacion[]> => {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set('estado', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<SolicitudCotizacion> | SolicitudCotizacion[]>(
      `${BASE}/solicitudes-cotizacion/${query ? '?' + query : ''}`,
    );
    return toList<SolicitudCotizacion>(response);
  },

  getById: async (id: string): Promise<SolicitudCotizacion> =>
    get<SolicitudCotizacion>(`${BASE}/solicitudes-cotizacion/${id}/`),

  create: async (payload: SolicitudCotizacionPayload): Promise<SolicitudCotizacion> =>
    post<SolicitudCotizacion>(
      `${BASE}/solicitudes-cotizacion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: SolicitudCotizacionPayload): Promise<SolicitudCotizacion> =>
    patch<SolicitudCotizacion>(
      `${BASE}/solicitudes-cotizacion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/solicitudes-cotizacion/${id}/`);
  },
};

export const detallesSolicitudService = {
  getAll: async (params?: { solicitud?: string }): Promise<DetalleSolicitud[]> => {
    const response = await get<PaginatedResponse<DetalleSolicitud> | DetalleSolicitud[]>(
      `${BASE}/detalles-solicitud-cotizacion/`,
    );
    const lista = toList<DetalleSolicitud>(response);
    return params?.solicitud
      ? lista.filter((d) => d.id_solicitud_cotizacion === params.solicitud)
      : lista;
  },

  create: async (payload: DetalleSolicitudPayload): Promise<DetalleSolicitud> =>
    post<DetalleSolicitud>(
      `${BASE}/detalles-solicitud-cotizacion/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: DetalleSolicitudPayload): Promise<DetalleSolicitud> =>
    patch<DetalleSolicitud>(
      `${BASE}/detalles-solicitud-cotizacion/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/detalles-solicitud-cotizacion/${id}/`);
  },
};

// ── Ofertas de Proveedor ────────────────────────────────────────────────────

export const ofertasProveedorService = {
  /** Ofertas; filtrable por solicitud (client-side) y por estado (querystring). */
  getAll: async (params?: { solicitud?: string; estado?: string }): Promise<OfertaProveedor[]> => {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set('estado', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<OfertaProveedor> | OfertaProveedor[]>(
      `${BASE}/ofertas-proveedor/${query ? '?' + query : ''}`,
    );
    const lista = toList<OfertaProveedor>(response);
    return params?.solicitud
      ? lista.filter((o) => o.id_solicitud_cotizacion === params.solicitud)
      : lista;
  },

  getById: async (id: string): Promise<OfertaProveedor> =>
    get<OfertaProveedor>(`${BASE}/ofertas-proveedor/${id}/`),

  create: async (payload: OfertaProveedorPayload): Promise<OfertaProveedor> =>
    post<OfertaProveedor>(
      `${BASE}/ofertas-proveedor/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: OfertaProveedorPayload): Promise<OfertaProveedor> =>
    patch<OfertaProveedor>(
      `${BASE}/ofertas-proveedor/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/ofertas-proveedor/${id}/`);
  },
};

export const detallesOfertaService = {
  getAll: async (params?: { oferta?: string }): Promise<DetalleOferta[]> => {
    const response = await get<PaginatedResponse<DetalleOferta> | DetalleOferta[]>(
      `${BASE}/detalles-oferta-proveedor/`,
    );
    const lista = toList<DetalleOferta>(response);
    return params?.oferta ? lista.filter((d) => d.id_oferta === params.oferta) : lista;
  },

  create: async (payload: DetalleOfertaPayload): Promise<DetalleOferta> =>
    post<DetalleOferta>(
      `${BASE}/detalles-oferta-proveedor/`,
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: DetalleOfertaPayload): Promise<DetalleOferta> =>
    patch<DetalleOferta>(
      `${BASE}/detalles-oferta-proveedor/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/detalles-oferta-proveedor/${id}/`);
  },
};
