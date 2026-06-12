import { describe, it, expect } from 'vitest';
import { contabilidadKeys, tesoreriaKeys } from '../lib/queryKeys';

describe('contabilidadKeys', () => {
  it('genera keys de asientos con defaults y con filtros', () => {
    expect(contabilidadKeys.asientos()).toEqual(['contabilidad', 'asientos', 'list', 1, null, null, null]);
    expect(
      contabilidadKeys.asientos(2, { estado: 'APROBADO', fechaDesde: '2026-06-01', fechaHasta: '2026-06-30' }),
    ).toEqual(['contabilidad', 'asientos', 'list', 2, 'APROBADO', '2026-06-01', '2026-06-30']);
  });

  it('los prefijos de familia cubren lista y detalle (invalidación)', () => {
    const all = contabilidadKeys.asientosAll();
    expect(contabilidadKeys.asiento('as-1').slice(0, all.length)).toEqual([...all]);
    expect(contabilidadKeys.detallesAsiento('as-1').slice(0, all.length)).toEqual([...all]);
    expect(contabilidadKeys.planCuentas()).toEqual(['contabilidad', 'plan-cuentas']);
    expect(contabilidadKeys.mapeosAll()).toEqual(['contabilidad', 'mapeos']);
    expect(contabilidadKeys.tiposAsiento()).toEqual(['contabilidad', 'tipos-asiento']);
  });
});

describe('tesoreriaKeys', () => {
  it('genera keys de movimientos con defaults y con filtros', () => {
    expect(tesoreriaKeys.movimientos()).toEqual([
      'tesoreria', 'movimientos-bancarios', 'list', 1, null, null,
    ]);
    expect(tesoreriaKeys.movimientos(3, { cuenta: 'cb-1', estado: 'PENDIENTE' })).toEqual([
      'tesoreria', 'movimientos-bancarios', 'list', 3, 'cb-1', 'PENDIENTE',
    ]);
  });

  it('genera keys de conciliaciones, cambio de divisa y catálogos', () => {
    const all = tesoreriaKeys.conciliacionesAll();
    expect(tesoreriaKeys.conciliaciones().slice(0, all.length)).toEqual([...all]);
    expect(tesoreriaKeys.conciliaciones(2)).toEqual(['tesoreria', 'conciliaciones', 'list', 2]);
    expect(tesoreriaKeys.conciliacion('con-1')).toEqual(['tesoreria', 'conciliaciones', 'detail', 'con-1']);
    expect(tesoreriaKeys.operacionesCambio()).toEqual(['tesoreria', 'operaciones-cambio', 'list', 1]);
    expect(tesoreriaKeys.operacionesCambio(4).slice(0, 2)).toEqual([
      ...tesoreriaKeys.operacionesCambioAll(),
    ]);
    expect(tesoreriaKeys.cuentasBancarias('emp-1')).toEqual(['tesoreria', 'cuentas-bancarias', 'emp-1']);
    expect(tesoreriaKeys.cuentasBancarias()).toEqual(['tesoreria', 'cuentas-bancarias', null]);
    expect(tesoreriaKeys.cajas('emp-1')).toEqual(['tesoreria', 'cajas', 'emp-1']);
    expect(tesoreriaKeys.cajas()).toEqual(['tesoreria', 'cajas', null]);
  });
});
