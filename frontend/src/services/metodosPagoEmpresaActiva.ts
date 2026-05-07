import { get, patch } from './api';

export interface MetodoPagoEmpresaActiva {
  id: string;
  nombre_metodo: string;
  monedas: string[];
  [key: string]: unknown;
}

export async function fetchMetodosPagoEmpresaActivos(empresa: string): Promise<MetodoPagoEmpresaActiva[]> {
  const data = await get<MetodoPagoEmpresaActiva[] | { results: MetodoPagoEmpresaActiva[] }>(
    `/finanzas/metodos-pago-empresa-activas/?empresa=${empresa}`
  );
  if (Array.isArray(data)) return data;
  if (data && 'results' in data && Array.isArray(data.results)) return data.results;
  return [];
}

export async function updateMonedasMetodoPagoEmpresaActiva(id: string, monedas: string[]): Promise<unknown> {
  return patch(`/finanzas/metodos-pago-empresa-activas/${id}/`, { monedas });
}
