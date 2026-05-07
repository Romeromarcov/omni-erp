import { get } from './api';

export interface TasaBCV {
  moneda_origen: string;
  moneda_destino: string;
  tasa: number;
  fecha: string;
}

export async function fetchTasaBCV(moneda_origen = 'USD', moneda_destino = 'VES', fecha?: string): Promise<TasaBCV> {
  let url = `/finanzas/tasa-oficial-bcv/?moneda_origen=${moneda_origen}&moneda_destino=${moneda_destino}`;
  if (fecha) url += `&fecha=${fecha}`;
  return get<TasaBCV>(url);
}
