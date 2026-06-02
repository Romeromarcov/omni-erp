import { describe, it, expect } from 'vitest';
import {
  inventarioKeys,
  notasVentaKeys,
  pagosKeys,
  productosKeys,
} from '../lib/queryKeys';

describe('queryKeys factory', () => {
  it('inventario keys son estables y tipadas', () => {
    expect(inventarioKeys.stockActualAll()).toEqual(['stock-actual-all']);
    expect(inventarioKeys.productosInventario()).toEqual(['productos-inventario']);
    expect(inventarioKeys.producto('p1')).toEqual(['producto', 'p1']);
    expect(inventarioKeys.kardex('p1', '2024-01-01', '2024-02-01')).toEqual([
      'kardex',
      'p1',
      '2024-01-01',
      '2024-02-01',
    ]);
    expect(inventarioKeys.kardexAll()).toEqual(['kardex']);
  });

  it('notas de venta usan prefijo común para invalidación por familia', () => {
    const all = notasVentaKeys.all();
    const detail = notasVentaKeys.detail('nv1');
    expect(all).toEqual(['notas-venta']);
    expect(detail).toEqual(['notas-venta', 'nv1']);
    // El detalle comparte prefijo con la familia (permite invalidar por prefijo).
    expect(detail.slice(0, all.length)).toEqual(all);
  });

  it('pagos por documento comparten prefijo con la familia', () => {
    const all = pagosKeys.all();
    const porDoc = pagosKeys.porDocumento('NOTA_VENTA', 'nv1');
    expect(porDoc).toEqual(['pagos', 'NOTA_VENTA', 'nv1']);
    expect(porDoc.slice(0, all.length)).toEqual(all);
  });

  it('productos por empresa comparten prefijo con la familia', () => {
    const all = productosKeys.all();
    const porEmpresa = productosKeys.porEmpresa('e1');
    expect(porEmpresa).toEqual(['productos', 'e1']);
    expect(porEmpresa.slice(0, all.length)).toEqual(all);
  });
});
