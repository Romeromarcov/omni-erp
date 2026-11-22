/**
 * Servicio de ingestas y plano de control de bots (`/api/bots/`).
 *
 * - Ingestas: borradores enviados por bots (contactos, cotizaciones, pedidos,
 *   pagos, proveedores, facturas/gastos de compra y eventos), completar pagos
 *   y reintentar empuje en borrador hacia Odoo.
 * - Plano de control multi-tenant: estado de la flota, parámetros remotos,
 *   pausa/reanudación, salud de destinos y bitácora auditable.
 * - Usuarios de Telegram autorizados por empresa y por bot.
 */
import { get, post, patch, del } from './api';
import { toList } from '../utils/api';

export type KindIngesta =
  | 'contacto'
  | 'cotizacion'
  | 'pedido'
  | 'pago'
  | 'pago_proveedor'
  | 'proveedor'
  | 'factura_proveedor'
  | 'gasto'
  | 'evento';

export type EstadoIngesta = 'PROCESADO' | 'BORRADOR' | 'INCOMPLETO' | 'SINCRONIZADO' | 'ERROR';

export const KINDS_INGESTA: readonly KindIngesta[] = [
  'contacto',
  'cotizacion',
  'pedido',
  'pago',
  'pago_proveedor',
  'proveedor',
  'factura_proveedor',
  'gasto',
  'evento',
] as const;

export const ESTADOS_INGESTA: readonly EstadoIngesta[] = [
  'PROCESADO',
  'BORRADOR',
  'INCOMPLETO',
  'SINCRONIZADO',
  'ERROR',
] as const;

/** Tipos cuya ingesta admite «completar» (pagos, facturas de proveedor y gastos). */
export const KINDS_COMPLETABLES: readonly KindIngesta[] = [
  'pago',
  'pago_proveedor',
  'factura_proveedor',
  'gasto',
] as const;

/** Los 7 tipos que pueden empujarse en borrador hacia Odoo cuando están completos. */
export const KINDS_SINCRONIZABLES: readonly KindIngesta[] = [
  'contacto',
  'pedido',
  'pago',
  'pago_proveedor',
  'proveedor',
  'factura_proveedor',
  'gasto',
] as const;

export const CODIGOS_BOT_ESTANDAR = [
  'pedidos',
  'cobranza',
  'compras',
  'eventos',
  'tareas',
] as const;

export type CodigoBotEstandar = (typeof CODIGOS_BOT_ESTANDAR)[number];

export const ETIQUETAS_BOT = new Map<string, string>([
  ['pedidos', 'Ventas y Pedidos'],
  ['cobranza', 'Cobranzas'],
  ['compras', 'Compras y Gastos'],
  ['eventos', 'Eventos'],
  ['tareas', 'Tareas'],
  ['asana', 'Tareas (legado)'],
]);

export interface Ingesta {
  id_ingesta: string;
  kind: KindIngesta;
  estado: EstadoIngesta;
  incompleto: string[];
  resultado: Record<string, unknown>;
  auto: boolean;
  payload: Record<string, unknown>;
  odoo_ref: string;
  error?: string;
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
  bots?: string[];
  activo: boolean;
}

export interface BotUsuarioPayload {
  telegram_user_id: number;
  usuario: string;
  nombre: string;
  bots?: string[];
}

export interface EstadoRuntimeBot {
  modo?: string;
  gemini?: string;
  omni?: string;
  cxc?: string;
  outbox_pendientes?: number;
  mensajes_hoy?: number;
  errores_hoy?: number;
  ultimo_error?: string | null;
}

export interface ParametrosBot {
  auto_envio_min?: number;
  gemini_model?: string;
  [clave: string]: unknown;
}

export interface ChatsBot {
  grupo?: number | null;
  respaldo?: number | null;
  [clave: string]: number | null | undefined;
}

export interface ResumenBotFlota {
  bot: string;
  nombre: string;
  habilitado: boolean;
  en_linea: boolean;
  ultimo_latido: string | null;
  hace_segundos: number | null;
  visto_alguna_vez: boolean;
  version: string;
  estado: EstadoRuntimeBot;
  parametros: ParametrosBot;
  chats: ChatsBot;
  url_panel: string;
  mensaje: string;
  actualizado_por: string;
  actualizado_en: string | null;
  n_usuarios?: number;
}

export interface HistorialDiaBot {
  dia: string;
  latidos: number;
  mensajes: number;
  errores: number;
}

export interface IngestaRecienteBot {
  id_ingesta: string;
  kind: KindIngesta;
  estado: EstadoIngesta;
  fecha_creacion: string;
  odoo_ref: string;
  error: string;
  incompleto: string[];
  vendedor: string;
  auto: boolean;
}

export interface EntradaBitacoraBot {
  id: string;
  entidad: string;
  accion: string;
  antes: Record<string, unknown>;
  despues: Record<string, unknown>;
  actor: string;
  en: string;
}

export interface UsuarioResumenBot {
  id_bot_usuario: string;
  telegram_user_id: number;
  email: string;
  nombre: string;
  bots: string[];
}

export interface DetalleBotFlota extends ResumenBotFlota {
  usuarios: UsuarioResumenBot[];
  ingestas_recientes: IngestaRecienteBot[];
  historial: HistorialDiaBot[];
  bitacora: EntradaBitacoraBot[];
  modelos_sugeridos: string[];
}

export interface BotControlPatchPayload {
  habilitado?: boolean;
  nombre?: string;
  parametros?: ParametrosBot;
  chats?: ChatsBot;
  url_panel?: string;
  mensaje?: string;
}

export type EstadoSaludDestino = 'ok' | 'error' | 'desactivado' | 'sin_clave' | 'sin_datos';

export interface SaludDestinoBot {
  estado: EstadoSaludDestino;
  por_bot: Record<string, string>;
}

export interface ResumenDestinosBots {
  omni: SaludDestinoBot;
  cxc: SaludDestinoBot;
  gemini: SaludDestinoBot;
  outbox_pendientes: number;
  ingestas: Record<string, number>;
  bots_en_linea: number;
  bots_total: number;
}

const BASE = '/bots';

function extraerItems<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object' && 'items' in raw) {
    const items = (raw as { items: unknown }).items;
    if (Array.isArray(items)) return items as T[];
  }
  return toList<T>(raw);
}

export const ingestasService = {
  getAll: async (f: { estado?: EstadoIngesta | ''; kind?: KindIngesta | '' } = {}): Promise<Ingesta[]> => {
    const qs = new URLSearchParams();
    if (f.estado) qs.set('estado', f.estado);
    if (f.kind) qs.set('kind', f.kind);
    const q = qs.toString();
    return toList<Ingesta>(await get<unknown>(`${BASE}/ingest/${q ? '?' + q : ''}`));
  },

  /** Completa una ingesta incompleta: `cambios` = campos del borrador a fusionar. */
  completar: (id: string, cambios: Record<string, string>): Promise<Ingesta> =>
    post<Ingesta>(`${BASE}/ingest/${encodeURIComponent(id)}/completar/`, { cambios }),

  /** Encola el empuje en borrador hacia Odoo para una ingesta sincronizable completa. */
  sincronizar: (id: string): Promise<Ingesta> =>
    post<Ingesta>(`${BASE}/ingest/${encodeURIComponent(id)}/sincronizar/`, {}),
};

export const botUsuariosService = {
  getAll: async (): Promise<BotUsuario[]> =>
    toList<BotUsuario>(await get<unknown>(`${BASE}/usuarios/`)),

  create: (p: BotUsuarioPayload): Promise<BotUsuario> => {
    const body: Record<string, unknown> = {
      telegram_user_id: p.telegram_user_id,
      usuario: p.usuario,
      nombre: p.nombre,
    };
    if (p.bots !== undefined) body.bots = p.bots;
    return post<BotUsuario>(`${BASE}/usuarios/`, body);
  },

  update: (id: string, p: Partial<BotUsuarioPayload>): Promise<BotUsuario> => {
    const body: Record<string, unknown> = {};
    if (p.telegram_user_id !== undefined) body.telegram_user_id = p.telegram_user_id;
    if (p.usuario !== undefined) body.usuario = p.usuario;
    if (p.nombre !== undefined) body.nombre = p.nombre;
    if (p.bots !== undefined) body.bots = p.bots;
    return patch<BotUsuario>(`${BASE}/usuarios/${encodeURIComponent(id)}/`, body);
  },

  remove: (id: string): Promise<void> => del<void>(`${BASE}/usuarios/${encodeURIComponent(id)}/`),
};

export const botsControlService = {
  listarFlota: async (): Promise<ResumenBotFlota[]> =>
    extraerItems<ResumenBotFlota>(await get<unknown>(`${BASE}/control/`)),

  obtenerDetalle: (codigo: string): Promise<DetalleBotFlota> =>
    get<DetalleBotFlota>(`${BASE}/control/${encodeURIComponent(codigo)}/`),

  actualizarBot: (codigo: string, cambios: BotControlPatchPayload): Promise<DetalleBotFlota> =>
    patch<DetalleBotFlota>(`${BASE}/control/${encodeURIComponent(codigo)}/`, { ...cambios }),

  obtenerDestinos: (): Promise<ResumenDestinosBots> =>
    get<ResumenDestinosBots>(`${BASE}/destinos/`),

  listarBitacora: async (f: { entidad?: string; limite?: number } = {}): Promise<EntradaBitacoraBot[]> => {
    const qs = new URLSearchParams();
    if (f.entidad) qs.set('entidad', f.entidad);
    if (f.limite) qs.set('limite', String(f.limite));
    const q = qs.toString();
    return extraerItems<EntradaBitacoraBot>(await get<unknown>(`${BASE}/bitacora/${q ? '?' + q : ''}`));
  },
};
