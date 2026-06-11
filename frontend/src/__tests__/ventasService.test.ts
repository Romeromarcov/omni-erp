import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetcher: vi.fn(),
}));

import { get, post, patch, fetcher } from '../services/api';
import {
  cotizacionService,
  pedidoService,
  notaVentaService,
  facturaFiscalService,
  notaCreditoVentaService,
  notaCreditoFiscalService,
  devolucionVentaService,
} from '../services/ventas';

const mockGet = get as unknown as ReturnType<typeof vi.fn>;
const mockPost = post as unknown as ReturnType<typeof vi.fn>;
const mockPatch = patch as unknown as ReturnType<typeof vi.fn>;
const mockFetcher = fetcher as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockFetcher.mockReset();
});

describe('BaseVentasService (vía cotizacionService)', () => {
  it('getAll desempaqueta respuesta paginada a lista', async () => {
    mockGet.mockResolvedValueOnce({ count: 1, next: null, previous: null, results: [{ id: 'c1' }] });
    const res = await cotizacionService.getAll();

    expect(mockGet).toHaveBeenCalledWith('/ventas/cotizaciones/');
    expect(res).toEqual([{ id: 'c1' }]);
  });

  it('getAll acepta respuesta como array plano', async () => {
    mockGet.mockResolvedValueOnce([{ id: 'c1' }, { id: 'c2' }]);
    const res = await cotizacionService.getAll();
    expect(res).toHaveLength(2);
  });

  it('getAllPaginated pasa page y page_size y devuelve la página tal cual', async () => {
    const page = { count: 40, next: 'x', previous: null, results: [{ id: 'c1' }] };
    mockGet.mockResolvedValueOnce(page);
    const res = await cotizacionService.getAllPaginated(2, 10);

    expect(mockGet).toHaveBeenCalledWith('/ventas/cotizaciones/?page=2&page_size=10');
    expect(res).toEqual(page);
  });

  it('getAllPaginated normaliza una respuesta no paginada (array) a página sintética', async () => {
    mockGet.mockResolvedValueOnce([{ id: 'c1' }]);
    const res = await cotizacionService.getAllPaginated();

    expect(mockGet).toHaveBeenCalledWith('/ventas/cotizaciones/?page=1&page_size=20');
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [{ id: 'c1' }] });
  });

  it('getAllPaginated normaliza una respuesta inválida a página vacía', async () => {
    mockGet.mockResolvedValueOnce(null);
    const res = await cotizacionService.getAllPaginated();
    expect(res).toEqual({ count: 0, next: null, previous: null, results: [] });
  });

  it('getById, create, update y delete usan los verbos y URLs correctos', async () => {
    mockGet.mockResolvedValueOnce({ id: 'c1' });
    await cotizacionService.getById('c1');
    expect(mockGet).toHaveBeenCalledWith('/ventas/cotizaciones/c1/');

    mockPost.mockResolvedValueOnce({ id: 'c2' });
    await cotizacionService.create({ observaciones: 'x' });
    expect(mockPost).toHaveBeenCalledWith('/ventas/cotizaciones/', { observaciones: 'x' });

    mockPatch.mockResolvedValueOnce({ id: 'c1' });
    await cotizacionService.update('c1', { observaciones: 'y' });
    expect(mockPatch).toHaveBeenCalledWith('/ventas/cotizaciones/c1/', { observaciones: 'y' });

    mockFetcher.mockResolvedValueOnce(undefined);
    await cotizacionService.delete('c1');
    expect(mockFetcher).toHaveBeenCalledWith('/ventas/cotizaciones/c1/', { method: 'DELETE' });
  });
});

describe('acciones específicas de cada documento de venta', () => {
  it('cotización: convertirAPedido y getByCliente', async () => {
    mockPost.mockResolvedValueOnce({ id: 'p1' });
    await cotizacionService.convertirAPedido('c1', { id_sucursal: 's1' });
    expect(mockPost).toHaveBeenCalledWith('/ventas/cotizaciones/c1/convertir-pedido/', { id_sucursal: 's1' });

    mockGet.mockResolvedValueOnce([]);
    await cotizacionService.getByCliente('cli-1');
    expect(mockGet).toHaveBeenCalledWith('/ventas/cotizaciones/?id_cliente=cli-1');
  });

  it('pedido: convertirANotaVenta, getByCliente y agregarPago con el payload de dinero intacto', async () => {
    mockPost.mockResolvedValueOnce({ id: 'nv1' });
    await pedidoService.convertirANotaVenta('p1', {});
    expect(mockPost).toHaveBeenCalledWith('/ventas/pedidos/p1/convertir-nota-venta/', {});

    mockGet.mockResolvedValueOnce([]);
    await pedidoService.getByCliente('cli-1');
    expect(mockGet).toHaveBeenCalledWith('/ventas/pedidos/?id_cliente=cli-1');

    const pago = { metodo: 'efectivo', moneda: 'USD', monto: 12.5, tasa: 36.5, referencia: 'r-1' };
    mockPost.mockResolvedValueOnce({ id: 'p1' });
    await pedidoService.agregarPago('p1', pago);
    expect(mockPost).toHaveBeenCalledWith('/ventas/pedidos/p1/agregar-pago/', pago);
  });

  it('nota de venta: convertirAFactura y getByCliente', async () => {
    mockPost.mockResolvedValueOnce({ id: 'f1' });
    await notaVentaService.convertirAFactura('nv1', { serie: 'A' });
    expect(mockPost).toHaveBeenCalledWith('/ventas/notas-venta/nv1/convertir-factura/', { serie: 'A' });

    mockGet.mockResolvedValueOnce([]);
    await notaVentaService.getByCliente('cli-1');
    expect(mockGet).toHaveBeenCalledWith('/ventas/notas-venta/?id_cliente=cli-1');
  });

  it('factura fiscal: generarNotaCredito fusiona motivo con data extra', async () => {
    mockPost.mockResolvedValueOnce({ id: 'nc1' });
    await facturaFiscalService.generarNotaCredito('f1', 'devolución parcial', { monto: '10.00' });
    expect(mockPost).toHaveBeenCalledWith('/ventas/facturas-fiscales/f1/generar-nota-credito/', {
      motivo: 'devolución parcial',
      monto: '10.00',
    });

    mockGet.mockResolvedValueOnce([]);
    await facturaFiscalService.getByCliente('cli-1');
    expect(mockGet).toHaveBeenCalledWith('/ventas/facturas-fiscales/?id_cliente=cli-1');
  });

  it('notas de crédito (venta y fiscal): aplicar', async () => {
    mockPost.mockResolvedValue({ id: 'nc' });
    await notaCreditoVentaService.aplicar('ncv1');
    expect(mockPost).toHaveBeenCalledWith('/ventas/notas-credito-venta/ncv1/aplicar/', {});

    await notaCreditoFiscalService.aplicar('ncf1');
    expect(mockPost).toHaveBeenCalledWith('/ventas/notas-credito-fiscal/ncf1/aplicar/', {});
  });

  it('devolución de venta: procesar y generarNotaCredito', async () => {
    mockPost.mockResolvedValue({ id: 'dv1' });
    await devolucionVentaService.procesar('dv1');
    expect(mockPost).toHaveBeenCalledWith('/ventas/devoluciones-venta/dv1/procesar/', {});

    await devolucionVentaService.generarNotaCredito('dv1');
    expect(mockPost).toHaveBeenCalledWith('/ventas/devoluciones-venta/dv1/generar-nota-credito/', {});
  });

  it('propaga errores HTTP sin transformarlos', async () => {
    mockPost.mockRejectedValueOnce(new Error('HTTP 400'));
    await expect(pedidoService.agregarPago('p1', { metodo: 'x', moneda: 'USD', monto: 1, tasa: 1 }))
      .rejects.toThrow('HTTP 400');
  });
});
