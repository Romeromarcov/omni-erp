import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  clientesService,
  contactosClienteService,
  direccionesClienteService,
  buscarClientes,
  fetchClientes,
  crearClienteConEmpresa,
  type ClientePayload,
  type ContactoClientePayload,
  type DireccionClientePayload,
} from '../services/clientesService';

const clientePayload: ClientePayload = {
  id_empresa: 'e1',
  razon_social: 'ACME C.A.',
  nombre_comercial: 'ACME',
  rif: 'J-12345678',
  direccion: 'Av. Principal',
  telefono: '04141234567',
  email: 'ventas@acme.com',
  tipo_cliente: 'CREDITO',
  limite_credito: '1000.00',
  dias_credito: 30,
};

describe('clientesService CRUD', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa y search', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_cliente: 'c1' }] });
    const r = await clientesService.getAll({ empresa: 'e1', search: 'acme' });
    expect(get).toHaveBeenCalledWith('/crm/clientes/?empresa=e1&search=acme');
    expect(r).toEqual([{ id_cliente: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_cliente: 'c1' }]);
    await clientesService.getAll();
    expect(get).toHaveBeenCalledWith('/crm/clientes/');
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_cliente: 'c1' });
    await clientesService.getById('c1');
    expect(get).toHaveBeenCalledWith('/crm/clientes/c1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_cliente: 'c2' });
    await clientesService.create(clientePayload);
    expect(post).toHaveBeenCalledWith('/crm/clientes/', clientePayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_cliente: 'c2' });
    await clientesService.update('c2', clientePayload);
    expect(patch).toHaveBeenCalledWith('/crm/clientes/c2/', clientePayload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await clientesService.remove('c2');
    expect(del).toHaveBeenCalledWith('/crm/clientes/c2/');
  });
});

describe('clientesService acciones', () => {
  beforeEach(() => vi.clearAllMocks());

  it('buscarPorRif normaliza la lista', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_cliente: 'c1' }] });
    const r = await clientesService.buscarPorRif('J-123');
    expect(get).toHaveBeenCalledWith('/crm/clientes/buscar-por-rif/?rif=J-123');
    expect(r).toEqual([{ id_cliente: 'c1' }]);
  });

  it('historialVentas pega al endpoint de historial', async () => {
    vi.mocked(get).mockResolvedValueOnce({ cliente_id: 'c1', pedidos: [] });
    const r = await clientesService.historialVentas('c1');
    expect(get).toHaveBeenCalledWith('/crm/clientes/c1/historial-ventas/');
    expect(r.pedidos).toEqual([]);
  });

  it('creditoDisponible pega al endpoint de crédito', async () => {
    vi.mocked(get).mockResolvedValueOnce({ credito_disponible: '500.00' });
    const r = await clientesService.creditoDisponible('c1');
    expect(get).toHaveBeenCalledWith('/crm/clientes/c1/credito-disponible/');
    expect(r.credito_disponible).toBe('500.00');
  });
});

describe('contactosClienteService', () => {
  beforeEach(() => vi.clearAllMocks());

  const contactoPayload: ContactoClientePayload = {
    id_empresa: 'e1',
    id_cliente: 'c1',
    nombre_contacto: 'Ana',
    apellido_contacto: 'Pérez',
    cargo: 'Compras',
    telefono_directo: null,
    telefono_movil: '0414',
    email_contacto: 'ana@acme.com',
    es_contacto_principal: true,
    observaciones: null,
  };

  it('getAll filtra por cliente en el querystring y en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_contacto: 'k1', id_cliente: 'c1' },
      { id_contacto: 'k2', id_cliente: 'otro' },
    ]);
    const r = await contactosClienteService.getAll({ cliente: 'c1' });
    expect(get).toHaveBeenCalledWith('/crm/contactos-cliente/?id_cliente=c1');
    expect(r.map((c) => c.id_contacto)).toEqual(['k1']);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_contacto: 'k1' });
    await contactosClienteService.create(contactoPayload);
    expect(post).toHaveBeenCalledWith('/crm/contactos-cliente/', contactoPayload);

    vi.mocked(patch).mockResolvedValue({ id_contacto: 'k1' });
    await contactosClienteService.update('k1', contactoPayload);
    expect(patch).toHaveBeenCalledWith('/crm/contactos-cliente/k1/', contactoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await contactosClienteService.remove('k1');
    expect(del).toHaveBeenCalledWith('/crm/contactos-cliente/k1/');
  });
});

describe('direccionesClienteService', () => {
  beforeEach(() => vi.clearAllMocks());

  const direccionPayload: DireccionClientePayload = {
    id_empresa: 'e1',
    id_cliente: 'c1',
    tipo_direccion: 'FISCAL',
    direccion_completa: 'Av. Principal, Edif. X',
    ciudad: 'Caracas',
    estado_provincia: 'Distrito Capital',
    codigo_postal: null,
    pais: 'Venezuela',
    telefono: null,
    persona_contacto: null,
    es_direccion_principal: true,
    observaciones: null,
  };

  it('getAll filtra por cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_direccion: 'd1', id_cliente: 'c1' },
      { id_direccion: 'd2', id_cliente: 'otro' },
    ]);
    const r = await direccionesClienteService.getAll({ cliente: 'c1' });
    expect(get).toHaveBeenCalledWith('/crm/direcciones-cliente/?id_cliente=c1');
    expect(r.map((d) => d.id_direccion)).toEqual(['d1']);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_direccion: 'd1' });
    await direccionesClienteService.create(direccionPayload);
    expect(post).toHaveBeenCalledWith('/crm/direcciones-cliente/', direccionPayload);

    vi.mocked(patch).mockResolvedValue({ id_direccion: 'd1' });
    await direccionesClienteService.update('d1', direccionPayload);
    expect(patch).toHaveBeenCalledWith('/crm/direcciones-cliente/d1/', direccionPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await direccionesClienteService.remove('d1');
    expect(del).toHaveBeenCalledWith('/crm/direcciones-cliente/d1/');
  });
});

describe('funciones de compatibilidad (Ventas/POS)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('buscarClientes incluye search y empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_cliente: 'c1' }] });
    await buscarClientes('acme', 'e1');
    expect(get).toHaveBeenCalledWith('/crm/clientes/?search=acme&empresa=e1');
  });

  it('fetchClientes filtra por empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await fetchClientes('e1');
    expect(get).toHaveBeenCalledWith('/crm/clientes/?empresa=e1');
  });

  it('crearClienteConEmpresa postea al endpoint de clientes', async () => {
    vi.mocked(post).mockResolvedValue({ id_cliente: 'c-auto' });
    await crearClienteConEmpresa({
      razon_social: 'X',
      rif: 'J-1',
      telefono: '0414',
      id_empresa: 'e1',
    });
    expect(post).toHaveBeenCalledWith('/crm/clientes/', expect.objectContaining({ id_empresa: 'e1' }));
  });
});
