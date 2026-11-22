import { IDEMPOTENCY_HEADER, newIdempotencyKey } from '../lib/idempotency';
import type { PaginatedResponse } from '../utils/api';
import { get, post } from './api';

export type TipoDocumentoConciliacion =
  | 'CUENTA_POR_COBRAR'
  | 'FACTURA_VENTA'
  | 'CUENTA_POR_PAGAR'
  | 'FACTURA_COMPRA';

export interface ContactoResumenConciliacion {
  id_contacto: string;
  nombre: string;
  rif: string;
  es_cliente: boolean;
  es_proveedor: boolean;
}

export interface SaldoMonedaConciliacion {
  moneda_id: string;
  codigo_iso: string;
  simbolo: string;
  /** Montos serializados como strings decimales — nunca number (R-CODE-4). */
  INGRESO: string;
  EGRESO: string;
  cantidad_pagos: number;
}

export interface SaldoAFavorResumen {
  total_por_moneda: Record<string, SaldoMonedaConciliacion>;
  total_pagos_con_saldo: number;
}

export interface PagoDisponibleConciliacion {
  id_pago: string;
  fecha_pago: string;
  tipo_operacion: 'INGRESO' | 'EGRESO' | string;
  monto: string;
  saldo_disponible: string;
  moneda_codigo: string;
  referencia: string;
  tasa: string;
}

export interface ObligacionAbiertaConciliacion {
  tipo_documento: TipoDocumentoConciliacion | string;
  id_documento: string;
  numero_documento: string;
  fecha_emision: string;
  fecha_vencimiento: string;
  monto_total: string;
  saldo_pendiente: string;
  moneda_codigo: string;
  estado: string;
}

export interface AsignacionPagoItem {
  id_asignacion: string;
  id_empresa: string;
  id_contacto: string;
  contacto_nombre: string;
  id_pago: string;
  pago_referencia: string;
  tipo_documento: TipoDocumentoConciliacion | string;
  id_documento: string;
  id_cxc: string | null;
  id_cxp: string | null;
  id_factura_venta: string | null;
  id_factura_compra: string | null;
  id_abono_cxc: string | null;
  id_abono_cxp: string | null;
  monto_asignado_pago: string;
  monto_asignado_documento: string;
  id_moneda_documento: string;
  moneda_documento_codigo: string;
  tasa_aplicada: string;
  diferencia_cambiaria: string;
  tipo_diferencia: 'NINGUNA' | 'GANANCIA' | 'PERDIDA' | string;
  estado: 'ACTIVA' | 'REVERTIDA' | string;
  fecha_aplicacion: string;
  fecha_reversion: string | null;
  motivo_reversion: string | null;
  id_asiento: string | null;
  id_asiento_reversion: string | null;
  id_usuario_registro: string | null;
  referencia_externa: string;
  activo: boolean;
  fecha_creacion: string;
}

export interface EstadoConciliacionContacto {
  contacto: ContactoResumenConciliacion;
  saldo_a_favor: SaldoAFavorResumen;
  pagos_disponibles: PagoDisponibleConciliacion[];
  obligaciones_abiertas: ObligacionAbiertaConciliacion[];
  asignaciones_activas: AsignacionPagoItem[];
}

export interface LineaConciliacionInput {
  tipo_documento: TipoDocumentoConciliacion | string;
  id_documento: string;
  /** Monto asignado expresado en la moneda del pago (string decimal). */
  monto_asignado_pago: string;
  monto_asignado_documento?: string | null;
  tasa_aplicada?: string | null;
  tasa_original?: string | null;
  tasa_liquidacion?: string | null;
  moneda_documento?: string;
  referencia_externa?: string;
}

export interface ConciliarDocumentosPayload {
  asignaciones: LineaConciliacionInput[];
  descripcion?: string;
  generar_asiento?: boolean;
}

export interface CrearAsignacionPagoPayload extends ConciliarDocumentosPayload {
  pago: string;
}

export interface ConciliarDocumentosResponse {
  pago_id: string;
  saldo_disponible: string;
  asignaciones: AsignacionPagoItem[];
}

export interface PropuestaDistribucionItem {
  tipo_documento: TipoDocumentoConciliacion | string;
  id_documento: string;
  referencia: string;
  fecha_emision: string;
  fecha_vencimiento: string;
  moneda_documento: string;
  moneda_documento_codigo: string;
  saldo_pendiente_documento: string;
  tasa_aplicada: string;
  monto_asignado_pago: string;
  monto_asignado_documento: string;
}

export interface OmitidaSinTasaItem {
  tipo_documento: string;
  id_documento: string;
  moneda_codigo: string;
  motivo: string;
}

export interface SugerirDistribucionResponse {
  pago_id: string;
  saldo_disponible: string;
  propuestas: PropuestaDistribucionItem[];
  total_a_aplicar: string;
  saldo_a_favor_resultante: string;
  omitidas_sin_tasa: OmitidaSinTasaItem[];
}

export interface ListarAsignacionesFilters {
  pago?: string;
  contacto?: string;
  tipo_documento?: string;
  id_documento?: string;
  estado?: 'ACTIVA' | 'REVERTIDA' | string;
  page?: number;
}

export const conciliacionPagosService = {
  obtenerEstadoConciliacionContacto: (
    idContacto: string,
    tipoOperacion?: 'INGRESO' | 'EGRESO' | '',
  ): Promise<EstadoConciliacionContacto> => {
    const qs = tipoOperacion ? `?tipo_operacion=${encodeURIComponent(tipoOperacion)}` : '';
    return get<EstadoConciliacionContacto>(
      `/finanzas/contactos/${encodeURIComponent(idContacto)}/estado-conciliacion/${qs}`,
    );
  },

  sugerirDistribucionPago: (
    idPago: string,
    tipoDocumento?: TipoDocumentoConciliacion | '',
  ): Promise<SugerirDistribucionResponse> => {
    const qs = tipoDocumento ? `?tipo_documento=${encodeURIComponent(tipoDocumento)}` : '';
    return get<SugerirDistribucionResponse>(
      `/finanzas/pagos/${encodeURIComponent(idPago)}/sugerir-distribucion/${qs}`,
    );
  },

  conciliarPagoDocumentos: (
    idPago: string,
    payload: ConciliarDocumentosPayload,
    idempotencyKey?: string,
  ): Promise<ConciliarDocumentosResponse> =>
    post<ConciliarDocumentosResponse>(
      `/finanzas/pagos/${encodeURIComponent(idPago)}/conciliar-documentos/`,
      payload as unknown as Record<string, unknown>,
      {
        headers: {
          [IDEMPOTENCY_HEADER]: idempotencyKey ?? newIdempotencyKey(),
        },
      },
    ),

  crearAsignacionPago: (
    payload: CrearAsignacionPagoPayload,
    idempotencyKey?: string,
  ): Promise<ConciliarDocumentosResponse> =>
    post<ConciliarDocumentosResponse>(
      '/finanzas/asignaciones-pago/',
      payload as unknown as Record<string, unknown>,
      {
        headers: {
          [IDEMPOTENCY_HEADER]: idempotencyKey ?? newIdempotencyKey(),
        },
      },
    ),

  revertirAsignacionPago: (
    idAsignacion: string,
    motivo = '',
    idempotencyKey?: string,
  ): Promise<AsignacionPagoItem> =>
    post<AsignacionPagoItem>(
      `/finanzas/asignaciones-pago/${encodeURIComponent(idAsignacion)}/revertir/`,
      { motivo },
      {
        headers: {
          [IDEMPOTENCY_HEADER]: idempotencyKey ?? newIdempotencyKey(),
        },
      },
    ),

  listarAsignacionesPago: (
    filters: ListarAsignacionesFilters = {},
  ): Promise<PaginatedResponse<AsignacionPagoItem> | AsignacionPagoItem[]> => {
    const params = new URLSearchParams();
    if (filters.pago) params.set('pago', filters.pago);
    if (filters.contacto) params.set('contacto', filters.contacto);
    if (filters.tipo_documento) params.set('tipo_documento', filters.tipo_documento);
    if (filters.id_documento) params.set('id_documento', filters.id_documento);
    if (filters.estado) params.set('estado', filters.estado);
    if (filters.page) params.set('page', String(filters.page));
    const qs = params.toString();
    return get<PaginatedResponse<AsignacionPagoItem> | AsignacionPagoItem[]>(
      `/finanzas/asignaciones-pago/${qs ? `?${qs}` : ''}`,
    );
  },
};
