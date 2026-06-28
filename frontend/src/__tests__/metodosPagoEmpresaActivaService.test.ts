import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  patch: vi.fn(),
}));

import { get, patch } from '../services/api';
import {
  fetchMetodosPagoEmpresaActivos,
  updateMonedasMetodoPagoEmpresaActiva,
} from '../services/metodosPagoEmpresaActiva';

describe('fetchMetodosPagoEmpresaActivos', () => {
  beforeEach(() => vi.clearAllMocks());

  it('devuelve el array directo y arma el querystring con la empresa', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id: 'link-1', nombre_metodo: 'Transferencia', monedas: ['m1'] },
    ]);
    const r = await fetchMetodosPagoEmpresaActivos('e1');
    // Recorre páginas: la primera petición incluye page=1.
    expect(get).toHaveBeenCalledWith('/finanzas/metodos-pago-empresa-activas/?empresa=e1&page=1');
    expect(r.map((m) => m.id)).toEqual(['link-1']);
  });

  it('extrae results de una respuesta paginada (rama results)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id: 'link-1', nombre_metodo: 'Efectivo', monedas: [] }],
    });
    expect((await fetchMetodosPagoEmpresaActivos('e1')).length).toBe(1);
  });

  it('ante respuesta inesperada devuelve [] (rama fallback)', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await fetchMetodosPagoEmpresaActivos('e1')).toEqual([]);
  });

  it('ante objeto sin results devuelve [] (rama fallback con objeto)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0 } as unknown as never);
    expect(await fetchMetodosPagoEmpresaActivos('e1')).toEqual([]);
  });
});

describe('updateMonedasMetodoPagoEmpresaActiva', () => {
  beforeEach(() => vi.clearAllMocks());

  it('parchea las monedas del método por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id: 'link-1' });
    await updateMonedasMetodoPagoEmpresaActiva('link-1', ['m1', 'm2']);
    expect(patch).toHaveBeenCalledWith('/finanzas/metodos-pago-empresa-activas/link-1/', {
      monedas: ['m1', 'm2'],
    });
  });

  it('propaga el error del backend', async () => {
    vi.mocked(patch).mockRejectedValueOnce(new Error('boom'));
    await expect(updateMonedasMetodoPagoEmpresaActiva('link-1', [])).rejects.toThrow('boom');
  });
});
