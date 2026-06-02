import { describe, it, expect } from 'vitest';
import { D, sumDecimals, subtotalLinea, toFixedStr } from '../lib/decimal';

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

  it('treats non-numeric strings as 0', () => {
    expect(D('abc').toFixed(2)).toBe('0.00');
  });
});

describe('sumDecimals', () => {
  it('sums precisely without float drift', () => {
    expect(sumDecimals(['0.1', '0.2', '0.3']).toFixed(2)).toBe('0.60');
  });

  it('sums Decimal inputs', () => {
    expect(sumDecimals([D('1.5'), D('2.5')]).toFixed(2)).toBe('4.00');
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

  it('matches a tricky float case exactly', () => {
    // 1.1 * 1.1 = 1.21 (native: 1.2100000000000002)
    expect(subtotalLinea('1.1', '1.1').toFixed(2)).toBe('1.21');
  });
});

describe('toFixedStr', () => {
  it('formats numbers/strings/Decimals to fixed decimals', () => {
    expect(toFixedStr('1.005')).toBe('1.01');
    expect(toFixedStr(2)).toBe('2.00');
    expect(toFixedStr(D('3.14159'), 4)).toBe('3.1416');
  });
});
