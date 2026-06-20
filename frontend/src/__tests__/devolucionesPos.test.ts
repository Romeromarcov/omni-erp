/**
 * Cobertura del servicio de devoluciones POS (Q1, ruta de dinero, sub-fase 1.G).
 * Verifica búsqueda por número (trim/encode/unwrap), endpoint de estado y el
 * POST de devolución con su Idempotency-Key.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(() => Promise.resolve({ results: [] })),
  post: vi.fn(() => Promise.resolve({})),
}));

import { get, post } from '../services/api';
import {
  buscarVentaPorNumero,
  getEstadoDevoluciones,
  devolverVenta,
} from '../services/devolucionesPos';

describe('devolucionesPos', () => {
  beforeEach(() => vi.clearAllMocks());

  it('buscarVentaPorNumero recorta y url-encodea el número', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_nota_venta: 'n1', numero_nota: 'NV 1', estado: 'ENTREGADA' }] });
    const r = await buscarVentaPorNumero('  NV 1  ');
    expect(vi.mocked(get).mock.calls[0][0]).toBe('/ventas/notas-venta/?numero_nota=NV%201');
    expect(r?.id_nota_venta).toBe('n1');
  });

  it('buscarVentaPorNumero acepta array plano y devuelve el primero', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_nota_venta: 'n2', numero_nota: 'NV-2', estado: 'ENTREGADA' }]);
    expect((await buscarVentaPorNumero('NV-2'))?.id_nota_venta).toBe('n2');
  });

  it('buscarVentaPorNumero devuelve null si no hay resultados', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [] });
    expect(await buscarVentaPorNumero('X')).toBeNull();
    vi.mocked(get).mockResolvedValueOnce(undefined);
    expect(await buscarVentaPorNumero('Y')).toBeNull();
  });

  it('getEstadoDevoluciones pega al endpoint de la venta', async () => {
    vi.mocked(get).mockResolvedValueOnce({ venta: {}, lineas: [], devoluciones: [] });
    await getEstadoDevoluciones('nv-9');
    expect(vi.mocked(get).mock.calls[0][0]).toBe('/ventas/notas-venta/nv-9/devoluciones/');
  });

  it('devolverVenta hace POST con payload e Idempotency-Key', async () => {
    vi.mocked(post).mockResolvedValueOnce({ pago_id: 'p1' });
    const payload = {
      almacen_id: 'a1', id_metodo_pago: 'm1',
      lineas: [{ id_detalle: 'd1', cantidad: '2' }], motivo: 'CAMBIO_CLIENTE',
    };
    const res = await devolverVenta('nv-1', payload, 'clave-dev');
    expect(res).toEqual({ pago_id: 'p1' });
    const [url, body, opts] = vi.mocked(post).mock.calls[0];
    expect(url).toBe('/ventas/notas-venta/nv-1/devolver/');
    expect(body).toEqual(payload);
    expect((opts as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe('clave-dev');
  });
});
