import { get, post, put, patch } from './api';

export async function getCajaTipoChoices() {
  return get('/finanzas/cajas/tipo-caja-choices/');
}

export async function getCajas(id_empresa: string, filters: Record<string, unknown> = {}) {
  const params = new URLSearchParams({ ...filters, empresa: id_empresa } as Record<string, string>).toString();
  return get(`/finanzas/cajas/${params ? `?${params}` : ''}`);
}

export async function createCaja(id_empresa: string, payload: Record<string, unknown>) {
  return post('/finanzas/cajas/', { ...payload, empresa: id_empresa });
}

export async function updateCaja(id_caja: string, payload: Record<string, unknown>) {
  return put(`/finanzas/cajas/${id_caja}/`, payload);
}

export async function toggleCajaActiva(id_caja: string, activo: boolean) {
  return patch(`/finanzas/cajas/${id_caja}/`, { activo });
}

export async function getCajaDetail(id_caja: string) {
  return get(`/finanzas/cajas/${id_caja}/`);
}

export async function getMovimientosCaja(id_caja: string, filters: Record<string, unknown> = {}) {
  const params = new URLSearchParams(filters as Record<string, string>).toString();
  return get(`/finanzas/cajas/${id_caja}/movimientos-caja-banco/${params ? `?${params}` : ''}`);
}
