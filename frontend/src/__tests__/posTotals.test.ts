/**
 * Sub-fase 1.G — POS: la aritmética del carrito/cobro es decimal.js puro
 * (R-CODE-4). Estos tests fijan los totales EXACTOS (sin errores de flotante).
 */
import { describe, it, expect } from 'vitest';
import Decimal from 'decimal.js';
import {
  lineaTotal, subtotalCarrito, montoEnDocumento, totalPagado,
  restantePorPagar, vuelto, type PosCartItem, type PosPago,
} from '../pages/Ventas/POS/posTotals';

const item = (precio: string, cantidad: string): PosCartItem => ({
  id_producto: 'p', nombre: 'P', precio, cantidad,
});

const pago = (monto: string, codigo_iso: string, tasa = '1'): PosPago => ({
  idempotencyKey: `k-${monto}-${codigo_iso}`,
  id_metodo_pago: 'm1', nombre_metodo: 'Efectivo',
  id_moneda: 'mo1', codigo_iso, monto, tasa,
});

describe('posTotals (decimal.js)', () => {
  it('calcula totales de línea sin error de punto flotante (0.1 × 3 = 0.30 exacto)', () => {
    expect(lineaTotal(item('0.1', '3')).toFixed(2)).toBe('0.30');
    // En flotante: 3 * 1.1 = 3.3000000000000003
    expect(lineaTotal(item('1.1', '3')).toString()).toBe('3.3');
  });

  it('suma el subtotal del carrito con precisión exacta (0.1 + 0.2 = 0.3)', () => {
    const carrito = [item('0.1', '1'), item('0.2', '1')];
    expect(subtotalCarrito(carrito).toString()).toBe('0.3');
  });

  it('trata cantidades vacías o inválidas como 0', () => {
    expect(lineaTotal(item('10', '')).toString()).toBe('0');
    expect(lineaTotal(item('10', 'abc')).toString()).toBe('0');
  });

  it('convierte pagos en divisa a la moneda del documento con la tasa', () => {
    // Documento en VES, pago de 2 USD a tasa 36.5 → 73 VES.
    expect(montoEnDocumento(pago('2', 'USD', '36.5'), 'VES').toString()).toBe('73');
    // Pago en la misma moneda del documento: sin conversión.
    expect(montoEnDocumento(pago('50', 'VES', '36.5'), 'VES').toString()).toBe('50');
    // Documento en USD, pago de 73 VES a tasa 36.5 → 2 USD.
    expect(montoEnDocumento(pago('73', 'VES', '36.5'), 'USD').toString()).toBe('2');
    // Tasa 0 (inválida): el pago no aporta.
    expect(montoEnDocumento(pago('10', 'USD', '0'), 'VES').toString()).toBe('0');
  });

  it('calcula total pagado, restante y vuelto en pago mixto multimoneda', () => {
    const total = new Decimal('116.00');
    const pagos = [pago('80', 'VES'), pago('1', 'USD', '40')]; // 80 + 40 = 120
    expect(totalPagado(pagos, 'VES').toString()).toBe('120');
    expect(restantePorPagar(total, pagos, 'VES').toString()).toBe('0');
    expect(vuelto(total, pagos, 'VES').toFixed(2)).toBe('4.00');
  });

  it('restante nunca es negativo y vuelto nunca es negativo', () => {
    const total = new Decimal('100');
    expect(restantePorPagar(total, [pago('30', 'VES')], 'VES').toString()).toBe('70');
    expect(vuelto(total, [pago('30', 'VES')], 'VES').toString()).toBe('0');
    expect(restantePorPagar(total, [pago('150', 'VES')], 'VES').toString()).toBe('0');
  });
});
