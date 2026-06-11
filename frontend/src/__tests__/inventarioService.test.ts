import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import {
  movimientoService,
  productoInventarioService,
  stockActualService,
} from '../services/inventarioService';

describe('productoInventarioService.getKardex', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normaliza la respuesta {kardex: [...]} del backend a MovimientoInventario', async () => {
    // Gap E2E (PR #76): el backend devuelve {kardex: [...]} con nombres propios;
    // antes el servicio esperaba lista/results y siempre devolvía [].
    vi.mocked(get).mockResolvedValue({
      producto_id: 'prod-001',
      producto_nombre: 'Producto A',
      almacen_id: null,
      saldo_final: '35',
      kardex: [
        {
          id_movimiento: 'mov-001',
          fecha_hora: '2026-05-01T08:00:00Z',
          tipo_movimiento: 'ENTRADA',
          cantidad: '50.0000',
          delta: '0',
          almacen_origen: null,
          almacen_destino: 'Almacén Principal',
          costo_unitario: '10.00',
          saldo_anterior: '0',
          saldo_posterior: '50',
          observaciones: 'Compra inicial',
        },
      ],
    });

    const movimientos = await productoInventarioService.getKardex('prod-001', {
      fecha_desde: '2026-01-01',
      fecha_hasta: '2026-06-01',
    });

    expect(get).toHaveBeenCalledWith(
      '/inventario/productos/prod-001/kardex/?fecha_desde=2026-01-01&fecha_hasta=2026-06-01'
    );
    expect(movimientos).toHaveLength(1);
    expect(movimientos[0]).toMatchObject({
      id_movimiento_inventario: 'mov-001',
      fecha_hora_movimiento: '2026-05-01T08:00:00Z',
      tipo_movimiento: 'ENTRADA',
      cantidad: '50.0000',
      costo_unitario_movimiento: '10.00',
      almacen_origen_nombre: null,
      almacen_destino_nombre: 'Almacén Principal',
      observaciones: 'Compra inicial',
      producto_nombre: 'Producto A',
    });
  });

  it('sigue aceptando una lista paginada {results: [...]} (fallback)', async () => {
    const mov = {
      id_movimiento_inventario: 'mov-002',
      tipo_movimiento: 'SALIDA',
      cantidad: '5',
    };
    vi.mocked(get).mockResolvedValue({ results: [mov], count: 1 });
    const movimientos = await productoInventarioService.getKardex('prod-001');
    expect(movimientos).toEqual([mov]);
  });

  it('devuelve [] ante respuestas inesperadas', async () => {
    vi.mocked(get).mockResolvedValue(null);
    expect(await productoInventarioService.getKardex('prod-001')).toEqual([]);
  });
});

describe('stockActualService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('arma el querystring de filtros', async () => {
    vi.mocked(get).mockResolvedValue([]);
    await stockActualService.getAll({ empresa: 'e1', producto: 'p1' });
    expect(get).toHaveBeenCalledWith('/inventario/stock-actual/?empresa=e1&producto=p1');
  });

  it('getBajoMinimo filtra stock por debajo del mínimo', async () => {
    vi.mocked(get).mockResolvedValue([
      { id_stock_actual: 's1', cantidad_disponible: '2', cantidad_minima: '5' },
      { id_stock_actual: 's2', cantidad_disponible: '10', cantidad_minima: '5' },
      { id_stock_actual: 's3', cantidad_disponible: '0', cantidad_minima: '0' },
    ]);
    const bajos = await stockActualService.getBajoMinimo('e1');
    expect(bajos.map((s) => s.id_stock_actual)).toEqual(['s1']);
  });
});

describe('productoInventarioService CRUD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getAll y getById usan los endpoints de productos', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_producto: 'p1' }] });
    expect(await productoInventarioService.getAll({ empresa: 'e1' })).toEqual([{ id_producto: 'p1' }]);
    expect(get).toHaveBeenCalledWith('/inventario/productos/?empresa=e1');

    vi.mocked(get).mockResolvedValueOnce({ id_producto: 'p1' });
    await productoInventarioService.getById('p1');
    expect(get).toHaveBeenCalledWith('/inventario/productos/p1/');
  });
});

describe('movimientoService', () => {
  it('registrarAjuste postea el movimiento AJUSTE', async () => {
    vi.mocked(post).mockResolvedValue({ id_movimiento_inventario: 'm1' });
    const payload = {
      id_empresa: 'e1',
      id_producto: 'p1',
      tipo_movimiento: 'AJUSTE' as const,
      cantidad: 5,
      fecha_hora_movimiento: '2026-06-01T00:00:00Z',
      id_almacen_destino: 'a1',
    };
    await movimientoService.registrarAjuste(payload);
    expect(post).toHaveBeenCalledWith('/inventario/movimientos-inventario/', payload);
  });
});
