import { get, post, put } from './api';


export async function getTransaccionesFinancieras(id_empresa: string | undefined, filters: Record<string, unknown>) {
  // Mapea los filtros a query params manualmente
  const params = new URLSearchParams();
  if (id_empresa) params.append('id_empresa', id_empresa);
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  });
  return get(`/finanzas/transacciones-financieras/?${params.toString()}`);
}


export async function exportTransaccionesFinancieras(id_empresa: string | undefined, filters: Record<string, unknown>) {
  // Implementa exportación descargando el archivo
  const params = new URLSearchParams();
  if (id_empresa) params.append('id_empresa', id_empresa);
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  });
  const url = `/finanzas/transacciones-financieras/export/?${params.toString()}`;
  window.open(url, '_blank');
}


export async function getTransaccionFinancieraDetail(id_transaccion: string | undefined) {
  return get(`/finanzas/transacciones-financieras/${id_transaccion}/`);
}


export async function updateTransaccionFinanciera(id_transaccion: string | undefined, data: Record<string, unknown>) {
  return put(`/finanzas/transacciones-financieras/${id_transaccion}/`, data);
}


export async function printTransaccionFinanciera(id_transaccion: string | undefined) {
  window.open(`/finanzas/transacciones-financieras/${id_transaccion}/print/`, '_blank');
}


export async function createIngreso(id_empresa: string | undefined, data: Record<string, unknown>) {
  // Si el backend espera id_empresa como query param, ajusta la URL:
  return post(`/finanzas/transacciones-financieras/ingreso/?id_empresa=${id_empresa}`, data);
}


export async function createEgreso(id_empresa: string | undefined, data: Record<string, unknown>) {
  return post(`/finanzas/transacciones-financieras/egreso/?id_empresa=${id_empresa}`, data);
}


