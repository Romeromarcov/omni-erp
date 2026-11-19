import { describe, it, expect } from 'vitest';
import { D, sumDecimals, subtotalLinea, toFixedStr, formatoDecimal } from '../lib/decimal';

describe('D / decimal arithmetic (FE-HIGH-7)', () => {
  it('avoids floating-point error: 0.1 + 0.2 === 0.30', () => {
    expect(D('0.1').plus(D('0.2')).toFixed(2)).toBe('0.30');
    // sanity: native float fails this
    expect((0.1 + 0.2).toString()).not.toBe('0.3');
  });

  it('treats null/undefined/empty as 0', () => {
    expect(D(null).toFixed(2)).toBe('0.00');
    expect(D(undefined).toFixed(2)).toBe('0.00');
    expect(D('').toFixed(2)).toBe('0.00');
  });

  it('treats non-numeric strings and Infinity as 0', () => {
    expect(D('abc').toFixed(2)).toBe('0.00');
    expect(D(Infinity).toFixed(2)).toBe('0.00');
    expect(D(NaN).toFixed(2)).toBe('0.00');
  });

  it('preserves Decimal instances and high precision (>15 significant digits)', () => {
    const big = D('12345678901234567890.1234');
    expect(D(big).toString()).toBe('12345678901234567890.1234');
  });
});

describe('sumDecimals', () => {
  it('sums precisely without float drift', () => {
    expect(sumDecimals(['0.1', '0.2', '0.3']).toFixed(2)).toBe('0.60');
  });

  it('sums Decimal, number, null and undefined inputs', () => {
    expect(sumDecimals([D('1.5'), '2.5', null, undefined]).toFixed(2)).toBe('4.00');
  });
});

describe('subtotalLinea (cantidad * precio - descuento)', () => {
  it('computes cantidad * precio to 2 decimals', () => {
    // 3 * 19.99 = 59.97
    expect(subtotalLinea('3', '19.99').toFixed(2)).toBe('59.97');
  });

  it('applies descuento porcentaje', () => {
    // 2 * 100 = 200, 10% off => 180
    expect(subtotalLinea('2', '100', '10').toFixed(2)).toBe('180.00');
  });

  it('accepts Decimal instances as inputs', () => {
    expect(subtotalLinea(D('0.1'), D('0.3')).toFixed(2)).toBe('0.03');
  });

  it('matches a tricky float case exactly', () => {
    // 1.1 * 1.1 = 1.21 (native: 1.2100000000000002)
    expect(subtotalLinea('1.1', '1.1').toFixed(2)).toBe('1.21');
  });
});

describe('toFixedStr', () => {
  it('formats numbers/strings/Decimals/nullables to fixed decimals', () => {
    expect(toFixedStr('1.005')).toBe('1.01');
    expect(toFixedStr(2)).toBe('2.00');
    expect(toFixedStr(D('3.14159'), 4)).toBe('3.1416');
    expect(toFixedStr(null)).toBe('0.00');
  });
});

describe('formatoDecimal', () => {
  it('formatea montos grandes sin pérdida IEEE-754', () => {
    // Number('123456789012345678.95') pierde precisión en float binario; como string conserva todas las cifras.
    expect(formatoDecimal('123456789012345678.95', 2, 2, 'es-VE')).toBe('123.456.789.012.345.678,95');
  });

  it('normaliza -0.00 a 0,00 positivo', () => {
    expect(formatoDecimal('-0.001', 2, 2, 'es-VE')).toBe('0,00');
  });
});
