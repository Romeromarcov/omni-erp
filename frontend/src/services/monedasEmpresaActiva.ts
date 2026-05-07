import { get } from './api';

export interface MonedaEmpresaActiva {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
  [key: string]: unknown;
}

export async function fetchMonedasEmpresaActivas(empresa: string): Promise<MonedaEmpresaActiva[]> {
  const data = await get<MonedaEmpresaActiva[] | { results: MonedaEmpresaActiva[] }>(
    `/finanzas/monedas-empresa-activas/?empresa=${empresa}`
  );
  if (Array.isArray(data)) return data;
  if (data && 'results' in data && Array.isArray(data.results)) return data.results;
  return [];
}
