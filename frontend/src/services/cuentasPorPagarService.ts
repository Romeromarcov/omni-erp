/**
 * Servicio de Cuentas por Pagar (CxP) — saldos, aging y abonos a proveedores.
 *
 * Endpoints del backend (`apps/cuentas_por_pagar`, base /api/cuentas-por-pagar/):
 *   GET  /cuentas-por-pagar/cuentas-por-pagar/                — lista paginada (?estado=&proveedor=&empresa=)
 *   GET  /cuentas-por-pagar/cuentas-por-pagar/aging/?empresa= — antigüedad de saldos por bucket
 *   POST /cuentas-por-pagar/cuentas-por-pagar/{id}/abonar/    — registra abono (Idempotency-Key, PR #86)
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { fetcher, get } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type EstadoCxP = 'PENDIENTE' | 'PAGADA' | 'ANULADA' | 'VENCIDA' | 'PARCIAL';

export interface CuentaPorPagar {
  id_cxp: string;
  id_empresa: string;
  id_proveedor: string;
  id_factura_compra: string | null;
  referencia_externa?: string | null;
  tipo_operacion?: string | null;
  fecha_cierre_estimada?: string | null;
  /** Montos como string decimal (R-CODE-4). */
  monto_total: string;
  monto_pendiente: string;
  fecha_emision: string;
  fecha_vencimiento: string;
  estado: EstadoCxP | string;
  observaciones: string | null;
  activo: boolean;
  fecha_creacion: string;
}

/** Bucket del aging: monto (string decimal) + cantidad de documentos. */
export interface AgingBucketCxP {
  monto: string;
  cantidad: number;
  [key: string]: string | number;
}

export interface AgingCxPResponse {
  empresa_id: string;
  corriente: AgingBucketCxP;
  dias_1_30: AgingBucketCxP;
  dias_31_60: AgingBucketCxP;
  dias_61_90: AgingBucketCxP;
  dias_90_mas: AgingBucketCxP;
  /** String decimal (R-CODE-4). */
  total_general: string;
}

export interface AbonarCxPPayload {
  /** String decimal (R-CODE-4); el backend lo parsea con Decimal. */
  monto: string;
  descripcion?: string;
}

export interface AbonarCxPResponse {
  abono_id: string;
  cxp_id: string;
  /** Strings decimales (R-CODE-4). */
  monto_abonado: string;
  monto_pendiente: string;
  estado_cxp: string;
}

export interface FiltrosCxP {
  estado?: string;
  proveedor?: string;
}

const BASE = '/cuentas-por-pagar/cuentas-por-pagar';

// ── Service ────────────────────────────────────────────────────────────────

export const cuentasPorPagarService = {
  /** Lista paginada de CxP, ordenada por vencimiento en el backend. */
  getAllPaginated: async (
    page = 1,
    pageSize = 20,
    filtros: FiltrosCxP = {},
  ): Promise<PaginatedResponse<CuentaPorPagar>> => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filtros.estado) params.set('estado', filtros.estado);
    if (filtros.proveedor) params.set('proveedor', filtros.proveedor);
    const response = await get<PaginatedResponse<CuentaPorPagar> | CuentaPorPagar[]>(
      `${BASE}/?${params.toString()}`,
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response;
    }
    const arr = toList<CuentaPorPagar>(response);
    return { count: arr.length, next: null, previous: null, results: arr };
  },

  /** Aging de saldos CxP por empresa (buckets con montos string decimal). */
  getAging: async (empresaId: string): Promise<AgingCxPResponse> => {
    return get<AgingCxPResponse>(`${BASE}/aging/?empresa=${encodeURIComponent(empresaId)}`);
  },

  /**
   * Registra un abono contra la CxP enviando la cabecera `Idempotency-Key`
   * (PR #86): un reintento del MISMO intento de submit reúsa la clave y el
   * backend devuelve el resultado original sin duplicar el abono. Un intento
   * nuevo del usuario debe generar una clave nueva (UUID por operación).
   */
  abonar: async (
    cxpId: string,
    payload: AbonarCxPPayload,
    idempotencyKey: string,
  ): Promise<AbonarCxPResponse> => {
    return fetcher<AbonarCxPResponse>(`${BASE}/${cxpId}/abonar/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(payload),
    });
  },
};
