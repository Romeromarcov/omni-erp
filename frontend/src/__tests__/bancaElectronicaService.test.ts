import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  cuentasBancariasEmpresaService,
  type CuentaBancariaEmpresaPayload,
} from '../services/bancaElectronicaService';

const BASE = '/banca-electronica/cuentas-bancarias-empresa/';

const payload: CuentaBancariaEmpresaPayload = {
  empresa: 'e1',
  banco: 'Banco de Venezuela',
  numero_cuenta: '0102-1234-5678-9012',
  tipo_cuenta: 'corriente',
  moneda: 'mon-1',
  saldo_actual: '1500.00',
  activa: true,
};

describe('cuentasBancariasEmpresaService CRUD', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa (respuesta paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id: 'c1' }] });
    const r = await cuentasBancariasEmpresaService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith(`${BASE}?empresa=e1`);
    expect(r).toEqual([{ id: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base (respuesta array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id: 'c1' }]);
    const r = await cuentasBancariasEmpresaService.getAll();
    expect(get).toHaveBeenCalledWith(BASE);
    expect(r).toEqual([{ id: 'c1' }]);
  });

  it('getAll con params vacío omite el querystring', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await cuentasBancariasEmpresaService.getAll({});
    expect(get).toHaveBeenCalledWith(BASE);
  });

  it('getAll normaliza respuesta inesperada a lista vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(null);
    const r = await cuentasBancariasEmpresaService.getAll({ empresa: 'e1' });
    expect(r).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id: 'c1' });
    await cuentasBancariasEmpresaService.getById('c1');
    expect(get).toHaveBeenCalledWith(`${BASE}c1/`);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id: 'c2' });
    await cuentasBancariasEmpresaService.create(payload);
    expect(post).toHaveBeenCalledWith(BASE, payload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id: 'c2' });
    await cuentasBancariasEmpresaService.update('c2', payload);
    expect(patch).toHaveBeenCalledWith(`${BASE}c2/`, payload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await cuentasBancariasEmpresaService.remove('c2');
    expect(del).toHaveBeenCalledWith(`${BASE}c2/`);
  });

  it('propaga el error del backend en getAll', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('boom'));
    await expect(cuentasBancariasEmpresaService.getAll({ empresa: 'e1' })).rejects.toThrow('boom');
  });
});
