import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  proveedoresService,
  contactosProveedorService,
  cuentasBancariasProveedorService,
  type ProveedorPayload,
  type ContactoProveedorPayload,
  type CuentaBancariaProveedorPayload,
} from '../services/proveedoresService';

const proveedorPayload: ProveedorPayload = {
  id_empresa: 'e1',
  razon_social: 'ACME Suministros C.A.',
  nombre_comercial: 'ACME',
  rif: 'J-12345678',
  direccion: 'Av. Principal',
  telefono: '04141234567',
  email: 'ventas@acme.com',
  referencia_externa: 'EXT-1',
};

describe('proveedoresService CRUD', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa y search', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_proveedor: 'p1' }] });
    const r = await proveedoresService.getAll({ empresa: 'e1', search: 'acme' });
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/?empresa=e1&search=acme');
    expect(r).toEqual([{ id_proveedor: 'p1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_proveedor: 'p1' }]);
    await proveedoresService.getAll();
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/');
  });

  it('getAll con objeto vacío pega al endpoint base (rama params sin claves)', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await proveedoresService.getAll({});
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/');
  });

  it('getAll solo con empresa arma el querystring sin search', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await proveedoresService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/?empresa=e1');
  });

  it('getAll solo con search arma el querystring sin empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await proveedoresService.getAll({ search: 'acme' });
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/?search=acme');
  });

  it('getAll normaliza respuesta paginada (toList con results)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 1, results: [{ id_proveedor: 'p1' }] });
    const r = await proveedoresService.getAll();
    expect(r).toEqual([{ id_proveedor: 'p1' }]);
  });

  it('getAll normaliza array directo (toList con array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_proveedor: 'p1' }, { id_proveedor: 'p2' }]);
    const r = await proveedoresService.getAll();
    expect(r.map((p) => p.id_proveedor)).toEqual(['p1', 'p2']);
  });

  it('getAll ante respuesta inesperada devuelve [] (toList fallback)', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    const r = await proveedoresService.getAll();
    expect(r).toEqual([]);
  });

  it('create propaga el error del backend (rama de rechazo)', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(proveedoresService.create(proveedorPayload)).rejects.toThrow('boom');
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_proveedor: 'p1' });
    await proveedoresService.getById('p1');
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/p1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_proveedor: 'p2' });
    await proveedoresService.create(proveedorPayload);
    expect(post).toHaveBeenCalledWith('/proveedores/proveedores/', proveedorPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_proveedor: 'p2' });
    await proveedoresService.update('p2', proveedorPayload);
    expect(patch).toHaveBeenCalledWith('/proveedores/proveedores/p2/', proveedorPayload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await proveedoresService.remove('p2');
    expect(del).toHaveBeenCalledWith('/proveedores/proveedores/p2/');
  });

  it('buscarPorRif normaliza la lista y codifica el rif', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_proveedor: 'p1' }] });
    const r = await proveedoresService.buscarPorRif('J-123');
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/buscar-por-rif/?rif=J-123');
    expect(r).toEqual([{ id_proveedor: 'p1' }]);
  });

  it('buscarPorRif normaliza array directo y codifica caracteres especiales', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_proveedor: 'p1' }]);
    const r = await proveedoresService.buscarPorRif('J-12 34');
    expect(get).toHaveBeenCalledWith('/proveedores/proveedores/buscar-por-rif/?rif=J-12%2034');
    expect(r).toEqual([{ id_proveedor: 'p1' }]);
  });
});

describe('contactosProveedorService', () => {
  beforeEach(() => vi.clearAllMocks());

  const contactoPayload: ContactoProveedorPayload = {
    id_proveedor: 'p1',
    nombre: 'Ana',
    apellido: 'Pérez',
    cargo: 'Ventas',
    telefono: '0414',
    email: 'ana@acme.com',
    es_contacto_principal: true,
    area_responsabilidad: 'Comercial',
    observaciones: null,
  };

  it('getAll filtra por proveedor en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_contacto: 'k1', id_proveedor: 'p1' },
      { id_contacto: 'k2', id_proveedor: 'otro' },
    ]);
    const r = await contactosProveedorService.getAll({ proveedor: 'p1' });
    expect(get).toHaveBeenCalledWith('/proveedores/contactos-proveedor/');
    expect(r.map((c) => c.id_contacto)).toEqual(['k1']);
  });

  it('getAll sin proveedor devuelve la lista completa (normalizada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_contacto: 'k1', id_proveedor: 'p1' }],
    });
    const r = await contactosProveedorService.getAll();
    expect(r.map((c) => c.id_contacto)).toEqual(['k1']);
  });

  it('getAll filtra por proveedor sobre respuesta paginada (results + filtro)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_contacto: 'k1', id_proveedor: 'p1' },
        { id_contacto: 'k2', id_proveedor: 'otro' },
      ],
    });
    const r = await contactosProveedorService.getAll({ proveedor: 'p1' });
    expect(r.map((c) => c.id_contacto)).toEqual(['k1']);
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('dup'));
    await expect(contactosProveedorService.create(contactoPayload)).rejects.toThrow('dup');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_contacto: 'k1' });
    await contactosProveedorService.create(contactoPayload);
    expect(post).toHaveBeenCalledWith('/proveedores/contactos-proveedor/', contactoPayload);

    vi.mocked(patch).mockResolvedValue({ id_contacto: 'k1' });
    await contactosProveedorService.update('k1', contactoPayload);
    expect(patch).toHaveBeenCalledWith('/proveedores/contactos-proveedor/k1/', contactoPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await contactosProveedorService.remove('k1');
    expect(del).toHaveBeenCalledWith('/proveedores/contactos-proveedor/k1/');
  });
});

describe('cuentasBancariasProveedorService', () => {
  beforeEach(() => vi.clearAllMocks());

  const cuentaPayload: CuentaBancariaProveedorPayload = {
    id_proveedor: 'p1',
    nombre_banco: 'Banco X',
    numero_cuenta: '0102-0000-0000000000',
    tipo_cuenta: 'CORRIENTE',
    moneda: 'm1',
    titular_cuenta: 'ACME C.A.',
    identificacion_titular: 'J-12345678',
    es_cuenta_principal: true,
    observaciones: null,
  };

  it('getAll filtra por proveedor', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_cuenta_bancaria: 'b1', id_proveedor: 'p1' },
      { id_cuenta_bancaria: 'b2', id_proveedor: 'otro' },
    ]);
    const r = await cuentasBancariasProveedorService.getAll({ proveedor: 'p1' });
    expect(get).toHaveBeenCalledWith('/proveedores/cuentas-bancarias-proveedor/');
    expect(r.map((c) => c.id_cuenta_bancaria)).toEqual(['b1']);
  });

  it('getAll sin proveedor devuelve todo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_cuenta_bancaria: 'b1', id_proveedor: 'p1' }]);
    const r = await cuentasBancariasProveedorService.getAll();
    expect(r.map((c) => c.id_cuenta_bancaria)).toEqual(['b1']);
  });

  it('getAll filtra por proveedor sobre respuesta paginada (results + filtro)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_cuenta_bancaria: 'b1', id_proveedor: 'p1' },
        { id_cuenta_bancaria: 'b2', id_proveedor: 'otro' },
      ],
    });
    const r = await cuentasBancariasProveedorService.getAll({ proveedor: 'p1' });
    expect(r.map((c) => c.id_cuenta_bancaria)).toEqual(['b1']);
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('dup'));
    await expect(cuentasBancariasProveedorService.create(cuentaPayload)).rejects.toThrow('dup');
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_cuenta_bancaria: 'b1' });
    await cuentasBancariasProveedorService.create(cuentaPayload);
    expect(post).toHaveBeenCalledWith(
      '/proveedores/cuentas-bancarias-proveedor/',
      cuentaPayload,
    );

    vi.mocked(patch).mockResolvedValue({ id_cuenta_bancaria: 'b1' });
    await cuentasBancariasProveedorService.update('b1', cuentaPayload);
    expect(patch).toHaveBeenCalledWith(
      '/proveedores/cuentas-bancarias-proveedor/b1/',
      cuentaPayload,
    );

    vi.mocked(del).mockResolvedValue(undefined);
    await cuentasBancariasProveedorService.remove('b1');
    expect(del).toHaveBeenCalledWith('/proveedores/cuentas-bancarias-proveedor/b1/');
  });
});
