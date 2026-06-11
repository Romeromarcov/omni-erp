import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get } from '../services/api';
import { productoInventarioService, stockActualService } from '../services/inventarioService';

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
});
