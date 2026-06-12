import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../services/api';
import { comprasService } from '../services/comprasService';

const orden = {
  id_orden_compra: 'oc-1',
  id_empresa: 'emp-1',
  id_proveedor: 'prov-1',
  tipo_operacion: null,
  fecha_cierre_estimada: null,
  numero_orden: 'OC-0001',
  fecha_orden: '2026-06-10',
  estado: 'BORRADOR',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-10T12:00:00Z',
};

const detalle = {
  id_detalle_orden_compra: 'det-1',
  id_orden_compra: 'oc-1',
  id_producto: 'prod-1',
  cantidad: '10.0000',
  precio_unitario: '25.5000',
  subtotal: '255.0000',
  observaciones: null,
};

describe('comprasService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getOrdenesPaginated pasa page/page_size y devuelve la página DRF', async () => {
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [orden] });
    const res = await comprasService.getOrdenesPaginated(2, 10);
    expect(get).toHaveBeenCalledWith('/compras/ordenes-compra/?page=2&page_size=10');
    expect(res.count).toBe(1);
    expect(res.results[0].numero_orden).toBe('OC-0001');
  });

  it('getOrdenesPaginated normaliza listas directas', async () => {
    vi.mocked(get).mockResolvedValue([orden]);
    const res = await comprasService.getOrdenesPaginated();
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [orden] });
  });

  it('getOrden consulta el detalle por id', async () => {
    vi.mocked(get).mockResolvedValue(orden);
    const res = await comprasService.getOrden('oc-1');
    expect(get).toHaveBeenCalledWith('/compras/ordenes-compra/oc-1/');
    expect(res.estado).toBe('BORRADOR');
  });

  it('getDetallesOrden recorre las páginas y filtra por la OC', async () => {
    const otro = { ...detalle, id_detalle_orden_compra: 'det-2', id_orden_compra: 'oc-OTRA' };
    vi.mocked(get)
      .mockResolvedValueOnce({ count: 3, next: 'pag2', previous: null, results: [detalle, otro] })
      .mockResolvedValueOnce({
        count: 3,
        next: null,
        previous: null,
        results: [{ ...detalle, id_detalle_orden_compra: 'det-3' }],
      });
    const res = await comprasService.getDetallesOrden('oc-1');
    expect(get).toHaveBeenNthCalledWith(1, '/compras/detalles-orden-compra/?page=1');
    expect(get).toHaveBeenNthCalledWith(2, '/compras/detalles-orden-compra/?page=2');
    expect(res.map((d) => d.id_detalle_orden_compra)).toEqual(['det-1', 'det-3']);
  });

  it('getRecepcionesOrden filtra por la OC y corta cuando no hay next', async () => {
    const recepcion = {
      id_recepcion: 'rec-1',
      id_empresa: 'emp-1',
      id_orden_compra: 'oc-1',
      fecha_recepcion: '2026-06-11',
      monto_total: '255.0000',
      observaciones: null,
      activo: true,
      fecha_creacion: '2026-06-11T10:00:00Z',
    };
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [recepcion] });
    const res = await comprasService.getRecepcionesOrden('oc-1');
    expect(get).toHaveBeenCalledTimes(1);
    expect(res).toHaveLength(1);
    expect(res[0].monto_total).toBe('255.0000');
  });

  it('crearOrden y crearDetalle postean los payloads con strings decimales', async () => {
    vi.mocked(post).mockResolvedValueOnce(orden).mockResolvedValueOnce(detalle);
    await comprasService.crearOrden({
      id_proveedor: 'prov-1',
      numero_orden: 'OC-0001',
      fecha_orden: '2026-06-10',
      observaciones: '',
    });
    await comprasService.crearDetalle({
      id_orden_compra: 'oc-1',
      id_producto: 'prod-1',
      cantidad: '10',
      precio_unitario: '25.50',
      subtotal: '255.0000',
    });
    expect(post).toHaveBeenNthCalledWith(1, '/compras/ordenes-compra/', {
      id_proveedor: 'prov-1',
      numero_orden: 'OC-0001',
      fecha_orden: '2026-06-10',
      observaciones: '',
    });
    expect(post).toHaveBeenNthCalledWith(2, '/compras/detalles-orden-compra/', {
      id_orden_compra: 'oc-1',
      id_producto: 'prod-1',
      cantidad: '10',
      precio_unitario: '25.50',
      subtotal: '255.0000',
    });
  });

  it('aprobarOrden postea a la acción aprobar', async () => {
    vi.mocked(post).mockResolvedValue({ detail: 'Orden aprobada.', estado: 'APROBADA' });
    const res = await comprasService.aprobarOrden('oc-1');
    expect(post).toHaveBeenCalledWith('/compras/ordenes-compra/oc-1/aprobar/', {});
    expect(res.estado).toBe('APROBADA');
  });

  it('recepcionar postea orden, almacén e items', async () => {
    vi.mocked(post).mockResolvedValue({
      recepcion_id: 'rec-1',
      movimientos: 1,
      cxp_id: 'cxp-1',
      monto_total: '255.0000',
    });
    const res = await comprasService.recepcionar({
      orden_compra_id: 'oc-1',
      almacen_id: 'alm-1',
      items: [{ producto_id: 'prod-1', cantidad: '10', costo_unitario: '25.50' }],
    });
    expect(post).toHaveBeenCalledWith('/compras/recepciones-mercancia/recepcionar/', {
      orden_compra_id: 'oc-1',
      almacen_id: 'alm-1',
      items: [{ producto_id: 'prod-1', cantidad: '10', costo_unitario: '25.50' }],
    });
    expect(res.cxp_id).toBe('cxp-1');
  });

  it('facturar postea recepción y número de factura', async () => {
    vi.mocked(post).mockResolvedValue({
      factura_id: 'fac-1',
      numero_factura: 'FAC-001',
      monto_total: '255.0000',
    });
    const res = await comprasService.facturar({
      recepcion_id: 'rec-1',
      numero_factura: 'FAC-001',
      fecha_emision: '2026-06-11',
    });
    expect(post).toHaveBeenCalledWith('/compras/facturas-compra/facturar/', {
      recepcion_id: 'rec-1',
      numero_factura: 'FAC-001',
      fecha_emision: '2026-06-11',
    });
    expect(res.numero_factura).toBe('FAC-001');
  });

  it('getProveedores normaliza la respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{ id_proveedor: 'prov-1', razon_social: 'ACME C.A.' }],
    });
    const res = await comprasService.getProveedores();
    expect(res).toEqual([{ id_proveedor: 'prov-1', razon_social: 'ACME C.A.' }]);
  });
});
