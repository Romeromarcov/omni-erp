import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  fetchText: vi.fn(),
  fetchBlob: vi.fn(),
}));

import { fetchText, fetchBlob } from '../services/api';
import { libroService } from '../services/fiscalService';

const TXT_VENTAS = [
  'rif_emisor|rif_receptor|fecha|nro_ctrl|nro_fac|base_imponible|iva|total',
  'J123|V456|2026-06-01|0001|F001|100.00|16.00|116.00',
].join('\n');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('libroService — descarga TXT con Accept compatible (no 406)', () => {
  // Regresión: el backend (APIView DRF con solo JSONRenderer) responde 406 si el
  // Accept es 'text/plain'. El frontend debe pedir '*/*' para que DRF acepte.
  it('fetchLibroVentasTxt usa Accept: */* (no text/plain)', async () => {
    vi.mocked(fetchText).mockResolvedValue(TXT_VENTAS);

    const entries = await libroService.fetchLibroVentasTxt('emp1', '2026-06');

    expect(fetchText).toHaveBeenCalledTimes(1);
    const [endpoint, options] = vi.mocked(fetchText).mock.calls[0];
    expect(endpoint).toBe('/fiscal/libro-ventas/?empresa=emp1&periodo=2026-06');
    expect(options?.headers).toEqual({ Accept: '*/*' });
    expect((options?.headers as Record<string, string>).Accept).not.toBe('text/plain');

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ rif_emisor: 'J123', total: '116.00' });
  });

  it('fetchLibroComprasTxt usa Accept: */* (no text/plain)', async () => {
    vi.mocked(fetchText).mockResolvedValue(TXT_VENTAS);

    await libroService.fetchLibroComprasTxt('emp1', '2026-06');

    const [endpoint, options] = vi.mocked(fetchText).mock.calls[0];
    expect(endpoint).toBe('/fiscal/libro-compras/?empresa=emp1&periodo=2026-06');
    expect(options?.headers).toEqual({ Accept: '*/*' });
  });

  it('downloadLibroVentasTxt pide el blob con Accept: */*', async () => {
    const blob = new Blob([TXT_VENTAS], { type: 'text/plain' });
    vi.mocked(fetchBlob).mockResolvedValue(blob);

    // jsdom: stub de las APIs de descarga.
    const createObjectURL = vi.fn(() => 'blob:mock');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);

    await libroService.downloadLibroVentasTxt('emp1', '2026-06');

    const [endpoint, options] = vi.mocked(fetchBlob).mock.calls[0];
    expect(endpoint).toBe('/fiscal/libro-ventas/?empresa=emp1&periodo=2026-06');
    expect(options?.headers).toEqual({ Accept: '*/*' });
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock');

    clickSpy.mockRestore();
  });

  it('downloadLibroComprasTxt pide el blob con Accept: */*', async () => {
    const blob = new Blob([TXT_VENTAS], { type: 'text/plain' });
    vi.mocked(fetchBlob).mockResolvedValue(blob);

    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:mock'), configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);

    await libroService.downloadLibroComprasTxt('emp1', '2026-06');

    const [endpoint, options] = vi.mocked(fetchBlob).mock.calls[0];
    expect(endpoint).toBe('/fiscal/libro-compras/?empresa=emp1&periodo=2026-06');
    expect(options?.headers).toEqual({ Accept: '*/*' });

    clickSpy.mockRestore();
  });
});
