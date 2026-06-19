/**
 * Cobertura del servicio de pagos (Q1: cobertura frontend, ruta de dinero).
 * Verifica construcción de query params, unwrapping de respuesta, cabecera de
 * idempotencia en createPago y la delegación por tipo de documento.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(() => Promise.resolve({ results: [] })),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
  del: vi.fn(() => Promise.resolve()),
}));

import { get, post, del } from '../services/api';
import { pagosService } from '../services/pagosService';

describe('pagosService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getPagos omite filtros undefined/null/vacíos y arma el query', async () => {
    await pagosService.getPagos({
      tipo_documento: 'NOTA_VENTA',
      tipo_operacion: undefined,
      id_documento: '',
      id_empresa: 'emp-1',
    });
    const url = vi.mocked(get).mock.calls[0][0] as string;
    const qs = new URL(url, 'http://x').searchParams;
    expect(qs.get('tipo_documento')).toBe('NOTA_VENTA');
    expect(qs.get('id_empresa')).toBe('emp-1');
    expect(qs.has('tipo_operacion')).toBe(false);
    expect(qs.has('id_documento')).toBe(false);
  });

  it('getPagos sin filtros no añade query string', async () => {
    await pagosService.getPagos();
    expect(vi.mocked(get).mock.calls[0][0]).toBe('/finanzas/pagos/');
  });

  it('getPagos desempaqueta {results} y también acepta array plano', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_pago: 'p1' }] });
    expect(await pagosService.getPagos()).toEqual([{ id_pago: 'p1' }]);

    vi.mocked(get).mockResolvedValueOnce([{ id_pago: 'p2' }]);
    expect(await pagosService.getPagos()).toEqual([{ id_pago: 'p2' }]);

    vi.mocked(get).mockResolvedValueOnce({});
    expect(await pagosService.getPagos()).toEqual([]);
  });

  it('createPago usa la Idempotency-Key provista', async () => {
    await pagosService.createPago(
      { id_empresa: 'e', tipo_operacion: 'INGRESO', tipo_documento: 'NOTA_VENTA',
        id_documento: 'd', fecha_pago: '2026-01-01', monto: 10, id_moneda: 'm',
        tasa: 1, id_metodo_pago: 'mp' },
      'clave-fija',
    );
    const [, , opts] = vi.mocked(post).mock.calls[0];
    expect((opts as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe('clave-fija');
  });

  it('createPago genera una Idempotency-Key cuando no se provee', async () => {
    await pagosService.createPago({
      id_empresa: 'e', tipo_operacion: 'INGRESO', tipo_documento: 'NOTA_VENTA',
      id_documento: 'd', fecha_pago: '2026-01-01', monto: 10, id_moneda: 'm',
      tasa: 1, id_metodo_pago: 'mp',
    });
    const [, , opts] = vi.mocked(post).mock.calls[0];
    const key = (opts as { headers: Record<string, string> }).headers['Idempotency-Key'];
    expect(typeof key).toBe('string');
    expect(key.length).toBeGreaterThan(0);
  });

  it('getPagosByTipoDocumento incluye id_documento solo si se pasa', async () => {
    await pagosService.getPagosByTipoDocumento('GASTO');
    let qs = new URL(vi.mocked(get).mock.calls[0][0] as string, 'http://x').searchParams;
    expect(qs.get('tipo_documento')).toBe('GASTO');
    expect(qs.has('id_documento')).toBe(false);

    await pagosService.getPagosByTipoDocumento('GASTO', 'g-9');
    qs = new URL(vi.mocked(get).mock.calls[1][0] as string, 'http://x').searchParams;
    expect(qs.get('id_documento')).toBe('g-9');
  });

  it('getPagosNotaVenta delega con el tipo correcto', async () => {
    await pagosService.getPagosNotaVenta('nv-1');
    const qs = new URL(vi.mocked(get).mock.calls[0][0] as string, 'http://x').searchParams;
    expect(qs.get('tipo_documento')).toBe('NOTA_VENTA');
    expect(qs.get('id_documento')).toBe('nv-1');
  });

  it('deletePago pega al endpoint del recurso', async () => {
    await pagosService.deletePago('p-x');
    expect(vi.mocked(del).mock.calls[0][0]).toBe('/finanzas/pagos/p-x/');
  });
});
