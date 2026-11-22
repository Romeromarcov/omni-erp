import { API_URL, fetchBlob, get, patch, post, type HttpError } from './api';
import { toList, type PaginatedResponse } from '../utils/api';
import type { EjecucionAgente } from './agentesService';

export type BotonTipo =
  | 'web'
  | 'instagram'
  | 'catalogo'
  | 'pago'
  | 'ubicacion'
  | 'whatsapp'
  | 'telefono'
  | 'correo';

export interface ConnectBoton {
  tipo: BotonTipo | string;
  etiqueta: string;
  valor: string;
}

export interface PublicConnectProfile {
  slug: string;
  nombre_publico: string;
  cargo: string;
  bio: string;
  telefono_publico: string;
  email_publico: string;
  tema: string;
  botones: ConnectBoton[];
  empresa_nombre: string;
  acepta_leads: boolean;
  consentimiento_texto: string;
}

export interface PublicLeadPayload {
  nombre: string;
  apellido?: string;
  empresa_nombre?: string;
  email?: string;
  telefono?: string;
  mensaje?: string;
  fuente?: 'NFC' | 'QR' | 'ENLACE' | '';
  origen?: 'NFC' | 'QR' | 'ENLACE' | '';
  uid?: string;
  uid_chip?: string;
  consentimiento_aceptado: boolean;
  consentimiento_texto: string;
  website?: string;
  company_url?: string;
}

export interface PublicLeadResponse {
  ok: boolean;
  mensaje: string;
}

export interface ConnectPerfil {
  id_perfil: string;
  id_empresa: string;
  usuario: string;
  slug: string;
  nombre_publico: string;
  cargo: string;
  bio: string;
  telefono_publico: string;
  email_publico: string;
  tema: string;
  botones: ConnectBoton[];
  plantilla_bloqueada: boolean;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface ConnectPerfilUpdatePayload {
  slug: string;
  nombre_publico: string;
  cargo?: string;
  bio?: string;
  telefono_publico?: string;
  email_publico?: string;
  tema?: string;
  botones?: ConnectBoton[];
}

const URL_BOTON_TIPOS = new Set<string>(['web', 'instagram', 'catalogo', 'pago', 'ubicacion']);

function createHttpError(message: string, status: number): HttpError {
  const err: HttpError = new Error(message);
  err.status = status;
  return err;
}

function extractApiErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback;
  const entries = Object.entries(data as Record<string, unknown>);
  for (const [key, val] of entries) {
    if ((key === 'detail' || key === 'error' || key === 'mensaje') && typeof val === 'string' && val.trim()) {
      return val.trim();
    }
  }
  for (const [, val] of entries) {
    if (typeof val === 'string' && val.trim()) return val.trim();
    if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'string' && val[0].trim()) {
      return val[0].trim();
    }
  }
  return fallback;
}

function buildPublicQueryString(params: { uid?: string; origen?: string }): string {
  const qs = new URLSearchParams();
  if (params.uid && params.uid.trim()) {
    qs.set('uid', params.uid.trim());
  }
  if (params.origen && params.origen.trim()) {
    qs.set('origen', params.origen.trim());
  }
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : '';
}

/**
 * Normaliza y valida un botón Connect frente a una allowlist estricta de esquemas
 * para impedir inyecciones ``javascript:`` o ``data:`` en enlaces públicos.
 */
export function buildHrefSeguro(boton: Pick<ConnectBoton, 'tipo' | 'valor'>): string | null {
  const tipo = String(boton.tipo || '').trim().toLowerCase();
  const valor = String(boton.valor || '').trim();
  if (!valor || /[\r\n\0]/.test(valor)) {
    return null;
  }

  if (URL_BOTON_TIPOS.has(tipo)) {
    try {
      const parsed = new URL(valor);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return parsed.toString();
      }
      return null;
    } catch {
      return null;
    }
  }

  if (tipo === 'whatsapp') {
    const clean = valor.replace(/[\s\-()]/g, '');
    if (!/^\+?[0-9]{7,15}$/.test(clean)) {
      return null;
    }
    const digits = clean.replace(/\D/g, '');
    return digits.length >= 7 ? `https://wa.me/${digits}` : null;
  }

  if (tipo === 'telefono') {
    const clean = valor.replace(/[\s\-()]/g, '');
    return /^\+?[0-9]{7,15}$/.test(clean) ? `tel:${clean}` : null;
  }

  if (tipo === 'correo') {
    return /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(valor) ? `mailto:${valor}` : null;
  }

  return null;
}

export async function getPublicProfile(
  slug: string,
  uid?: string,
  origen?: string,
): Promise<PublicConnectProfile> {
  const cleanSlug = encodeURIComponent(slug.trim());
  const qs = buildPublicQueryString({ uid, origen });
  const response = await fetch(`${API_URL}/public/connect/${cleanSlug}/${qs}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    let message =
      response.status === 404
        ? 'Perfil no encontrado o inactivo.'
        : 'No se pudo cargar la tarjeta digital.';
    try {
      const body = await response.json();
      message = extractApiErrorMessage(body, message);
    } catch {
      // Ignora cuerpos no JSON en respuestas de error.
    }
    throw createHttpError(message, response.status);
  }

  return (await response.json()) as PublicConnectProfile;
}

export function getPublicVCardUrl(slug: string, uid?: string): string {
  const cleanSlug = encodeURIComponent(slug.trim());
  const qs = buildPublicQueryString({ uid });
  return `${API_URL}/public/connect/${cleanSlug}/vcard/${qs}`;
}

export async function submitPublicLead(
  slug: string,
  payload: PublicLeadPayload,
  uid?: string,
  origen?: string,
): Promise<PublicLeadResponse> {
  const cleanSlug = encodeURIComponent(slug.trim());
  const qs = buildPublicQueryString({ uid, origen });
  const response = await fetch(`${API_URL}/public/connect/${cleanSlug}/leads/${qs}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message =
      response.status === 429
        ? 'Demasiados envíos en pocos minutos. Intenta más tarde.'
        : 'No pudimos enviar tus datos. Verifica los campos e intenta nuevamente.';
    try {
      const body = await response.json();
      message = extractApiErrorMessage(body, message);
    } catch {
      // Ignora cuerpos no JSON en respuestas de error.
    }
    throw createHttpError(message, response.status);
  }

  return (await response.json()) as PublicLeadResponse;
}

export async function getMiPerfil(empresaId?: string | null): Promise<ConnectPerfil> {
  const qs = empresaId ? `?empresa_id=${encodeURIComponent(empresaId)}` : '';
  return get<ConnectPerfil>(`/connect/perfiles/mi-perfil/${qs}`);
}

export async function updateMiPerfil(
  payload: ConnectPerfilUpdatePayload,
  empresaId?: string | null,
): Promise<ConnectPerfil> {
  const qs = empresaId ? `?empresa_id=${encodeURIComponent(empresaId)}` : '';
  return patch<ConnectPerfil>(
    `/connect/perfiles/mi-perfil/${qs}`,
    payload as unknown as Record<string, unknown>,
  );
}

// ── S10: Analíticas de Omni Connect ───────────────────────────────────────────

export interface ConnectAnaliticasPeriodo {
  desde: string;
  hasta: string;
  dias: number;
}

export interface ConnectAnaliticasSerieDia {
  fecha: string;
  toques: number;
  leads: number;
}

export interface ConnectAnaliticasTopPerfil {
  id_perfil: string;
  slug: string;
  nombre_publico: string;
  toques: number;
  visitantes_unicos: number;
  leads: number;
  leads_convertidos: number;
  tasa_conversion_pct: string;
}

export interface ConnectAnaliticasResponse {
  periodo: ConnectAnaliticasPeriodo;
  perfil_id: string | null;
  total_toques: number;
  visitantes_unicos: number;
  total_leads: number;
  leads_convertidos: number;
  tasa_conversion_pct: string;
  tasa_cierre_pct: string;
  por_origen: Record<string, number>;
  por_dispositivo: Record<string, number>;
  serie_diaria: ConnectAnaliticasSerieDia[];
  top_perfiles: ConnectAnaliticasTopPerfil[];
}

export interface ConnectAnaliticasParams {
  empresaId?: string | null;
  dias?: number;
  desde?: string;
  hasta?: string;
  perfilId?: string | null;
}

export async function getPerfilesConnect(empresaId?: string | null): Promise<ConnectPerfil[]> {
  const qs = empresaId ? `?empresa_id=${encodeURIComponent(empresaId)}` : '';
  const data = await get<PaginatedResponse<ConnectPerfil> | ConnectPerfil[]>(
    `/connect/perfiles/${qs}`,
  );
  return toList<ConnectPerfil>(data);
}

export async function getAnaliticasConnect(
  params: ConnectAnaliticasParams = {},
): Promise<ConnectAnaliticasResponse> {
  const qs = new URLSearchParams();
  if (params.empresaId) qs.set('empresa_id', params.empresaId);
  if (typeof params.dias === 'number' && Number.isFinite(params.dias)) {
    qs.set('dias', String(params.dias));
  }
  if (params.desde) qs.set('desde', params.desde);
  if (params.hasta) qs.set('hasta', params.hasta);
  if (params.perfilId) qs.set('perfil_id', params.perfilId);
  const query = qs.toString();
  return get<ConnectAnaliticasResponse>(`/connect/analiticas/${query ? `?${query}` : ''}`);
}

// ── S11: Tarjetas físicas NFC y generación QR SVG/PNG ────────────────────────

export type TarjetaTipo = 'PVC' | 'METAL' | 'PULSERA';
export type TarjetaEstado = 'INVENTARIO' | 'ACTIVA' | 'DESACTIVADA' | 'PERDIDA';
export type ConnectQrFormato = 'svg' | 'png';

export interface ConnectTarjeta {
  id_tarjeta: string;
  id_empresa: string;
  perfil: string | null;
  perfil_slug: string | null;
  perfil_nombre: string | null;
  uid_chip: string;
  tipo: TarjetaTipo | string;
  estado: TarjetaEstado | string;
  fecha_activacion: string | null;
  notas: string;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface ConnectTarjetaCreatePayload {
  uid_chip: string;
  tipo?: TarjetaTipo;
  notas?: string;
  perfil?: string | null;
}

export interface ConnectTarjetaAsignarPayload {
  perfil_id: string;
  activar?: boolean;
}

export async function getTarjetasConnect(params: {
  empresaId?: string | null;
  estado?: string | null;
  incluirInactivos?: boolean;
} = {}): Promise<ConnectTarjeta[]> {
  const qs = new URLSearchParams();
  if (params.empresaId) qs.set('empresa_id', params.empresaId);
  if (params.estado) qs.set('estado', params.estado);
  if (params.incluirInactivos) qs.set('incluir_inactivos', 'true');
  const query = qs.toString();
  const data = await get<PaginatedResponse<ConnectTarjeta> | ConnectTarjeta[]>(
    `/connect/tarjetas/${query ? `?${query}` : ''}`,
  );
  return toList<ConnectTarjeta>(data);
}

export async function crearTarjetaConnect(
  payload: ConnectTarjetaCreatePayload,
  empresaId?: string | null,
): Promise<ConnectTarjeta> {
  const body: Record<string, unknown> = {
    uid_chip: payload.uid_chip.trim(),
    tipo: payload.tipo ?? 'PVC',
    notas: payload.notas?.trim() ?? '',
  };
  if (payload.perfil) body.perfil = payload.perfil;
  if (empresaId) body.id_empresa = empresaId;
  return post<ConnectTarjeta>('/connect/tarjetas/', body);
}

export async function asignarTarjetaConnect(
  tarjetaId: string,
  payload: ConnectTarjetaAsignarPayload,
): Promise<ConnectTarjeta> {
  return post<ConnectTarjeta>(`/connect/tarjetas/${encodeURIComponent(tarjetaId)}/asignar/`, {
    perfil_id: payload.perfil_id,
    activar: Boolean(payload.activar),
  });
}

export async function activarTarjetaConnect(tarjetaId: string): Promise<ConnectTarjeta> {
  return post<ConnectTarjeta>(`/connect/tarjetas/${encodeURIComponent(tarjetaId)}/activar/`, {});
}

export async function desactivarTarjetaConnect(tarjetaId: string): Promise<ConnectTarjeta> {
  return post<ConnectTarjeta>(`/connect/tarjetas/${encodeURIComponent(tarjetaId)}/desactivar/`, {});
}

export async function marcarPerdidaTarjetaConnect(tarjetaId: string): Promise<ConnectTarjeta> {
  return post<ConnectTarjeta>(
    `/connect/tarjetas/${encodeURIComponent(tarjetaId)}/marcar-perdida/`,
    {},
  );
}

export async function getTarjetaQrBlob(
  tarjetaId: string,
  formato: ConnectQrFormato = 'svg',
): Promise<Blob> {
  const accept = formato === 'png' ? 'image/png' : 'image/svg+xml';
  return fetchBlob(
    `/connect/tarjetas/${encodeURIComponent(tarjetaId)}/qr/?formato=${encodeURIComponent(formato)}`,
    { headers: { Accept: `${accept}, application/json` } },
  );
}

export async function getMiPerfilQrBlob(
  formato: ConnectQrFormato = 'svg',
  empresaId?: string | null,
): Promise<Blob> {
  const qs = new URLSearchParams({ formato });
  if (empresaId) qs.set('empresa_id', empresaId);
  const accept = formato === 'png' ? 'image/png' : 'image/svg+xml';
  return fetchBlob(`/connect/perfiles/mi-perfil/qr/?${qs.toString()}`, {
    headers: { Accept: `${accept}, application/json` },
  });
}

// ── S12: Agentes IA Omni Connect (calificador + seguimiento con aprobación) ───

export async function calificarLeadConnect(leadId: string): Promise<EjecucionAgente> {
  return post<EjecucionAgente>('/agentes/predicciones/calificar-lead-connect/', {
    lead_id: leadId,
  });
}

export async function proponerSeguimientoConnect(leadId: string): Promise<EjecucionAgente> {
  return post<EjecucionAgente>('/agentes/predicciones/proponer-seguimiento-connect/', {
    lead_id: leadId,
  });
}
