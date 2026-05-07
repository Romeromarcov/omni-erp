import { get, post } from './api';

export interface SesionCaja {
  id_sesion: string;
  usuario: {
    id: number;
    username: string;
    first_name: string;
    last_name: string;
  };
  caja_fisica_principal: {
    id_caja: string;
    nombre: string;
    sucursal: {
      id_sucursal: string;
      nombre: string;
      empresa: {
        id_empresa: string;
        nombre: string;
      };
    };
  };
  estado: string;
  fecha_apertura: string;
  observaciones?: string;
}

export async function getSesionActiva(): Promise<SesionCaja | null> {
  const response = await get<SesionCaja[] | { results: SesionCaja[] }>('/finanzas/sesiones-caja/?estado=ABIERTA&limit=1');
  if (Array.isArray(response)) return response[0] ?? null;
  if (response && 'results' in response && Array.isArray(response.results)) return response.results[0] ?? null;
  return null;
}

export async function closeSesion(sesionId: string, observaciones?: string): Promise<void> {
  await post(`/finanzas/sesiones-caja/${sesionId}/cerrar/`, { observaciones });
}
