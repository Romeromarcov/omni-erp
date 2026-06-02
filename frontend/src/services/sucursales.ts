import { get } from './api';

export type Sucursal = {
  id_sucursal: string;
  nombre: string;
};

export async function fetchSucursales(id_empresa: string): Promise<Sucursal[]> {
  const res = await get<{ results: Sucursal[] } | Sucursal[]>(`/core/sucursales/?id_empresa=${id_empresa}`);
  if (Array.isArray(res)) return res;
  if (res && Array.isArray(res.results)) return res.results;
  return [];
}

export async function fetchAllSucursales(): Promise<Sucursal[]> {
  const res = await get<{ results: Sucursal[] } | Sucursal[]>('/core/sucursales/');
  if (Array.isArray(res)) return res;
  if (res && Array.isArray(res.results)) return res.results;
  return [];
}
