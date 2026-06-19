/**
 * Cobertura del servicio de pagos (Q1: cobertura frontend, ruta de dinero).
 * Verifica query params, unwrapping de respuesta, cabecera de idempotencia,
 * delegación por tipo de documento y la orquestación de createPagoDocumento.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(() => Promise.resolve({ results: [] })),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
  del: vi.fn(() => Promise.resolve()),
}));

import { get, post, put, del } from '../services/api';
import { pagosService } from '../services/pagosService';

const basePago = {
  id_empresa: 'e', tipo_operacion: 'INGRESO' as const, tipo_documento: 'NOTA_VENTA',
  id_documento: 'd', fecha_pago: '2026-01-01', monto: 10, id_moneda: 'm',
  tasa: 1, id_metodo_pago: 'mp',
};

describe('pagosService — consultas', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getPagos omite filtros undefined/null/vacíos y arma el query', async () => {
    await pagosService.getPagos({
      tipo_documento: 'NOTA_VENTA', tipo_operacion: undefined,
      id_documento: '', id_empresa: 'emp-1',
    });
    const qs = new URL(vi.mocked(get).mock.calls[0][0] as string, 'http://x').searchParams;
    expect(qs.get('tipo_documento')).toBe('NOTA_VENTA');
    expect(qs.get('id_empresa')).toBe('emp-1');
    expect(qs.has('tipo_operacion')).toBe(false);
    expect(qs.has('id_documento')).toBe(false);
  });

  it('getPagos sin filtros no añade query string', async () => {
    await pagosService.getPagos();
    expect(vi.mocked(get).mock.calls[0][0]).toBe('/finanzas/pagos/');
  });

  it('getPagos desempaqueta {results} / array / vacío', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_pago: 'p1' }] });
    expect(await pagosService.getPagos()).toEqual([{ id_pago: 'p1' }]);
    vi.mocked(get).mockResolvedValueOnce([{ id_pago: 'p2' }]);
    expect(await pagosService.getPagos()).toEqual([{ id_pago: 'p2' }]);
    vi.mocked(get).mockResolvedValueOnce({});
    expect(await pagosService.getPagos()).toEqual([]);
  });

  it('getPago / getPagosCXP / getPagosGasto / getPagosPedido pegan al endpoint', async () => {
    await pagosService.getPago('p-1');
    expect(vi.mocked(get).mock.calls[0][0]).toBe('/finanzas/pagos/p-1/');
    await pagosService.getPagosCXP('cxp-1');
    expect(vi.mocked(get).mock.calls[1][0]).toContain('tipo_documento=CXP');
    await pagosService.getPagosGasto('g-1');
    expect(vi.mocked(get).mock.calls[2][0]).toContain('tipo_documento=GASTO');
    await pagosService.getPagosPedido('pe-1');
    expect(vi.mocked(get).mock.calls[3][0]).toContain('tipo_documento=PEDIDO');
  });

  it('getPagosByTipoDocumento incluye id_documento solo si se pasa', async () => {
    await pagosService.getPagosByTipoDocumento('GASTO');
    let qs = new URL(vi.mocked(get).mock.calls[0][0] as string, 'http://x').searchParams;
    expect(qs.has('id_documento')).toBe(false);
    await pagosService.getPagosByTipoDocumento('GASTO', 'g-9');
    qs = new URL(vi.mocked(get).mock.calls[1][0] as string, 'http://x').searchParams;
    expect(qs.get('id_documento')).toBe('g-9');
  });
});

describe('pagosService — mutaciones', () => {
  beforeEach(() => vi.clearAllMocks());

  it('createPago usa la Idempotency-Key provista', async () => {
    await pagosService.createPago(basePago, 'clave-fija');
    const [, , opts] = vi.mocked(post).mock.calls[0];
    expect((opts as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe('clave-fija');
  });

  it('createPago genera una Idempotency-Key cuando no se provee', async () => {
    await pagosService.createPago(basePago);
    const [, , opts] = vi.mocked(post).mock.calls[0];
    const key = (opts as { headers: Record<string, string> }).headers['Idempotency-Key'];
    expect(typeof key).toBe('string');
    expect(key.length).toBeGreaterThan(0);
  });

  it('updatePago y deletePago pegan al endpoint del recurso', async () => {
    await pagosService.updatePago('p-x', { monto: 5 });
    expect(vi.mocked(put).mock.calls[0][0]).toBe('/finanzas/pagos/p-x/');
    await pagosService.deletePago('p-x');
    expect(vi.mocked(del).mock.calls[0][0]).toBe('/finanzas/pagos/p-x/');
  });

  it('procesarVueltos es un stub que resuelve', async () => {
    await expect(pagosService.procesarVueltos([])).resolves.toBeUndefined();
  });

  it('conciliarNotasCredito marca cada nota como UTILIZADA', async () => {
    await pagosService.conciliarNotasCredito(
      [{ id_nota_credito: 'nc-1' }, { id_nota_credito: 'nc-2' }] as never,
      'doc-1', 'NOTA_VENTA',
    );
    expect(vi.mocked(put)).toHaveBeenCalledTimes(2);
    const [url, body] = vi.mocked(put).mock.calls[0];
    expect(url).toBe('/finanzas/notas-credito/nc-1/');
    expect((body as { estado: string }).estado).toBe('UTILIZADA');
  });
});

describe('pagosService — helpers puros', () => {
  it('getTipoOperacionPorDocumento clasifica ingreso/egreso/desconocido', () => {
    expect(pagosService.getTipoOperacionPorDocumento('NOTA_VENTA')).toBe('INGRESO');
    expect(pagosService.getTipoOperacionPorDocumento('CXP')).toBe('EGRESO');
    expect(pagosService.getTipoOperacionPorDocumento('DESCONOCIDO')).toBe('EGRESO');
  });

  it('getDocumentoField mapea el campo específico por tipo', () => {
    expect(pagosService.getDocumentoField('PEDIDO', 'x')).toEqual({ id_pedido: 'x' });
    expect(pagosService.getDocumentoField('NOTA_VENTA', 'x')).toEqual({ id_nota_venta: 'x' });
    expect(pagosService.getDocumentoField('CXP', 'x')).toEqual({ id_cxp: 'x' });
    expect(pagosService.getDocumentoField('GASTO', 'x')).toEqual({ id_gasto: 'x' });
    expect(pagosService.getDocumentoField('NOMINA', 'x')).toEqual({ id_nomina: 'x' });
    expect(pagosService.getDocumentoField('IMPUESTO', 'x')).toEqual({ id_contribucion: 'x' });
    expect(pagosService.getDocumentoField('COTIZACION', 'x')).toEqual({});
    expect(pagosService.getDocumentoField('OTRO', 'x')).toEqual({});
  });
});

describe('pagosService — info de documento/método/moneda', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getDocumentoInfo resuelve el endpoint por tipo y devuelve id_empresa', async () => {
    vi.mocked(get).mockResolvedValue({ id_empresa: 'emp-9' });
    expect(await pagosService.getDocumentoInfo('NOTA_VENTA', 'n1')).toEqual({ id_empresa: 'emp-9' });
    expect(vi.mocked(get).mock.calls[0][0]).toBe('/ventas/notas-venta/n1/');
    await pagosService.getDocumentoInfo('CXP', 'c1');
    expect(vi.mocked(get).mock.calls[1][0]).toBe('/cuentas-por-pagar/cxp/c1/');
  });

  it('getDocumentoInfo resuelve el endpoint de cada tipo soportado', async () => {
    vi.mocked(get).mockResolvedValue({ id_empresa: 'e' });
    const casos: Array<[string, string]> = [
      ['PEDIDO', '/ventas/pedidos/x/'],
      ['FACTURA', '/ventas/facturas/x/'],
      ['FACTURA_FISCAL', '/ventas/facturas-fiscales/x/'],
      ['COTIZACION', '/ventas/cotizaciones/x/'],
      ['GASTO', '/gastos/gastos/x/'],
      ['REEMBOLSO_GASTO', '/gastos/reembolsos/x/'],
      ['NOMINA', '/nomina/nominas/x/'],
      ['IMPUESTO', '/fiscal/contribuciones/x/'],
    ];
    for (const [tipo, endpoint] of casos) {
      vi.mocked(get).mockClear();
      await pagosService.getDocumentoInfo(tipo, 'x');
      expect(vi.mocked(get).mock.calls[0][0]).toBe(endpoint);
    }
  });

  it('getDocumentoField cubre FACTURA / FACTURA_FISCAL / REEMBOLSO_GASTO', () => {
    expect(pagosService.getDocumentoField('FACTURA', 'x')).toEqual({ id_factura: 'x' });
    expect(pagosService.getDocumentoField('FACTURA_FISCAL', 'x')).toEqual({ id_factura: 'x' });
    expect(pagosService.getDocumentoField('REEMBOLSO_GASTO', 'x')).toEqual({ id_reembolso_gasto: 'x' });
  });

  it('getDocumentoInfo lanza para tipo no soportado', async () => {
    await expect(pagosService.getDocumentoInfo('RARO', 'x')).rejects.toThrow(/no soportado/);
  });

  it('getMetodoPagoInfo cae al ID si la llamada falla', async () => {
    vi.mocked(get).mockResolvedValueOnce({ nombre_metodo: 'Efectivo' });
    expect(await pagosService.getMetodoPagoInfo('mp-1')).toEqual({ nombre_metodo: 'Efectivo' });
    vi.mocked(get).mockRejectedValueOnce(new Error('404'));
    expect(await pagosService.getMetodoPagoInfo('mp-2')).toEqual({ nombre_metodo: 'mp-2' });
  });

  it('getMonedaInfo cae al ID si la llamada falla', async () => {
    vi.mocked(get).mockResolvedValueOnce({ codigo_iso: 'USD' });
    expect(await pagosService.getMonedaInfo('m-1')).toEqual({ codigo_iso: 'USD' });
    vi.mocked(get).mockRejectedValueOnce(new Error('404'));
    expect(await pagosService.getMonedaInfo('m-2')).toEqual({ codigo_iso: 'm-2' });
  });

  it('createPagoDocumento orquesta info + crea el pago con la operación correcta', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/ventas/notas-venta/')) return Promise.resolve({ id_empresa: 'emp-1' });
      if (url.startsWith('/finanzas/metodos-pago/')) return Promise.resolve({ nombre_metodo: 'Efectivo' });
      if (url.startsWith('/finanzas/monedas/')) return Promise.resolve({ codigo_iso: 'USD' });
      return Promise.resolve({});
    });
    vi.mocked(post).mockResolvedValueOnce({ id_pago: 'srv-1' });

    const res = await pagosService.createPagoDocumento('NOTA_VENTA', 'nv-1', {
      monto: 50, id_metodo_pago: 'mp', id_moneda: 'm', tasa: 1,
    }, 'clave-x');

    expect(res).toEqual({ id_pago: 'srv-1' });
    const [endpoint, body, opts] = vi.mocked(post).mock.calls[0];
    expect(endpoint).toBe('/finanzas/pagos/');
    const pago = body as Record<string, unknown>;
    expect(pago.tipo_operacion).toBe('INGRESO');
    expect(pago.id_empresa).toBe('emp-1');
    expect(pago.id_nota_venta).toBe('nv-1');
    expect(pago.metodo).toBe('Efectivo');
    expect(pago.moneda).toBe('USD');
    expect((opts as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe('clave-x');
  });
});
