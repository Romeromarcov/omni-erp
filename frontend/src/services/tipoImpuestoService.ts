export interface TipoImpuestoData extends Record<string, unknown> {
  nombre_impuesto: string;
  codigo_impuesto: string;
  es_retencion: boolean;
}

export interface TipoImpuestoEmpresaActiva {
  id: string;
  tipo_impuesto: string;
  tipo_impuesto_nombre: string;
  tipo_impuesto_codigo: string;
  empresa_nombre: string;
  activa: boolean;
}
import { get, post, patch } from './api';

const API = '/finanzas';


export async function getTiposImpuestoEmpresaActivas(): Promise<TipoImpuestoEmpresaActiva[]> {
  const res = await get<{ results: TipoImpuestoEmpresaActiva[] } | TipoImpuestoEmpresaActiva[]>(
    `${API}/tipos-impuesto-empresa-activas/`
  );
  if (Array.isArray(res)) return res;
  if (res && Array.isArray((res as { results?: unknown }).results)) return (res as { results: TipoImpuestoEmpresaActiva[] }).results;
  return [];
}

export async function activateTipoImpuestoEmpresa(id: string) {
  return patch(`${API}/tipos-impuesto-empresa-activas/${id}/`, { activa: true });
}

export async function deactivateTipoImpuestoEmpresa(id: string) {
  return patch(`${API}/tipos-impuesto-empresa-activas/${id}/`, { activa: false });
}

export async function getTipoImpuestoById(id: string) {
  return get(`${API}/tipos-impuesto/${id}/`);
}

export async function updateTipoImpuesto(id: string, data: TipoImpuestoData) {
  return patch(`${API}/tipos-impuesto/${id}/`, data);
}

export async function createTipoImpuesto(data: TipoImpuestoData) {
  return post(`${API}/tipos-impuesto/`, data);
}
