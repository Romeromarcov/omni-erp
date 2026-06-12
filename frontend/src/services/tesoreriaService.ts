/**
 * Servicio de Tesorería (workstream F) — movimientos bancarios (con import CSV),
 * conciliación bancaria y operaciones de cambio de divisa.
 *
 * Endpoints del backend (`apps/tesoreria`):
 *   GET/POST /tesoreria/movimientos-bancarios/?cuenta=&estado=
 *   POST     /tesoreria/movimientos-bancarios/importar-csv/   (multipart)
 *   POST     /tesoreria/movimientos-bancarios/conciliar-auto/
 *   GET/POST /tesoreria/conciliaciones-bancarias/  ·  POST /{id}/cerrar/
 *   GET/POST /tesoreria/operaciones-cambio-divisa/
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 * El POST de cambio de divisa puede responder 422 si la contabilidad está
 * activa sin mapeo CAMBIO_DIVISA (R-CODE-11 / CTF-013).
 */
import { get, post, postForm } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type EstadoMovBancario = 'PENDIENTE' | 'CONCILIADO' | 'DESCARTADO';
export type EstadoConciliacion = 'ABIERTA' | 'CERRADA';

export interface MovimientoBancario {
  id: string;
  id_empresa: string;
  id_cuenta_bancaria: string;
  fecha_mov: string;
  descripcion: string;
  tipo: 'DEBITO' | 'CREDITO' | string;
  /** Monto como string decimal (R-CODE-4). */
  monto: string;
  referencia: string;
  estado: EstadoMovBancario | string;
  id_pago_conciliado: string | null;
  origen: 'CSV' | 'MANUAL' | 'API' | string;
  fecha_creacion: string;
}

export interface ImportarCsvResultado {
  importados?: number;
  omitidos?: number;
  errores?: string[];
  [key: string]: unknown;
}

export interface ConciliarAutoResultado {
  conciliados?: number;
  pendientes?: number;
  [key: string]: unknown;
}

export interface ConciliacionBancaria {
  id: string;
  id_empresa: string;
  id_cuenta_bancaria: string;
  periodo_inicio: string;
  periodo_fin: string;
  /** Saldos y diferencia como string decimal (R-CODE-4). */
  saldo_banco: string;
  saldo_libro: string;
  diferencia: string;
  estado: EstadoConciliacion | string;
  movimientos_conciliados: number;
  movimientos_pendientes: number;
  realizada_por: string | null;
  fecha_creacion: string;
  fecha_cierre: string | null;
  observaciones: string;
}

export interface CrearConciliacionPayload {
  id_empresa: string;
  id_cuenta_bancaria: string;
  periodo_inicio: string;
  periodo_fin: string;
  saldo_banco: string;
  saldo_libro: string;
  observaciones?: string;
}

export interface OperacionCambioDivisa {
  id: number;
  empresa: string;
  numero_operacion: string;
  fecha_operacion: string;
  tipo_operacion: 'COMPRA' | 'VENTA' | string;
  moneda_origen: string;
  moneda_destino: string;
  /** Montos y tasa como string decimal (R-CODE-4). */
  monto_origen: string;
  tasa_cambio: string;
  monto_destino: string;
  comision: string;
  caja_origen: string | null;
  caja_destino: string | null;
  banco_origen: string | null;
  banco_destino: string | null;
  metodo_pago_origen: string | null;
  metodo_pago_destino: string | null;
  referencia_transaccion_origen: string | null;
  referencia_transaccion_destino: string | null;
  observaciones: string | null;
  activo: boolean;
  fecha_creacion: string;
}

export interface CrearOperacionCambioPayload {
  empresa: string;
  numero_operacion: string;
  fecha_operacion: string;
  tipo_operacion: string;
  moneda_origen: string;
  moneda_destino: string;
  monto_origen: string;
  tasa_cambio: string;
  monto_destino: string;
  comision?: string;
  caja_origen?: string | null;
  caja_destino?: string | null;
  banco_origen?: string | null;
  banco_destino?: string | null;
  metodo_pago_origen: string;
  metodo_pago_destino: string;
  referencia_transaccion_origen?: string;
  referencia_transaccion_destino?: string;
  observaciones?: string;
}

/** Cuenta bancaria (finanzas) — solo los campos que usan los selectores. */
export interface CuentaBancariaOption {
  id_cuenta_bancaria: string;
  nombre_banco: string;
  numero_cuenta: string;
  activo: boolean;
}

export interface MovimientosFiltros {
  cuenta?: string;
  estado?: string;
}

const BASE = '/tesoreria';

function paginada<T>(response: PaginatedResponse<T> | T[]): PaginatedResponse<T> {
  if (response && typeof response === 'object' && 'results' in response) return response;
  const arr = toList<T>(response);
  return { count: arr.length, next: null, previous: null, results: arr };
}

// ── Service ────────────────────────────────────────────────────────────────

export const tesoreriaService = {
  /** Cuentas bancarias de la empresa (selector de filtros e import CSV). */
  getCuentasBancarias: async (empresaId: string): Promise<CuentaBancariaOption[]> => {
    const response = await get<CuentaBancariaOption[] | PaginatedResponse<CuentaBancariaOption>>(
      `/finanzas/cuentas-bancarias-empresa/?empresa=${empresaId}`,
    );
    return toList<CuentaBancariaOption>(response);
  },

  // ── Movimientos bancarios ────────────────────────────────────────────────

  getMovimientosBancariosPaginated: async (
    page = 1,
    pageSize = 20,
    filtros: MovimientosFiltros = {},
  ): Promise<PaginatedResponse<MovimientoBancario>> => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filtros.cuenta) params.set('cuenta', filtros.cuenta);
    if (filtros.estado) params.set('estado', filtros.estado);
    const response = await get<PaginatedResponse<MovimientoBancario> | MovimientoBancario[]>(
      `${BASE}/movimientos-bancarios/?${params.toString()}`,
    );
    return paginada(response);
  },

  /** Importa un extracto CSV (fecha,descripcion,tipo,monto,referencia). */
  importarCsv: async (
    empresaId: string,
    cuentaBancariaId: string,
    archivo: File,
  ): Promise<ImportarCsvResultado> => {
    const form = new FormData();
    form.set('empresa', empresaId);
    form.set('cuenta_bancaria', cuentaBancariaId);
    form.set('archivo', archivo);
    return postForm<ImportarCsvResultado>(`${BASE}/movimientos-bancarios/importar-csv/`, form);
  },

  /** Matching automático movimiento ↔ pago por monto/fecha (tolerancia en días). */
  conciliarAuto: async (cuentaBancariaId: string, toleranciaDias = 3): Promise<ConciliarAutoResultado> => {
    return post<ConciliarAutoResultado>(`${BASE}/movimientos-bancarios/conciliar-auto/`, {
      cuenta_bancaria: cuentaBancariaId,
      tolerancia_dias: toleranciaDias,
    });
  },

  // ── Conciliaciones bancarias ─────────────────────────────────────────────

  getConciliacionesPaginated: async (
    page = 1,
    pageSize = 20,
  ): Promise<PaginatedResponse<ConciliacionBancaria>> => {
    const response = await get<PaginatedResponse<ConciliacionBancaria> | ConciliacionBancaria[]>(
      `${BASE}/conciliaciones-bancarias/?page=${page}&page_size=${pageSize}`,
    );
    return paginada(response);
  },

  getConciliacion: async (id: string): Promise<ConciliacionBancaria> => {
    return get<ConciliacionBancaria>(`${BASE}/conciliaciones-bancarias/${id}/`);
  },

  crearConciliacion: async (payload: CrearConciliacionPayload): Promise<ConciliacionBancaria> => {
    return post<ConciliacionBancaria>(
      `${BASE}/conciliaciones-bancarias/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  cerrarConciliacion: async (id: string): Promise<ConciliacionBancaria> => {
    return post<ConciliacionBancaria>(`${BASE}/conciliaciones-bancarias/${id}/cerrar/`, {});
  },

  // ── Operaciones de cambio de divisa ──────────────────────────────────────

  getOperacionesCambioPaginated: async (
    page = 1,
    pageSize = 20,
  ): Promise<PaginatedResponse<OperacionCambioDivisa>> => {
    const response = await get<PaginatedResponse<OperacionCambioDivisa> | OperacionCambioDivisa[]>(
      `${BASE}/operaciones-cambio-divisa/?page=${page}&page_size=${pageSize}`,
    );
    return paginada(response);
  },

  /**
   * Crea la operación de cambio (doble registro + asiento CAMBIO_DIVISA en una
   * transacción). Si la contabilidad está activa sin mapeo CAMBIO_DIVISA el
   * backend responde 422 y NADA queda registrado.
   */
  crearOperacionCambio: async (payload: CrearOperacionCambioPayload): Promise<OperacionCambioDivisa> => {
    return post<OperacionCambioDivisa>(
      `${BASE}/operaciones-cambio-divisa/`,
      payload as unknown as Record<string, unknown>,
    );
  },
};
