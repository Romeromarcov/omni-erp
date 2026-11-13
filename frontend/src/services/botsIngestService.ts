/**
 * Servicio de ingestas de bots de Telegram (`/api/bots/`).
 *
 * - Ingestas: lo que enviaron los bots (pedidos, cotizaciones, pagos, eventos…).
 *   Los pagos incompletos se pueden completar desde aquí.
 * - Usuarios de Telegram autorizados (telegram_user_id ↔ usuario Omni/vendedor).
 *
 * Multi-tenant lo aplica el backend. Payloads con whitelist explícita (CTF-005).
 */
import { get, post, patch, del } from './api';
import { toList } from '../utils/api';

export type KindIngesta =
  | 'contacto'
  | 'cotizacion'
  | 'pedido'
  | 'pago'
  | 'pago_proveedor'
  | 'evento';

export type EstadoIngesta = 'PROCESADO' | 'BORRADOR' | 'INCOMPLETO' | 'SINCRONIZADO' | 'ERROR';

export const KINDS_INGESTA: readonly KindIngesta[] = [
  'contacto',
  'cotizacion',
  'pedido',
  'pago',
  'pago_proveedor',
  'evento',
] as const;

export const ESTADOS_INGESTA: readonly EstadoIngesta[] = [
  'PROCESADO',
  'BORRADOR',
  'INCOMPLETO',
  'SINCRONIZADO',
  'ERROR',
] as const;

/** Tipos cuya ingesta admite «completar» (el backend solo acepta pagos). */
export const KINDS_COMPLETABLES: readonly KindIngesta[] = ['pago', 'pago_proveedor'] as const;

export interface Ingesta {
  id_ingesta: string;
  kind: KindIngesta;
  estado: EstadoIngesta;
  incompleto: string[];
  resultado: Record<string, unknown>;
  auto: boolean;
  payload: Record<string, unknown>;
  odoo_ref: string;
  idempotency_key: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface BotUsuario {
  id_bot_usuario: string;
  id_empresa: string;
  telegram_user_id: number;
  usuario: string;
  nombre: string;
  activo: boolean;
}

export interface BotUsuarioPayload {
  telegram_user_id: number;
  usuario: string;
  nombre: string;
}

const BASE = '/bots';

export const ingestasService = {
  getAll: async (f: { estado?: EstadoIngesta | ''; kind?: KindIngesta | '' } = {}): Promise<Ingesta[]> => {
    const qs = new URLSearchParams();
    if (f.estado) qs.set('estado', f.estado);
    if (f.kind) qs.set('kind', f.kind);
    const q = qs.toString();
    return toList<Ingesta>(await get<unknown>(`${BASE}/ingest/${q ? '?' + q : ''}`));
  },

  /** Completa un pago incompleto: `cambios` = campos del borrador a fusionar. */
  completar: (id: string, cambios: Record<string, string>): Promise<Ingesta> =>
    post<Ingesta>(`${BASE}/ingest/${id}/completar/`, { cambios }),
};

export const botUsuariosService = {
  getAll: async (): Promise<BotUsuario[]> =>
    toList<BotUsuario>(await get<unknown>(`${BASE}/usuarios/`)),

  create: (p: BotUsuarioPayload): Promise<BotUsuario> =>
    post<BotUsuario>(`${BASE}/usuarios/`, {
      telegram_user_id: p.telegram_user_id,
      usuario: p.usuario,
      nombre: p.nombre,
    }),

  update: (id: string, p: Partial<BotUsuarioPayload>): Promise<BotUsuario> => {
    const body: Record<string, unknown> = {};
    if (p.telegram_user_id !== undefined) body.telegram_user_id = p.telegram_user_id;
    if (p.usuario !== undefined) body.usuario = p.usuario;
    if (p.nombre !== undefined) body.nombre = p.nombre;
    return patch<BotUsuario>(`${BASE}/usuarios/${id}/`, body);
  },

  remove: (id: string): Promise<void> => del<void>(`${BASE}/usuarios/${id}/`),
};
