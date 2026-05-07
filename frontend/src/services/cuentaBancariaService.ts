// Obtener movimientos de una cuenta bancaria
export async function getMovimientosCuentaBancaria(id_cuenta_bancaria: string, filters: Record<string, unknown> = {}) {
  const params = new URLSearchParams(filters as Record<string, string>).toString();
  const endpoint = `/finanzas/cuentas-bancarias-empresa/${id_cuenta_bancaria}/movimientos-cuenta-bancaria/${params ? `?${params}` : ''}`;
  return get(endpoint);
}
import { get, post, put } from './api';

export async function getCuentasBancarias(id_empresa: string, filters: Record<string, unknown> = {}) {
  const params = new URLSearchParams({ ...filters, empresa: id_empresa } as Record<string, string>).toString();
  const endpoint = `/finanzas/cuentas-bancarias-empresa/${params ? `?${params}` : ''}`;
  return get(endpoint);
}

export async function updateCuentaBancaria(id_cuenta_bancaria: string, payload: Record<string, unknown>) {
  return put(`/finanzas/cuentas-bancarias-empresa/${id_cuenta_bancaria}/`, payload);
}

export async function createCuentaBancaria(id_empresa: string, payload: Record<string, unknown>) {
  const mappedPayload = {
    ...payload,
    empresa: id_empresa,
  };
  return post(`/finanzas/cuentas-bancarias-empresa/`, mappedPayload);
}

export async function getCuentaBancariaDetail(id_cuenta_bancaria: string) {
  return get(`/finanzas/cuentas-bancarias-empresa/${id_cuenta_bancaria}/`);
}
