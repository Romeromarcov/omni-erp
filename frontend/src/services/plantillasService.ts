import { get, post, put, patch, del } from './api';

export interface PlantillaMaestroCajasVirtuales {
  id_plantilla: string;
  nombre: string;
  descripcion?: string;
  id_empresa: string;
  metodos_pago: string[]; // IDs de métodos de pago
  monedas: string[]; // IDs de monedas
  activa: boolean;
  fecha_creacion: string;
  fecha_modificacion: string;
}

export interface CajaVirtualAuto {
  id_caja_virtual: string;
  nombre: string;
  id_plantilla: string;
  id_usuario?: string;
  id_empleado?: string;
  id_sucursal?: string;
  metodos_pago: string[];
  monedas: string[];
  activa: boolean;
  fecha_creacion: string;
}

export interface CajaMetodoPagoOverride {
  id_override: string;
  id_sucursal: string;
  id_metodo_pago: string;
  deshabilitado: boolean;
  fecha_creacion: string;
  sucursal_nombre?: string;
  metodo_pago_nombre?: string;
}

// Plantillas Maestro
export async function getPlantillasMaestro(id_empresa: string): Promise<PlantillaMaestroCajasVirtuales[]> {
  const response = await get(`/finanzas/plantillas-maestro-cajas/?id_empresa=${id_empresa}`);
  if (Array.isArray(response)) return response;
  if (response && typeof response === 'object' && 'results' in response && Array.isArray(response.results)) return response.results;
  return [];
}

export async function createPlantillaMaestro(data: Omit<PlantillaMaestroCajasVirtuales, 'id_plantilla' | 'fecha_creacion' | 'fecha_modificacion'>): Promise<PlantillaMaestroCajasVirtuales> {
  return post('/finanzas/plantillas-maestro-cajas/', data);
}

export async function updatePlantillaMaestro(id: string, data: Partial<PlantillaMaestroCajasVirtuales>): Promise<PlantillaMaestroCajasVirtuales> {
  return put(`/finanzas/plantillas-maestro-cajas/${id}/`, data);
}

export async function togglePlantillaMaestroActiva(id: string, activa: boolean): Promise<void> {
  return patch(`/finanzas/plantillas-maestro-cajas/${id}/`, { activa });
}

// Cajas Virtuales Automáticas
export async function getCajasVirtualesAuto(id_empresa: string): Promise<CajaVirtualAuto[]> {
  const response = await get(`/finanzas/cajas-virtuales-auto/?id_empresa=${id_empresa}`);
  if (Array.isArray(response)) return response;
  if (response && typeof response === 'object' && 'results' in response && Array.isArray(response.results)) return response.results;
  return [];
}

// Overrides de Métodos de Pago
export async function getOverridesMetodosPago(id_empresa: string): Promise<CajaMetodoPagoOverride[]> {
  const response = await get(`/finanzas/overrides-metodos-pago/?id_empresa=${id_empresa}`);
  if (Array.isArray(response)) return response;
  if (response && typeof response === 'object' && 'results' in response && Array.isArray(response.results)) return response.results;
  return [];
}

export async function createOverrideMetodoPago(data: Omit<CajaMetodoPagoOverride, 'id_override' | 'fecha_creacion'>): Promise<CajaMetodoPagoOverride> {
  return post('/finanzas/overrides-metodos-pago/', data);
}

export async function updateOverrideMetodoPago(id: string, data: Partial<CajaMetodoPagoOverride>): Promise<CajaMetodoPagoOverride> {
  return put(`/finanzas/overrides-metodos-pago/${id}/`, data);
}

export async function deleteOverrideMetodoPago(id: string): Promise<void> {
  await del(`/finanzas/overrides-metodos-pago/${id}/`);
}