import { post, get, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

export type TipoCuenta = 'corriente' | 'ahorro';

/**
 * Cuenta bancaria de la empresa para banca electrónica. El `saldo_actual` viaja
 * como string para no perder la precisión del DecimalField del backend
 * (R-CODE-4). La isolación multi-tenant la hace el backend
 * (get_empresas_visible + filtro por `empresa`); reforzamos con `?empresa=`.
 */
export interface CuentaBancariaEmpresa {
  id: string;
  banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuenta;
  moneda: string;
  saldo_actual: string;
  activa: boolean;
  empresa: string;
  referencia_externa?: string | null;
  documento_json?: Record<string, unknown> | null;
}

/**
 * Payload de escritura: whitelist explícita de campos editables (CTF-005,
 * defensa en profundidad CWE-915). El `saldo_actual` viaja como string
 * (R-CODE-4); la unicidad del número de cuenta la valida el backend.
 */
export interface CuentaBancariaEmpresaPayload {
  empresa: string;
  banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuenta;
  moneda: string;
  saldo_actual: string;
  activa: boolean;
}

const BASE = '/banca-electronica/cuentas-bancarias-empresa/';

// ── CRUD ──────────────────────────────────────────────────────────────────────

export const cuentasBancariasEmpresaService = {
  getAll: async (params?: { empresa?: string }): Promise<CuentaBancariaEmpresa[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    const query = qs.toString();
    const response = await get<PaginatedResponse<CuentaBancariaEmpresa> | CuentaBancariaEmpresa[]>(
      `${BASE}${query ? '?' + query : ''}`,
    );
    return toList<CuentaBancariaEmpresa>(response);
  },

  getById: async (id: string): Promise<CuentaBancariaEmpresa> => {
    return get<CuentaBancariaEmpresa>(`${BASE}${id}/`);
  },

  create: async (payload: CuentaBancariaEmpresaPayload): Promise<CuentaBancariaEmpresa> =>
    post<CuentaBancariaEmpresa>(BASE, payload as unknown as Record<string, unknown>),

  update: async (
    id: string,
    payload: CuentaBancariaEmpresaPayload,
  ): Promise<CuentaBancariaEmpresa> =>
    patch<CuentaBancariaEmpresa>(`${BASE}${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${BASE}${id}/`);
  },
};
