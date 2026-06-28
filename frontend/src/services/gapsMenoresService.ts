/**
 * Servicios "gaps menores": cuatro entidades con router backend operativo pero
 * sin pantalla propia. Cada bloque es un CRUD/flujo fino sobre su recurso:
 *
 *   1. Ubicaciones de almacén  — /almacenes/ubicaciones-almacen/   (CRUD puro)
 *   2. Movimientos internos de fondo — /tesoreria/movimientos-internos-fondo/ (CRUD; el
 *      backend genera los dos MovimientoCajaBanco al crear)
 *   3. Pagos de terceros (Zelle) — /finanzas/pagos-terceros/ (alta + acciones de
 *      ciclo de vida; NO se elimina, se anula)
 *   4. Pagos de contribuciones parafiscales — /fiscal/pagos-parafiscales/ (alta +
 *      acciones pagar/anular; NO se elimina, se anula)
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4). `id_empresa` lo inyecta
 * el backend (H-API-1), por eso no se envía en los payloads de alta.
 */
import { get, post, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ─────────────────────────────────────────────────────────────────────────────
// 1) Ubicaciones de almacén
// ─────────────────────────────────────────────────────────────────────────────

export type TipoUbicacion =
  | 'ESTANTERIA'
  | 'PISO'
  | 'REFRIGERADO'
  | 'CONGELADO'
  | 'EXTERIOR'
  | 'CUARENTENA'
  | 'DEVOLUCION'
  | 'PICKING'
  | 'RECEPCION'
  | 'DESPACHO';

export interface UbicacionAlmacen {
  id_ubicacion: string;
  id_empresa?: string;
  id_almacen: string;
  codigo_ubicacion: string;
  nombre_ubicacion: string;
  tipo_ubicacion: TipoUbicacion;
  pasillo: string | null;
  estante: string | null;
  nivel: string | null;
  posicion: string | null;
  capacidad_maxima: string | null;
  unidad_capacidad: string | null;
  temperatura_minima: string | null;
  temperatura_maxima: string | null;
  activo: boolean;
  requiere_autorizacion: boolean;
  observaciones: string | null;
  fecha_creacion?: string;
}

/**
 * Payload de alta/edición de ubicación (whitelist). El ViewSet de almacenes NO
 * usa `EmpresaInjectMixin` (igual que `AlmacenViewSet`): el contrato del módulo
 * `almacenes` exige que el cliente envíe `id_empresa` explícitamente.
 */
export interface UbicacionAlmacenPayload {
  id_empresa: string;
  id_almacen: string;
  codigo_ubicacion: string;
  nombre_ubicacion: string;
  tipo_ubicacion: TipoUbicacion;
  pasillo: string | null;
  estante: string | null;
  nivel: string | null;
  posicion: string | null;
  capacidad_maxima: string | null;
  unidad_capacidad: string | null;
  activo: boolean;
  requiere_autorizacion: boolean;
  observaciones: string | null;
}

const BASE_UBIC = '/almacenes/ubicaciones-almacen/';

export const ubicacionesAlmacenService = {
  getAll: async (params?: { almacen?: string }): Promise<UbicacionAlmacen[]> => {
    const qs = new URLSearchParams();
    if (params?.almacen) qs.set('id_almacen', params.almacen);
    const query = qs.toString();
    const response = await get<PaginatedResponse<UbicacionAlmacen> | UbicacionAlmacen[]>(
      `${BASE_UBIC}${query ? '?' + query : ''}`,
    );
    const lista = toList<UbicacionAlmacen>(response);
    // El backend filtra por empresa; reforzamos por almacén en cliente para que
    // cada almacén muestre solo sus ubicaciones.
    return params?.almacen ? lista.filter((u) => u.id_almacen === params.almacen) : lista;
  },

  create: async (payload: UbicacionAlmacenPayload): Promise<UbicacionAlmacen> =>
    post<UbicacionAlmacen>(BASE_UBIC, payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: UbicacionAlmacenPayload): Promise<UbicacionAlmacen> =>
    patch<UbicacionAlmacen>(`${BASE_UBIC}${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE_UBIC}${id}/`);
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// 2) Movimientos internos de fondo (transferencias entre cajas/cuentas)
// ─────────────────────────────────────────────────────────────────────────────

export interface MovimientoInternoFondo {
  id: number;
  caja_origen: string;
  caja_destino: string;
  monto: string;
  fecha?: string;
  descripcion: string | null;
  id_moneda: string | null;
  id_banco_origen: string | null;
  id_banco_destino: string | null;
  referencia_externa: string | null;
  usuario: number | null;
}

/** Payload de alta de movimiento interno (la fecha la fija el backend, auto_now_add). */
export interface MovimientoInternoFondoPayload {
  caja_origen: string;
  caja_destino: string;
  monto: string;
  descripcion: string | null;
  id_moneda: string | null;
  referencia_externa: string | null;
}

const BASE_MIF = '/tesoreria/movimientos-internos-fondo/';

export const movimientosInternosFondoService = {
  getAll: async (): Promise<MovimientoInternoFondo[]> => {
    const response = await get<PaginatedResponse<MovimientoInternoFondo> | MovimientoInternoFondo[]>(
      BASE_MIF,
    );
    return toList<MovimientoInternoFondo>(response);
  },

  create: async (payload: MovimientoInternoFondoPayload): Promise<MovimientoInternoFondo> =>
    post<MovimientoInternoFondo>(BASE_MIF, payload as unknown as Record<string, unknown>),

  remove: async (id: string | number): Promise<void> => {
    await del<void>(`${BASE_MIF}${id}/`);
  },
};

/** Cajas virtuales (selector de origen/destino). Devuelve id_caja + nombre. */
export interface CajaOption {
  id_caja: string;
  nombre: string;
  moneda?: string | null;
  activa?: boolean;
}

export async function fetchCajasEmpresa(empresa: string): Promise<CajaOption[]> {
  const response = await get<PaginatedResponse<CajaOption> | CajaOption[]>(
    `/finanzas/cajas/?empresa=${empresa}`,
  );
  return toList<CajaOption>(response);
}

// ─────────────────────────────────────────────────────────────────────────────
// 3) Pagos de terceros (Zelle)
// ─────────────────────────────────────────────────────────────────────────────

export type EstadoPagoTercero =
  | 'pendiente'
  | 'abonado'
  | 'reintegro_pendiente'
  | 'reintegrado'
  | 'anulado';

export interface PagoTercero {
  id_pago_tercero: string;
  id_empresa?: string;
  id_proveedor: string | null;
  proveedor_nombre: string | null;
  id_moneda: string;
  moneda_codigo: string | null;
  monto: string;
  comision: string | null;
  referencia_zelle: string | null;
  fecha: string;
  concepto: string | null;
  estado: EstadoPagoTercero;
  id_abono_cxp: string | null;
  id_cxc_reintegro: string | null;
  fecha_creacion?: string;
}

/** Payload de alta (estado/comisión/FKs de documentos son read-only en el backend). */
export interface PagoTerceroPayload {
  id_proveedor: string | null;
  id_moneda: string;
  monto: string;
  referencia_zelle: string | null;
  fecha: string;
  concepto: string | null;
}

const BASE_PT = '/finanzas/pagos-terceros/';

export const pagosTercerosService = {
  getAll: async (params?: { estado?: string; proveedor?: string }): Promise<PagoTercero[]> => {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set('estado', params.estado);
    if (params?.proveedor) qs.set('proveedor', params.proveedor);
    const query = qs.toString();
    const response = await get<PaginatedResponse<PagoTercero> | PagoTercero[]>(
      `${BASE_PT}${query ? '?' + query : ''}`,
    );
    return toList<PagoTercero>(response);
  },

  create: async (payload: PagoTerceroPayload): Promise<PagoTercero> =>
    post<PagoTercero>(BASE_PT, payload as unknown as Record<string, unknown>),

  /** pendiente → abonado: aplica el cobro como abono a una CxP del proveedor. */
  abonar: async (id: string, cxp: string, descripcion?: string): Promise<PagoTercero> =>
    post<PagoTercero>(`${BASE_PT}${id}/abonar/`, { cxp, descripcion: descripcion ?? '' }),

  /** pendiente → reintegro_pendiente: emite una CxC contra el proveedor. */
  solicitarReintegro: async (
    id: string,
    body?: { comision?: string; fecha_vencimiento?: string; descripcion?: string },
  ): Promise<PagoTercero> =>
    post<PagoTercero>(`${BASE_PT}${id}/solicitar-reintegro/`, { ...(body ?? {}) }),

  /** fija el proveedor de un pago pendiente. */
  asociarProveedor: async (id: string, proveedor: string): Promise<PagoTercero> =>
    post<PagoTercero>(`${BASE_PT}${id}/asociar-proveedor/`, { proveedor }),

  /** reintegro_pendiente → reintegrado (confirmación manual). */
  marcarReintegrado: async (id: string): Promise<PagoTercero> =>
    post<PagoTercero>(`${BASE_PT}${id}/marcar-reintegrado/`, {}),

  /** pendiente → anulado. */
  anular: async (id: string): Promise<PagoTercero> =>
    post<PagoTercero>(`${BASE_PT}${id}/anular/`, {}),
};

// ─────────────────────────────────────────────────────────────────────────────
// 4) Pagos de contribuciones parafiscales (IVSS / INCES / FAOV)
// ─────────────────────────────────────────────────────────────────────────────

export type EstadoPagoParafiscal = 'pendiente' | 'pagado' | 'anulado';

export interface PagoParafiscal {
  id_pago_parafiscal: string;
  id_empresa?: string;
  contribucion: string;
  contribucion_codigo: string | null;
  contribucion_nombre: string | null;
  periodo_año: number;
  periodo_mes: number;
  periodo: string;
  monto: string;
  id_moneda: string;
  moneda_codigo: string | null;
  referencia: string | null;
  estado: EstadoPagoParafiscal;
  fecha_pago: string | null;
  id_pago: string | null;
  fecha_creacion?: string;
}

/** Payload de alta (estado/fecha_pago/id_pago/referencia los fija la acción `pagar`). */
export interface PagoParafiscalPayload {
  contribucion: string;
  periodo_año: number;
  periodo_mes: number;
  monto: string;
  id_moneda: string;
}

/** Body de la acción `pagar`: exactamente un origen de fondos (caja XOR cuenta). */
export interface PagarParafiscalBody {
  metodo_pago: string;
  caja?: string;
  cuenta_bancaria?: string;
  referencia?: string;
  fecha_pago?: string;
}

const BASE_PP = '/fiscal/pagos-parafiscales/';

export const pagosParafiscalesService = {
  getAll: async (params?: {
    estado?: string;
    contribucion?: string;
    periodo_año?: string | number;
    periodo_mes?: string | number;
  }): Promise<PagoParafiscal[]> => {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set('estado', params.estado);
    if (params?.contribucion) qs.set('contribucion', params.contribucion);
    if (params?.periodo_año) qs.set('periodo_año', String(params.periodo_año));
    if (params?.periodo_mes) qs.set('periodo_mes', String(params.periodo_mes));
    const query = qs.toString();
    const response = await get<PaginatedResponse<PagoParafiscal> | PagoParafiscal[]>(
      `${BASE_PP}${query ? '?' + query : ''}`,
    );
    return toList<PagoParafiscal>(response);
  },

  create: async (payload: PagoParafiscalPayload): Promise<PagoParafiscal> =>
    post<PagoParafiscal>(BASE_PP, payload as unknown as Record<string, unknown>),

  /** pendiente → pagado: egreso en libro de caja + asiento PAGO_PARAFISCAL. */
  pagar: async (id: string, body: PagarParafiscalBody): Promise<PagoParafiscal> =>
    post<PagoParafiscal>(`${BASE_PP}${id}/pagar/`, { ...body }),

  /** pendiente → anulado (libera el período para re-declarar). */
  anular: async (id: string): Promise<PagoParafiscal> =>
    post<PagoParafiscal>(`${BASE_PP}${id}/anular/`, {}),
};
