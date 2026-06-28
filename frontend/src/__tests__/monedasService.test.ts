import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
}));

import { get } from '../services/api';
import { fetchMonedas } from '../services/monedas';

describe('fetchMonedas', () => {
  beforeEach(() => vi.clearAllMocks());

  it('devuelve el array directo (rama Array.isArray)', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_moneda: 'm1', nombre: 'Dólar', codigo_iso: 'USD' },
    ]);
    const r = await fetchMonedas();
    expect(get).toHaveBeenCalledWith('/finanzas/monedas/');
    expect(r.map((m) => m.codigo_iso)).toEqual(['USD']);
  });

  it('extrae results de una respuesta paginada (rama results)', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [{ id_moneda: 'm1', nombre: 'Bolívar', codigo_iso: 'VES' }],
    });
    expect((await fetchMonedas()).length).toBe(1);
  });

  it('ante respuesta inesperada devuelve [] (rama fallback)', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await fetchMonedas()).toEqual([]);
  });

  it('ante objeto sin results devuelve [] (rama fallback con objeto)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ count: 0 } as unknown as never);
    expect(await fetchMonedas()).toEqual([]);
  });
});
