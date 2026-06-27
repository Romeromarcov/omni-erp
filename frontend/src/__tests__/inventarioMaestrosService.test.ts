import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  variantesProductoService,
  conversionesUnidadService,
  stockConsignacionClienteService,
  stockConsignacionProveedorService,
  type VarianteProductoPayload,
  type ConversionUnidadPayload,
  type StockConsignacionClientePayload,
  type StockConsignacionProveedorPayload,
} from '../services/inventarioMaestrosService';

const variantePayload: VarianteProductoPayload = {
  id_producto: 'p1',
  codigo_variante: 'V-AZUL',
  sku: 'SKU-1',
  atributos_json: { color: 'azul' },
};

const conversionPayload: ConversionUnidadPayload = {
  id_empresa: 'e1',
  id_producto: 'p1',
  id_unidad_origen: 'u1',
  id_unidad_destino: 'u2',
  factor_conversion: '12.00000000',
};

const consClientePayload: StockConsignacionClientePayload = {
  id_empresa: 'e1',
  id_cliente: 'c1',
  id_producto: 'p1',
  id_variante: null,
  cantidad_consignada: '10.0000',
  cantidad_vendida: '0.0000',
  cantidad_devuelta: '0.0000',
  fecha_consignacion: '2026-06-27',
  fecha_vencimiento: null,
  precio_unitario_consignacion: '5.0000',
  id_moneda: 'm1',
  estado: 'ACTIVA',
};

const consProvPayload: StockConsignacionProveedorPayload = {
  id_empresa: 'e1',
  id_proveedor: 'pr1',
  id_producto: 'p1',
  id_variante: null,
  cantidad_recibida: '20.0000',
  cantidad_consumida: '0.0000',
  cantidad_devuelta: '0.0000',
  fecha_recepcion: '2026-06-27',
  fecha_vencimiento: null,
  costo_unitario_consignacion: '3.0000',
  id_moneda: 'm1',
  estado: 'ACTIVA',
};

describe('variantesProductoService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la rama paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_variante: 'v1', id_producto: 'p1' }] });
    const r = await variantesProductoService.getAll();
    expect(get).toHaveBeenCalledWith('/inventario/variantes-producto/');
    expect(r).toEqual([{ id_variante: 'v1', id_producto: 'p1' }]);
  });

  it('getAll normaliza la rama array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_variante: 'v1', id_producto: 'p1' }]);
    expect(await variantesProductoService.getAll()).toHaveLength(1);
  });

  it('getAll normaliza respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await variantesProductoService.getAll()).toEqual([]);
  });

  it('getAll filtra por producto en el cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_variante: 'v1', id_producto: 'p1' },
      { id_variante: 'v2', id_producto: 'otro' },
    ]);
    const r = await variantesProductoService.getAll({ producto: 'p1' });
    expect(r.map((v) => v.id_variante)).toEqual(['v1']);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_variante: 'v2' });
    await variantesProductoService.create(variantePayload);
    expect(post).toHaveBeenCalledWith('/inventario/variantes-producto/', variantePayload);

    vi.mocked(patch).mockResolvedValue({ id_variante: 'v1' });
    await variantesProductoService.update('v1', variantePayload);
    expect(patch).toHaveBeenCalledWith('/inventario/variantes-producto/v1/', variantePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await variantesProductoService.remove('v1');
    expect(del).toHaveBeenCalledWith('/inventario/variantes-producto/v1/');
  });
});

describe('conversionesUnidadService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza la rama paginada y filtra por producto', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_conversion: 'co1', id_producto: 'p1' },
        { id_conversion: 'co2', id_producto: 'otro' },
      ],
    });
    const r = await conversionesUnidadService.getAll({ producto: 'p1' });
    expect(get).toHaveBeenCalledWith('/inventario/conversiones-unidad-medida/');
    expect(r.map((c) => c.id_conversion)).toEqual(['co1']);
  });

  it('getAll sin filtro normaliza array', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_conversion: 'co1', id_producto: 'p1' }]);
    expect(await conversionesUnidadService.getAll()).toHaveLength(1);
  });

  it('getAll normaliza respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await conversionesUnidadService.getAll()).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_conversion: 'co2' });
    await conversionesUnidadService.create(conversionPayload);
    expect(post).toHaveBeenCalledWith('/inventario/conversiones-unidad-medida/', conversionPayload);

    vi.mocked(patch).mockResolvedValue({ id_conversion: 'co1' });
    await conversionesUnidadService.update('co1', conversionPayload);
    expect(patch).toHaveBeenCalledWith('/inventario/conversiones-unidad-medida/co1/', conversionPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await conversionesUnidadService.remove('co1');
    expect(del).toHaveBeenCalledWith('/inventario/conversiones-unidad-medida/co1/');
  });
});

describe('stockConsignacionClienteService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza array y filtra por cliente y estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_stock_consignacion: 's1', id_cliente: 'c1', estado: 'ACTIVA' },
      { id_stock_consignacion: 's2', id_cliente: 'c1', estado: 'CERRADA' },
      { id_stock_consignacion: 's3', id_cliente: 'otro', estado: 'ACTIVA' },
    ]);
    const r = await stockConsignacionClienteService.getAll({ cliente: 'c1', estado: 'ACTIVA' });
    expect(get).toHaveBeenCalledWith('/inventario/stock-consignacion-cliente/');
    expect(r.map((s) => s.id_stock_consignacion)).toEqual(['s1']);
  });

  it('getAll sin filtros normaliza la rama paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_stock_consignacion: 's1' }] });
    expect(await stockConsignacionClienteService.getAll()).toHaveLength(1);
  });

  it('getAll normaliza respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await stockConsignacionClienteService.getAll()).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_stock_consignacion: 's2' });
    await stockConsignacionClienteService.create(consClientePayload);
    expect(post).toHaveBeenCalledWith('/inventario/stock-consignacion-cliente/', consClientePayload);

    vi.mocked(patch).mockResolvedValue({ id_stock_consignacion: 's1' });
    await stockConsignacionClienteService.update('s1', consClientePayload);
    expect(patch).toHaveBeenCalledWith('/inventario/stock-consignacion-cliente/s1/', consClientePayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await stockConsignacionClienteService.remove('s1');
    expect(del).toHaveBeenCalledWith('/inventario/stock-consignacion-cliente/s1/');
  });
});

describe('stockConsignacionProveedorService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll normaliza array y filtra por proveedor y estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_stock_consignacion: 's1', id_proveedor: 'pr1', estado: 'ACTIVA' },
      { id_stock_consignacion: 's2', id_proveedor: 'pr1', estado: 'VENCIDA' },
      { id_stock_consignacion: 's3', id_proveedor: 'otro', estado: 'ACTIVA' },
    ]);
    const r = await stockConsignacionProveedorService.getAll({ proveedor: 'pr1', estado: 'ACTIVA' });
    expect(get).toHaveBeenCalledWith('/inventario/stock-consignacion-proveedor/');
    expect(r.map((s) => s.id_stock_consignacion)).toEqual(['s1']);
  });

  it('getAll sin filtros normaliza la rama paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_stock_consignacion: 's1' }] });
    expect(await stockConsignacionProveedorService.getAll()).toHaveLength(1);
  });

  it('getAll normaliza respuesta vacía', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as []);
    expect(await stockConsignacionProveedorService.getAll()).toEqual([]);
  });

  it('create / update / remove pegan a sus endpoints', async () => {
    vi.mocked(post).mockResolvedValue({ id_stock_consignacion: 's2' });
    await stockConsignacionProveedorService.create(consProvPayload);
    expect(post).toHaveBeenCalledWith('/inventario/stock-consignacion-proveedor/', consProvPayload);

    vi.mocked(patch).mockResolvedValue({ id_stock_consignacion: 's1' });
    await stockConsignacionProveedorService.update('s1', consProvPayload);
    expect(patch).toHaveBeenCalledWith('/inventario/stock-consignacion-proveedor/s1/', consProvPayload);

    vi.mocked(del).mockResolvedValue(undefined);
    await stockConsignacionProveedorService.remove('s1');
    expect(del).toHaveBeenCalledWith('/inventario/stock-consignacion-proveedor/s1/');
  });
});
