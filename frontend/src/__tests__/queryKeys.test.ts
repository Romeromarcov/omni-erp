import { describe, it, expect } from 'vitest';
import {
  inventarioKeys,
  notasVentaKeys,
  pagosKeys,
  pedidosKeys,
  almacenesKeys,
  productosKeys,
  ventasKeys,
  cxcKeys,
  finanzasKeys,
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

  it('pedidos y almacenes: el detalle comparte prefijo con la familia', () => {
    const all = pedidosKeys.all();
    const detail = pedidosKeys.detail('p1');
    expect(all).toEqual(['pedidos']);
    expect(detail).toEqual(['pedidos', 'detail', 'p1']);
    expect(detail.slice(0, all.length)).toEqual(all);
    expect(almacenesKeys.all()).toEqual(['almacenes']);
  });

  it('cxc cuentas: paginada con default y prefijo de familia', () => {
    expect(cxcKeys.cuentas()).toEqual(['cxc', 'cuentas', 1]);
    expect(cxcKeys.cuentas(3)).toEqual(['cxc', 'cuentas', 3]);
    const all = cxcKeys.cuentasAll();
    expect(cxcKeys.cuentas(3).slice(0, all.length)).toEqual(all);
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

  it('ventas: el detalle de cada documento comparte prefijo con su familia', () => {
    const families = [
      ventasKeys.devoluciones,
      ventasKeys.notasCreditoVenta,
      ventasKeys.notasCreditoFiscal,
      ventasKeys.cotizaciones,
    ];
    for (const fam of families) {
      const all = fam.all();
      const detail = fam.detail('x1');
      expect(detail.slice(0, all.length)).toEqual(all);
    }
    expect(ventasKeys.clientes('e1')).toEqual(['ventas', 'clientes', 'e1']);
    expect(ventasKeys.productos(null)).toEqual(['ventas', 'productos', null]);
  });

  it('cxc: las queries comparten prefijo con su familia para invalidar por prefijo', () => {
    expect(cxcKeys.carteraDashboard().slice(0, cxcKeys.carteraAll().length)).toEqual(
      cxcKeys.carteraAll(),
    );
    expect(cxcKeys.tasasHoy().slice(0, cxcKeys.tasasAll().length)).toEqual(cxcKeys.tasasAll());
    expect(cxcKeys.acuerdos('VIGENTE').slice(0, cxcKeys.acuerdosAll().length)).toEqual(
      cxcKeys.acuerdosAll(),
    );
    expect(cxcKeys.acuerdos()).toEqual(['cxc', 'acuerdos', null]);
  });

  it('finanzas: cajas-fisicas y monedas comparten prefijo de familia', () => {
    const cf = finanzasKeys.cajasFisicas;
    expect(cf.list('e1').slice(0, cf.all().length)).toEqual(cf.all());
    expect(cf.detail('c1').slice(0, cf.all().length)).toEqual(cf.all());
    expect(cf.virtuales('c1').slice(0, cf.all().length)).toEqual(cf.all());
    // El catálogo de tipos NO debe colgar del prefijo de la familia.
    expect(cf.tipoChoices().slice(0, cf.all().length)).not.toEqual(cf.all());

    const mon = finanzasKeys.monedas;
    expect(mon.detail('m1').slice(0, mon.all().length)).toEqual(mon.all());
    expect(mon.listFull().slice(0, mon.all().length)).toEqual(mon.all());
    expect(finanzasKeys.pagos.porDocumento('COTIZACION', 'q1')).toEqual([
      'finanzas',
      'pagos',
      'COTIZACION',
      'q1',
    ]);
  });
});
