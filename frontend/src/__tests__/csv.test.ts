import { describe, it, expect } from 'vitest';

import { toCsv } from '../utils/csv';

describe('toCsv', () => {
  it('arma encabezado + filas, todo entre comillas', () => {
    expect(toCsv(['A', 'B'], [['1', '2']])).toBe('"A","B"\n"1","2"');
  });

  it('escapa comillas dobles duplicándolas', () => {
    expect(toCsv(['x'], [['di "hola"']])).toBe('"x"\n"di ""hola"""');
  });

  it('trata null/undefined como celda vacía', () => {
    expect(toCsv(['a', 'b'], [[null, undefined]])).toBe('"a","b"\n"",""');
  });

  it('coacciona números a texto sin alterar el valor (dinero como string)', () => {
    // El monto debe pasarse como string crudo para no perder precisión (R-CODE-4).
    expect(toCsv(['n', 'monto'], [[5, '1234.56']])).toBe('"n","monto"\n"5","1234.56"');
  });

  it('solo encabezado cuando no hay filas', () => {
    expect(toCsv(['A', 'B'], [])).toBe('"A","B"');
  });
});
