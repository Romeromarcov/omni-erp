import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import { cuentasPorCobrarService } from '../services/cuentasPorCobrarService';
import { almacenesService } from '../services/almacenesService';

const cxc = {
  id: 1,
  empresa: 'emp-1',
  cliente: null,
  cliente_nombre: 'Cliente X',
  cliente_ref: null,
  monto: '100.00',
  saldo_pendiente: '40.00',
  fecha_emision: '2026-06-01',
  fecha_vencimiento: '2026-07-01',
  estado: 'parcial',
};

describe('cuentasPorCobrarService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getAllPaginated pasa page/page_size y devuelve la página', async () => {
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [cxc] });
    const res = await cuentasPorCobrarService.getAllPaginated(2, 10);
    expect(get).toHaveBeenCalledWith('/cxc/cuentas-por-cobrar/?page=2&page_size=10');
    expect(res.count).toBe(1);
    expect(res.results[0].saldo_pendiente).toBe('40.00');
  });

  it('getAllPaginated normaliza listas directas', async () => {
    vi.mocked(get).mockResolvedValue([cxc]);
    const res = await cuentasPorCobrarService.getAllPaginated();
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [cxc] });
  });

  it('getAllPaginated tolera respuestas inesperadas', async () => {
    vi.mocked(get).mockResolvedValue(null);
    const res = await cuentasPorCobrarService.getAllPaginated();
    expect(res.results).toEqual([]);
    expect(res.count).toBe(0);
  });

  it('crearAbono envía el contrato P0-2 con monto como string decimal', async () => {
    vi.mocked(post).mockResolvedValue({ id: 9, cuenta_por_cobrar: 1, monto: '40.00', descripcion: '' });
    await cuentasPorCobrarService.crearAbono({ cuenta_por_cobrar: 1, monto: '40.00', descripcion: 'abono' });
    expect(post).toHaveBeenCalledWith('/cxc/abonos-cxc/', {
      cuenta_por_cobrar: 1,
      monto: '40.00',
      descripcion: 'abono',
    });
  });
});

describe('almacenesService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getAll consulta /almacenes/almacenes/ y normaliza paginado', async () => {
    const alm = { id_almacen: 'a1', nombre_almacen: 'Central', id_empresa: 'emp-1' };
    vi.mocked(get).mockResolvedValue({ results: [alm], count: 1 });
    const res = await almacenesService.getAll();
    expect(get).toHaveBeenCalledWith('/almacenes/almacenes/');
    expect(res).toEqual([alm]);
  });
});
