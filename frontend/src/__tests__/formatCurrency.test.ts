import { describe, it, expect } from 'vitest';
import { D } from '../lib/decimal';
import { formatCurrency } from '../utils/formatCurrency';

describe('formatCurrency (Decimal-safe)', () => {
  it('formatea 0.1 + 0.2 exacto sin error de punto flotante', () => {
    const suma = D('0.1').plus(D('0.2'));
    expect(formatCurrency(suma)).toBe('$0.30');
    expect(formatCurrency(0.1 + 0.2)).toBe('$0.30');
  });

  it('acepta montos grandes como string sin truncamiento IEEE-754', () => {
    expect(formatCurrency('123456789012345678.95', 'USD', 'en-US')).toBe('$123,456,789,012,345,678.95');
  });

  it('soporta VES con locale es-VE por defecto explícito', () => {
    const txt = formatCurrency('1234.5', 'VES', 'es-VE');
    expect(txt).toContain('1.234,50');
  });

  it('maneja null, undefined, cadena vacía y no numérica de forma segura como 0.00', () => {
    expect(formatCurrency(null)).toBe('$0.00');
    expect(formatCurrency(undefined)).toBe('$0.00');
    expect(formatCurrency('')).toBe('$0.00');
    expect(formatCurrency('abc')).toBe('$0.00');
  });
});
