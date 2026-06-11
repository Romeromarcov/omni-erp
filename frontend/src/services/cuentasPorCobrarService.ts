import { get, post } from './api';
import type { PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export interface CuentaPorCobrar {
  id: number;
  empresa: string;
  cliente: string | null;
  cliente_nombre: string | null;
  cliente_ref: string | null;
  /** Montos como string decimal — nunca number (R-CODE-4). */
  monto: string;
  saldo_pendiente: string;
  fecha_emision: string;
  fecha_vencimiento: string;
  estado: 'pendiente' | 'parcial' | 'pagada' | 'vencida' | string;
  referencia_externa?: string | null;
  tipo_operacion?: string | null;
  descripcion?: string | null;
}

export interface AbonoCxC {
  id: number;
  cuenta_por_cobrar: number;
  monto: string;
  descripcion: string;
  fecha_abono?: string;
}

export interface AbonoCxCPayload {
  cuenta_por_cobrar: number;
  /** String decimal (contrato P0-2) — el backend lo parsea con Decimal. */
  monto: string;
  descripcion?: string;
}

// ── Service ────────────────────────────────────────────────────────────────

export const cuentasPorCobrarService = {
  getAllPaginated: async (page = 1, pageSize = 20): Promise<PaginatedResponse<CuentaPorCobrar>> => {
    const response = await get<PaginatedResponse<CuentaPorCobrar> | CuentaPorCobrar[]>(
      `/cxc/cuentas-por-cobrar/?page=${page}&page_size=${pageSize}`,
    );
    if (response && typeof response === 'object' && 'results' in response) {
      return response;
    }
    const arr = Array.isArray(response) ? response : [];
    return { count: arr.length, next: null, previous: null, results: arr };
  },

  /**
   * Registra un abono (contrato P0-2): POST /api/cxc/abonos-cxc/ con
   * {cuenta_por_cobrar, monto, descripcion}. El backend valida monto > 0 y
   * tope de saldo, y actualiza el estado de la CxC de forma atómica.
   */
  crearAbono: async (payload: AbonoCxCPayload): Promise<AbonoCxC> => {
    return post<AbonoCxC>('/cxc/abonos-cxc/', payload as unknown as Record<string, unknown>);
  },
};
