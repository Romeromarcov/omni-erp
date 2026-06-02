import { describe, it, expect } from 'vitest';
import { facturaFiscalSchema } from '../schemas/ventas.schemas';

const baseFactura = {
  fecha_emision: '2026-06-01',
  id_empresa: 'emp-1',
  id_cliente: 'cli-1',
  condicion_pago: 'CONTADO' as const,
  detalles: [
    { id_producto: 'p1', cantidad: '2', precio_unitario: '100' }, // 200
    { id_producto: 'p2', cantidad: '1', precio_unitario: '50' }, // 50
  ],
};

describe('facturaFiscalSchema cross-field total validation (FE-HIGH-8)', () => {
  it('accepts a factura whose monto_total matches the sum of detalles', () => {
    const result = facturaFiscalSchema.safeParse({ ...baseFactura, monto_total: '250.00' });
    expect(result.success).toBe(true);
  });

  it('accepts a factura without monto_total (optional)', () => {
    const result = facturaFiscalSchema.safeParse(baseFactura);
    expect(result.success).toBe(true);
  });

  it('rejects a factura whose monto_total does not match the detalles', () => {
    const result = facturaFiscalSchema.safeParse({ ...baseFactura, monto_total: '999.99' });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message === 'El total no cuadra con los detalles')).toBe(true);
    }
  });

  it('accepts a tiny rounding difference within epsilon', () => {
    const result = facturaFiscalSchema.safeParse({ ...baseFactura, monto_total: '250.005' });
    expect(result.success).toBe(true);
  });

  it('honors line descuento_porcentaje when summing detalles', () => {
    // line1: 2*100 = 200, 10% off => 180 ; line2: 50 => total 230
    const result = facturaFiscalSchema.safeParse({
      ...baseFactura,
      detalles: [
        { id_producto: 'p1', cantidad: '2', precio_unitario: '100', descuento_porcentaje: '10' },
        { id_producto: 'p2', cantidad: '1', precio_unitario: '50' },
      ],
      monto_total: '230.00',
    });
    expect(result.success).toBe(true);
  });
});
