import { get } from './api';

export interface MonedasInfoMetodoPago {
  asociadas: string[];
  activas_empresa: string[];
  sugeridas: string[];
  obligatorias: string[];
}

export async function fetchMonedasInfoMetodoPago(id_metodo_pago: string, empresa?: string): Promise<MonedasInfoMetodoPago> {
  let url = `/finanzas/metodopago/${id_metodo_pago}/monedas_info/`;
  if (empresa) url += `?empresa=${empresa}`;
  return get<MonedasInfoMetodoPago>(url);
}
