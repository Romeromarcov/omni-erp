import { post, get, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';
import { isSimilar } from '../utils/fuzzyDuplicate';

// ── Types ──────────────────────────────────────────────────────────────────

export type TipoCliente = 'CONTADO' | 'CREDITO';

/**
 * Cliente del CRM. Los montos (limite_credito) viajan como string para no perder
 * precisión del DecimalField del backend (R-CODE-4).
 *
 * Compatibilidad: las páginas de ventas que importan `Cliente` solo consumen un
 * subconjunto (id_cliente, razon_social, rif, telefono); el resto es opcional
 * para no romper sus usos previos al maestro CRM.
 */
export interface Cliente {
  id_cliente: string;
  razon_social: string;
  nombre_comercial?: string | null;
  rif: string;
  direccion?: string | null;
  telefono?: string | null;
  email?: string | null;
  tipo_cliente?: TipoCliente;
  limite_credito?: string;
  dias_credito?: number;
  id_empresa?: string;
  activo?: boolean;
  contacto?: string | null;
}

/**
 * Payload de escritura de Cliente: whitelist explícita de campos editables
 * (CTF-005, defensa en profundidad CWE-915). Los montos viajan como string
 * (R-CODE-4); el RIF lo valida el backend.
 */
export interface ClientePayload {
  id_empresa: string;
  razon_social: string;
  nombre_comercial: string | null;
  rif: string;
  direccion: string | null;
  telefono: string | null;
  email: string | null;
  tipo_cliente: TipoCliente;
  limite_credito: string;
  dias_credito: number;
}

export interface ContactoCliente {
  id_contacto: string;
  id_empresa: string;
  id_cliente: string;
  nombre_contacto: string;
  apellido_contacto: string;
  cargo: string | null;
  telefono_directo: string | null;
  telefono_movil: string | null;
  email_contacto: string;
  es_contacto_principal: boolean;
  observaciones: string | null;
  activo?: boolean;
}

export interface ContactoClientePayload {
  id_empresa: string;
  id_cliente: string;
  nombre_contacto: string;
  apellido_contacto: string;
  cargo: string | null;
  telefono_directo: string | null;
  telefono_movil: string | null;
  email_contacto: string;
  es_contacto_principal: boolean;
  observaciones: string | null;
}

export type TipoDireccion = 'FISCAL' | 'COMERCIAL' | 'ENTREGA' | 'FACTURACION' | 'OTRA';

export interface DireccionCliente {
  id_direccion: string;
  id_empresa: string;
  id_cliente: string;
  tipo_direccion: TipoDireccion;
  direccion_completa: string;
  ciudad: string;
  estado_provincia: string;
  codigo_postal: string | null;
  pais: string;
  telefono: string | null;
  persona_contacto: string | null;
  es_direccion_principal: boolean;
  observaciones: string | null;
  activo?: boolean;
}

export interface DireccionClientePayload {
  id_empresa: string;
  id_cliente: string;
  tipo_direccion: TipoDireccion;
  direccion_completa: string;
  ciudad: string;
  estado_provincia: string;
  codigo_postal: string | null;
  pais: string;
  telefono: string | null;
  persona_contacto: string | null;
  es_direccion_principal: boolean;
  observaciones: string | null;
}

/** Respuesta de `credito-disponible`. Cliente de contado → credito_disponible null. */
export interface CreditoDisponible {
  cliente_id?: string;
  limite_credito?: string;
  saldo_pendiente?: string;
  credito_disponible: string | null;
  bloqueado?: boolean;
  detalle?: string;
}

/** Pedido tal como lo expone `historial-ventas` (subconjunto consumido por la UI). */
export interface PedidoHistorial {
  id_pedido: string;
  numero_pedido: string;
  fecha_pedido: string;
  estado: string;
  [key: string]: unknown;
}

export interface HistorialVentas {
  cliente_id: string;
  razon_social: string;
  rif: string;
  tipo_cliente: TipoCliente;
  limite_credito: string;
  dias_credito: number;
  pedidos: PedidoHistorial[];
}

// ── Compatibilidad: funciones existentes consumidas por Ventas/POS ───────────
// NO cambiar sus firmas/exports: las usan hooks de venta, POS y modales.

export async function crearCliente(data: Omit<Cliente, 'id_cliente'>): Promise<Cliente> {
  return await post('/crm/clientes/', data as unknown as Record<string, unknown>);
}

export interface ClienteCreate {
  razon_social: string;
  rif: string;
  telefono: string;
  id_empresa: string;
  [key: string]: unknown; // Index signature
}

export async function crearClienteConEmpresa(data: ClienteCreate): Promise<Cliente> {
  return await post('/crm/clientes/', data);
}

export async function buscarClientes(query: string, empresaId?: string): Promise<Cliente[]> {
  const empresaParam = empresaId ? `&empresa=${empresaId}` : '';
  const response: Cliente[] | { results: Cliente[] } = await get(
    `/crm/clientes/?search=${encodeURIComponent(query)}${empresaParam}`,
  );
  return toList<Cliente>(response);
}

export async function buscarClientesSimilares(
  nombre: string,
  rif: string,
  empresaId?: string,
): Promise<Cliente[]> {
  if (!empresaId) return [];
  const response = await fetchClientes(empresaId);
  let clientes = toList<Cliente>(response);
  // Extraer tipo_rif (prefijo) del rif
  const tipoRifNuevo = rif.split('-')[0] || '';
  // Filtrar por similitud cruzada: nombre y rif similares al mismo cliente, y tipo_rif coincida
  clientes = clientes.filter((cli) => {
    const tipoRifExistente = cli.rif.split('-')[0] || '';
    const nombreSimilar = nombre && isSimilar(nombre, cli.razon_social, 70);
    const rifSimilar = rif && isSimilar(rif, cli.rif, 80);
    const tipoCoincide = tipoRifNuevo === tipoRifExistente;
    return nombreSimilar && rifSimilar && tipoCoincide;
  });
  return clientes; // No limitar, devolver todos los que cumplan
}

export async function fetchClientes(
  empresaId: string,
): Promise<Cliente[] | { results: Cliente[] }> {
  return get<Cliente[] | { results: Cliente[] }>(`/crm/clientes/?empresa=${empresaId}`);
}

// ── Maestro de Clientes (CRUD + acciones) ────────────────────────────────────

export const clientesService = {
  getAll: async (params?: { empresa?: string; search?: string }): Promise<Cliente[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<Cliente> | Cliente[]>(
      `/crm/clientes/${query ? '?' + query : ''}`,
    );
    return toList<Cliente>(response);
  },

  getById: async (id: string): Promise<Cliente> => {
    return get<Cliente>(`/crm/clientes/${id}/`);
  },

  create: async (payload: ClientePayload): Promise<Cliente> =>
    post<Cliente>('/crm/clientes/', payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ClientePayload): Promise<Cliente> =>
    patch<Cliente>(`/crm/clientes/${id}/`, payload as unknown as Record<string, unknown>),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/crm/clientes/${id}/`);
  },

  buscarPorRif: async (rif: string): Promise<Cliente[]> => {
    const response = await get<PaginatedResponse<Cliente> | Cliente[]>(
      `/crm/clientes/buscar-por-rif/?rif=${encodeURIComponent(rif)}`,
    );
    return toList<Cliente>(response);
  },

  historialVentas: async (id: string): Promise<HistorialVentas> => {
    return get<HistorialVentas>(`/crm/clientes/${id}/historial-ventas/`);
  },

  creditoDisponible: async (id: string): Promise<CreditoDisponible> => {
    return get<CreditoDisponible>(`/crm/clientes/${id}/credito-disponible/`);
  },
};

// ── Contactos de cliente ─────────────────────────────────────────────────────

export const contactosClienteService = {
  getAll: async (params?: { cliente?: string }): Promise<ContactoCliente[]> => {
    const qs = params?.cliente ? `?id_cliente=${params.cliente}` : '';
    const response = await get<PaginatedResponse<ContactoCliente> | ContactoCliente[]>(
      `/crm/contactos-cliente/${qs}`,
    );
    const lista = toList<ContactoCliente>(response);
    // El backend filtra por empresa pero no necesariamente por cliente; reforzamos
    // el filtro en el cliente para que cada detalle muestre solo sus contactos.
    return params?.cliente ? lista.filter((c) => c.id_cliente === params.cliente) : lista;
  },

  create: async (payload: ContactoClientePayload): Promise<ContactoCliente> =>
    post<ContactoCliente>('/crm/contactos-cliente/', payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ContactoClientePayload): Promise<ContactoCliente> =>
    patch<ContactoCliente>(
      `/crm/contactos-cliente/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/crm/contactos-cliente/${id}/`);
  },
};

// ── Direcciones de cliente ───────────────────────────────────────────────────

export const direccionesClienteService = {
  getAll: async (params?: { cliente?: string }): Promise<DireccionCliente[]> => {
    const qs = params?.cliente ? `?id_cliente=${params.cliente}` : '';
    const response = await get<PaginatedResponse<DireccionCliente> | DireccionCliente[]>(
      `/crm/direcciones-cliente/${qs}`,
    );
    const lista = toList<DireccionCliente>(response);
    return params?.cliente ? lista.filter((d) => d.id_cliente === params.cliente) : lista;
  },

  create: async (payload: DireccionClientePayload): Promise<DireccionCliente> =>
    post<DireccionCliente>(
      '/crm/direcciones-cliente/',
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: DireccionClientePayload): Promise<DireccionCliente> =>
    patch<DireccionCliente>(
      `/crm/direcciones-cliente/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/crm/direcciones-cliente/${id}/`);
  },
};
