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
  rrhhKeys,
  nominaKeys,
  tareasKeys,
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
    expect(inventarioKeys.categoriasProducto()).toEqual(['inv-categorias-producto']);
    expect(inventarioKeys.unidadesMedida()).toEqual(['inv-unidades-medida']);
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

  it('rrhh y nomina: lista, detalle y recibos comparten el prefijo de su familia', () => {
    // RRHH: crear/editar un empleado invalida lista, detalle y la variante por empresa.
    const empAll = rrhhKeys.empleadosAll();
    expect(rrhhKeys.empleados(2).slice(0, empAll.length)).toEqual(empAll);
    expect(rrhhKeys.empleados()).toEqual(['rrhh', 'empleados', 'list', 1]);
    expect(rrhhKeys.empleado('7').slice(0, empAll.length)).toEqual(empAll);
    expect(rrhhKeys.empleadosDeEmpresa('e1').slice(0, empAll.length)).toEqual(empAll);
    expect(rrhhKeys.empleadosDeEmpresa()).toEqual(['rrhh', 'empleados', 'empresa', null]);
    // El catálogo de cargos NO cuelga de la familia de empleados.
    expect(rrhhKeys.cargos().slice(0, empAll.length)).not.toEqual(empAll);

    // Nómina: procesar invalida lista, detalle y recibos con un solo prefijo.
    const procAll = nominaKeys.procesosAll();
    expect(nominaKeys.procesos(3).slice(0, procAll.length)).toEqual(procAll);
    expect(nominaKeys.procesos()).toEqual(['nomina', 'procesos', 'list', 1]);
    expect(nominaKeys.proceso('p1').slice(0, procAll.length)).toEqual(procAll);
    expect(nominaKeys.recibos('p1').slice(0, procAll.length)).toEqual(procAll);
    // Los períodos NO deben invalidarse al procesar.
    expect(nominaKeys.periodos().slice(0, procAll.length)).not.toEqual(procAll);
  });

  it('tareasKeys aísla caché por empresaId y mantiene jerarquía de invalidación', () => {
    expect(tareasKeys.all()).toEqual(['tareas']);
    const emp = tareasKeys.porEmpresa('emp-1');
    expect(emp).toEqual(['tareas', 'emp-1']);
    expect(tareasKeys.porEmpresa()).toEqual(['tareas', null]);

    expect(tareasKeys.areas('emp-1').slice(0, emp.length)).toEqual(emp);
    expect(tareasKeys.proyectos('emp-1', false).slice(0, emp.length)).toEqual(emp);
    expect(tareasKeys.proyectos()).toEqual(['tareas', null, 'proyectos', null]);
    expect(tareasKeys.miTablero('emp-1')).toEqual(['tareas', 'emp-1', 'mi-tablero']);
    expect(tareasKeys.secciones('emp-1', 'p1')).toEqual(['tareas', 'emp-1', 'secciones', 'p1']);
    expect(tareasKeys.secciones()).toEqual(['tareas', null, 'secciones', null]);

    const itemsAll = tareasKeys.itemsAll('emp-1');
    expect(tareasKeys.items('emp-1', { estado: 'PENDIENTE' }).slice(0, itemsAll.length)).toEqual(
      itemsAll,
    );
    expect(tareasKeys.items()).toEqual([
      'tareas',
      null,
      'items',
      'list',
      null,
      null,
      null,
      null,
      null,
      null,
      null,
    ]);
    expect(tareasKeys.item('emp-1', 't1').slice(0, itemsAll.length)).toEqual(itemsAll);
    expect(tareasKeys.comentarios('emp-1', 't1').slice(0, itemsAll.length)).toEqual(itemsAll);
    expect(tareasKeys.dependencias('emp-1', 't1').slice(0, itemsAll.length)).toEqual(itemsAll);

    expect(tareasKeys.recurrentes('emp-1')).toEqual(['tareas', 'emp-1', 'recurrentes']);
    expect(tareasKeys.minutas('emp-1')).toEqual(['tareas', 'emp-1', 'minutas']);
    expect(tareasKeys.configuracion('emp-1')).toEqual(['tareas', 'emp-1', 'configuracion']);
    expect(tareasKeys.resumen('emp-1', '2026-11-20')).toEqual([
      'tareas',
      'emp-1',
      'resumen',
      '2026-11-20',
    ]);
    expect(tareasKeys.resumen()).toEqual(['tareas', null, 'resumen', null]);
    expect(tareasKeys.alertas('emp-1')).toEqual(['tareas', 'emp-1', 'alertas']);
  });
});
