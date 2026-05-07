import { get } from './api';

export type Moneda = {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
};

export async function fetchMonedas(): Promise<Moneda[]> {
  const res = await get<{ results: Moneda[] } | Moneda[]>(
    '/finanzas/monedas/'
  );
  if (Array.isArray(res)) return res;
  if (res && Array.isArray(res.results)) return res.results;
  return [];
}
