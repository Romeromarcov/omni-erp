import { post, get, patch, del } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

/**
 * Proveedor (maestro): datos fiscales (RIF), contacto y cuentas bancarias para
 * pagos. La isolación multi-tenant la hace el backend (get_empresas_visible +
 * `?empresa=`). El RIF es único por empresa (unique_together id_empresa+rif).
 *
 * NOTA: `comprasService` mantiene su propio helper `/proveedores/` para las
 * pantallas de compras — este servicio NO lo reemplaza; son consumidores
 * distintos del mismo recurso backend.
 */
export interface Proveedor {
  id_proveedor: string;
  id_empresa: string;
  razon_social: string;
  nombre_comercial?: string | null;
  rif: string;
  direccion?: string | null;
  telefono?: string | null;
  email?: string | null;
  referencia_externa?: string | null;
  contacto?: string | null;
  activo?: boolean;
}

/**
 * Payload de escritura de Proveedor: whitelist explícita de campos editables
 * (CTF-005, defensa en profundidad CWE-915). El RIF lo valida el backend.
 */
export interface ProveedorPayload {
  id_empresa: string;
  razon_social: string;
  nombre_comercial: string | null;
  rif: string;
  direccion: string | null;
  telefono: string | null;
  email: string | null;
  referencia_externa: string | null;
}

export interface ContactoProveedor {
  id_contacto: string;
  id_proveedor: string;
  nombre: string;
  apellido: string;
  cargo: string | null;
  telefono: string | null;
  email: string | null;
  es_contacto_principal: boolean;
  area_responsabilidad: string | null;
  observaciones: string | null;
  activo?: boolean;
}

export interface ContactoProveedorPayload {
  id_proveedor: string;
  nombre: string;
  apellido: string;
  cargo: string | null;
  telefono: string | null;
  email: string | null;
  es_contacto_principal: boolean;
  area_responsabilidad: string | null;
  observaciones: string | null;
}

export type TipoCuentaBancaria = 'CORRIENTE' | 'AHORRO' | 'VISTA' | 'PLAZO_FIJO';

export interface CuentaBancariaProveedor {
  id_cuenta_bancaria: string;
  id_proveedor: string;
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuentaBancaria;
  moneda: string;
  titular_cuenta: string | null;
  identificacion_titular: string | null;
  es_cuenta_principal: boolean;
  observaciones: string | null;
  activo?: boolean;
}

export interface CuentaBancariaProveedorPayload {
  id_proveedor: string;
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuentaBancaria;
  moneda: string;
  titular_cuenta: string | null;
  identificacion_titular: string | null;
  es_cuenta_principal: boolean;
  observaciones: string | null;
}

// ── Maestro de Proveedores (CRUD + acciones) ──────────────────────────────────

export const proveedoresService = {
  getAll: async (params?: { empresa?: string; search?: string }): Promise<Proveedor[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.search) qs.set('search', params.search);
    const query = qs.toString();
    const response = await get<PaginatedResponse<Proveedor> | Proveedor[]>(
      `/proveedores/proveedores/${query ? '?' + query : ''}`,
    );
    return toList<Proveedor>(response);
  },

  getById: async (id: string): Promise<Proveedor> => {
    return get<Proveedor>(`/proveedores/proveedores/${id}/`);
  },

  create: async (payload: ProveedorPayload): Promise<Proveedor> =>
    post<Proveedor>('/proveedores/proveedores/', payload as unknown as Record<string, unknown>),

  update: async (id: string, payload: ProveedorPayload): Promise<Proveedor> =>
    patch<Proveedor>(
      `/proveedores/proveedores/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/proveedores/proveedores/${id}/`);
  },

  buscarPorRif: async (rif: string): Promise<Proveedor[]> => {
    const response = await get<PaginatedResponse<Proveedor> | Proveedor[]>(
      `/proveedores/proveedores/buscar-por-rif/?rif=${encodeURIComponent(rif)}`,
    );
    return toList<Proveedor>(response);
  },
};

// ── Contactos de proveedor ────────────────────────────────────────────────────

export const contactosProveedorService = {
  getAll: async (params?: { proveedor?: string }): Promise<ContactoProveedor[]> => {
    const response = await get<PaginatedResponse<ContactoProveedor> | ContactoProveedor[]>(
      '/proveedores/contactos-proveedor/',
    );
    const lista = toList<ContactoProveedor>(response);
    // El backend filtra por empresa (vía FK) pero no por proveedor; reforzamos el
    // filtro en el cliente para que cada detalle muestre solo sus contactos.
    return params?.proveedor
      ? lista.filter((c) => c.id_proveedor === params.proveedor)
      : lista;
  },

  create: async (payload: ContactoProveedorPayload): Promise<ContactoProveedor> =>
    post<ContactoProveedor>(
      '/proveedores/contactos-proveedor/',
      payload as unknown as Record<string, unknown>,
    ),

  update: async (id: string, payload: ContactoProveedorPayload): Promise<ContactoProveedor> =>
    patch<ContactoProveedor>(
      `/proveedores/contactos-proveedor/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/proveedores/contactos-proveedor/${id}/`);
  },
};

// ── Cuentas bancarias de proveedor (para pagos) ───────────────────────────────

export const cuentasBancariasProveedorService = {
  getAll: async (params?: { proveedor?: string }): Promise<CuentaBancariaProveedor[]> => {
    const response = await get<
      PaginatedResponse<CuentaBancariaProveedor> | CuentaBancariaProveedor[]
    >('/proveedores/cuentas-bancarias-proveedor/');
    const lista = toList<CuentaBancariaProveedor>(response);
    return params?.proveedor
      ? lista.filter((c) => c.id_proveedor === params.proveedor)
      : lista;
  },

  create: async (
    payload: CuentaBancariaProveedorPayload,
  ): Promise<CuentaBancariaProveedor> =>
    post<CuentaBancariaProveedor>(
      '/proveedores/cuentas-bancarias-proveedor/',
      payload as unknown as Record<string, unknown>,
    ),

  update: async (
    id: string,
    payload: CuentaBancariaProveedorPayload,
  ): Promise<CuentaBancariaProveedor> =>
    patch<CuentaBancariaProveedor>(
      `/proveedores/cuentas-bancarias-proveedor/${id}/`,
      payload as unknown as Record<string, unknown>,
    ),

  remove: async (id: string): Promise<void> => {
    await del<void>(`/proveedores/cuentas-bancarias-proveedor/${id}/`);
  },
};
