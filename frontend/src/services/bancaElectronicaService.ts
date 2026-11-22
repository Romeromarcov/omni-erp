import { del, fetchBlob, get, patch, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos de Cuentas Bancarias (maestro canónico en apps/finanzas) ───────────

export type TipoCuenta = 'CORRIENTE' | 'AHORRO' | 'CREDITO';

/**
 * Cuenta bancaria de la empresa en el maestro canónico de `finanzas`.
 * `saldo_actual` viaja como string decimal para preservar precisión (R-CODE-4).
 */
export interface CuentaBancariaEmpresa {
  id_cuenta_bancaria: string;
  id_empresa: string;
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuenta;
  id_moneda: string;
  moneda_codigo_iso?: string;
  saldo_actual: string;
  activo: boolean;
  fecha_creacion?: string;
  metodos_pago?: string[];
  monedas?: string[];
}

export interface CuentaBancariaEmpresaPayload {
  id_empresa: string;
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuenta;
  id_moneda: string;
  saldo_actual: string;
  activo: boolean;
}

// ── Tipos de Lotes de Pago VE y Validadores (apps/banca_electronica) ────────

export type TipoLotePago = 'PROVEEDORES' | 'NOMINA';
export type FormatoBancoVE = 'BANESCO_TXT' | 'MERCANTIL_TXT' | 'BDV_TXT' | 'GENERICO_CSV';
export type EstadoLotePago = 'BORRADOR' | 'GENERADO' | 'ENVIADO' | 'PROCESADO' | 'ANULADO';

export interface DetalleLotePagoBancario {
  id_detalle: string;
  id_lote_pago: string;
  id_pago: string | null;
  id_nomina: string | null;
  beneficiario_nombre: string;
  beneficiario_identificacion: string;
  cuenta_destino: string;
  banco_destino: string;
  monto: string;
  referencia_linea: string;
  concepto: string;
}

export interface LotePagoBancario {
  id_lote_pago: string;
  id_empresa: string;
  empresa_nombre: string;
  id_cuenta_bancaria: string;
  cuenta_bancaria_nombre: string;
  cuenta_bancaria_numero: string;
  tipo_lote: TipoLotePago;
  formato_banco: FormatoBancoVE;
  referencia_lote: string;
  fecha_valor: string;
  estado: EstadoLotePago;
  id_proceso_nomina: string | null;
  total_registros: number;
  monto_total: string;
  sha256_archivo: string;
  nombre_archivo: string;
  generado_por: string | null;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
  detalles?: DetalleLotePagoBancario[];
}

export interface GenerarLoteProveedoresPayload {
  id_empresa?: string;
  id_cuenta_bancaria: string;
  pagos_ids: string[];
  formato_banco: FormatoBancoVE;
  fecha_valor: string;
  referencia_lote?: string;
  cuentas_destino_override?: Record<string, string>;
}

export interface GenerarLoteNominaPayload {
  id_empresa?: string;
  id_cuenta_bancaria: string;
  id_proceso_nomina: string;
  formato_banco: FormatoBancoVE;
  fecha_valor: string;
  referencia_lote?: string;
  cuentas_empleados?: Record<string, string>;
}

export interface ValidarCuentaVeResponse {
  valida: boolean;
  numero_normalizado: string;
  codigo_banco: string | null;
  banco_nombre: string | null;
  errores: string[];
}

export interface ValidarReferenciaPayload {
  id_empresa?: string;
  id_cuenta_bancaria?: string;
  referencia: string;
  excluir_pago_id?: string;
}

export interface CoincidenciaReferencia {
  origen: string;
  id: string;
  detalle: string;
}

export interface ValidarReferenciaResponse {
  duplicada: boolean;
  referencia_normalizada: string;
  coincidencias: CoincidenciaReferencia[];
}

const CUENTAS_BASE = '/finanzas/cuentas-bancarias-empresa/';
const LOTES_BASE = '/banca-electronica/lotes-pago/';

// ── Servicio maestro canónico de cuentas bancarias (finanzas) ───────────────

export const cuentasBancariasEmpresaService = {
  getAll: async (params?: { empresa?: string }): Promise<CuentaBancariaEmpresa[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    const query = qs.toString();
    const response = await get<PaginatedResponse<CuentaBancariaEmpresa> | CuentaBancariaEmpresa[]>(
      `${CUENTAS_BASE}${query ? '?' + query : ''}`,
    );
    return toList<CuentaBancariaEmpresa>(response);
  },

  getById: async (id: string): Promise<CuentaBancariaEmpresa> => {
    return get<CuentaBancariaEmpresa>(`${CUENTAS_BASE}${id}/`);
  },

  create: async (payload: CuentaBancariaEmpresaPayload): Promise<CuentaBancariaEmpresa> =>
    post<CuentaBancariaEmpresa>(CUENTAS_BASE, payload as unknown as Record<string, unknown>),

  update: async (
    id: string,
    payload: Partial<CuentaBancariaEmpresaPayload>,
  ): Promise<CuentaBancariaEmpresa> =>
    patch<CuentaBancariaEmpresa>(`${CUENTAS_BASE}${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`${CUENTAS_BASE}${id}/`);
  },
};

// ── Servicio operativo VE: Lotes de pago y validadores ──────────────────────

export const lotesPagoBancarioService = {
  getAll: async (params?: {
    empresa?: string;
    tipo_lote?: TipoLotePago | string;
    estado?: EstadoLotePago | string;
  }): Promise<LotePagoBancario[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.tipo_lote) qs.set('tipo_lote', params.tipo_lote);
    if (params?.estado) qs.set('estado', params.estado);
    const query = qs.toString();
    const response = await get<PaginatedResponse<LotePagoBancario> | LotePagoBancario[]>(
      `${LOTES_BASE}${query ? '?' + query : ''}`,
    );
    return toList<LotePagoBancario>(response);
  },

  getById: async (id: string): Promise<LotePagoBancario> =>
    get<LotePagoBancario>(`${LOTES_BASE}${id}/`),

  generarProveedores: async (payload: GenerarLoteProveedoresPayload): Promise<LotePagoBancario> =>
    post<LotePagoBancario>(
      `${LOTES_BASE}generar-proveedores/`,
      payload as unknown as Record<string, unknown>,
    ),

  generarNomina: async (payload: GenerarLoteNominaPayload): Promise<LotePagoBancario> =>
    post<LotePagoBancario>(
      `${LOTES_BASE}generar-nomina/`,
      payload as unknown as Record<string, unknown>,
    ),

  descargar: async (id: string): Promise<Blob> =>
    fetchBlob(`${LOTES_BASE}${id}/descargar/`, { headers: { Accept: '*/*' } }),

  marcarEnviado: async (id: string): Promise<LotePagoBancario> =>
    post<LotePagoBancario>(`${LOTES_BASE}${id}/marcar-enviado/`, {}),

  marcarProcesado: async (id: string): Promise<LotePagoBancario> =>
    post<LotePagoBancario>(`${LOTES_BASE}${id}/marcar-procesado/`, {}),

  anular: async (id: string): Promise<LotePagoBancario> =>
    post<LotePagoBancario>(`${LOTES_BASE}${id}/anular/`, {}),
};

export async function validarCuentaVe(numeroCuenta: string): Promise<ValidarCuentaVeResponse> {
  return post<ValidarCuentaVeResponse>('/banca-electronica/validar-cuenta-ve/', {
    numero_cuenta: numeroCuenta,
  });
}

export async function validarReferenciaBancaria(
  payload: ValidarReferenciaPayload,
): Promise<ValidarReferenciaResponse> {
  return post<ValidarReferenciaResponse>(
    '/banca-electronica/validar-referencia/',
    payload as unknown as Record<string, unknown>,
  );
}
