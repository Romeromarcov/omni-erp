import { describe, it, expect } from 'vitest';
import {
  facturaFiscalSchema,
  detalleVentaSchema,
  cotizacionFormSchema,
  pedidoFormSchema,
  notaVentaFormSchema,
  facturaFiscalFormSchema,
} from '../schemas/ventas.schemas';

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

describe('detalleVentaSchema (refines de línea)', () => {
  const linea = (o: Record<string, unknown> = {}) => ({
    id_producto: 'p1',
    cantidad: '2',
    precio_unitario: '100',
    ...o,
  });

  it('acepta una línea válida', () => {
    expect(detalleVentaSchema.safeParse(linea()).success).toBe(true);
  });

  it('rechaza producto vacío', () => {
    expect(detalleVentaSchema.safeParse(linea({ id_producto: '' })).success).toBe(false);
  });

  it('rechaza cantidad 0 o no numérica', () => {
    expect(detalleVentaSchema.safeParse(linea({ cantidad: '0' })).success).toBe(false);
    expect(detalleVentaSchema.safeParse(linea({ cantidad: 'abc' })).success).toBe(false);
  });

  it('rechaza precio_unitario negativo, acepta 0', () => {
    expect(detalleVentaSchema.safeParse(linea({ precio_unitario: '-5' })).success).toBe(false);
    expect(detalleVentaSchema.safeParse(linea({ precio_unitario: '0' })).success).toBe(true);
  });

  it('descuento: acepta vacío/omitido y 0-100, rechaza >100 o negativo', () => {
    expect(detalleVentaSchema.safeParse(linea({ descuento_porcentaje: '' })).success).toBe(true);
    expect(detalleVentaSchema.safeParse(linea({ descuento_porcentaje: '50' })).success).toBe(true);
    expect(detalleVentaSchema.safeParse(linea({ descuento_porcentaje: '150' })).success).toBe(false);
    expect(detalleVentaSchema.safeParse(linea({ descuento_porcentaje: '-1' })).success).toBe(false);
  });
});

describe('facturaFiscalSchema — condición de pago y monto_total', () => {
  it('CRÉDITO sin dias_credito es inválido (path dias_credito)', () => {
    const r = facturaFiscalSchema.safeParse({ ...baseFactura, condicion_pago: 'CREDITO' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues.some((i) => i.path.includes('dias_credito'))).toBe(true);
    }
  });

  it('CRÉDITO con dias_credito > 0 es válido', () => {
    const r = facturaFiscalSchema.safeParse({
      ...baseFactura,
      condicion_pago: 'CREDITO',
      dias_credito: 30,
    });
    expect(r.success).toBe(true);
  });

  it('condición de pago fuera del enum es inválida', () => {
    const r = facturaFiscalSchema.safeParse({ ...baseFactura, condicion_pago: 'PERMUTA' });
    expect(r.success).toBe(false);
  });

  it('monto_total no numérico es inválido', () => {
    const r = facturaFiscalSchema.safeParse({ ...baseFactura, monto_total: 'abc' });
    expect(r.success).toBe(false);
  });
});

describe('esquemas de formulario (RHF) — detalles mínimos', () => {
  const detalle = { id_producto: 'p1', cantidad: '1', precio_unitario: '10' };
  const base = {
    id_empresa: 'emp-1',
    id_sucursal: 'suc-1',
    detalles: [detalle],
  };

  it('cotizacionFormSchema: válido con moneda + fecha; rechaza detalles vacíos', () => {
    const valido = { ...base, fecha_cotizacion: '2026-06-01', id_moneda: 'mon-1' };
    expect(cotizacionFormSchema.safeParse(valido).success).toBe(true);
    expect(cotizacionFormSchema.safeParse({ ...valido, detalles: [] }).success).toBe(false);
  });

  it('pedidoFormSchema: válido; rechaza sin fecha', () => {
    expect(pedidoFormSchema.safeParse({ ...base, fecha_pedido: '2026-06-01' }).success).toBe(true);
    expect(pedidoFormSchema.safeParse({ ...base, fecha_pedido: '' }).success).toBe(false);
  });

  it('notaVentaFormSchema y facturaFiscalFormSchema: válidos con fecha_emision', () => {
    expect(notaVentaFormSchema.safeParse({ ...base, fecha_emision: '2026-06-01' }).success).toBe(true);
    expect(facturaFiscalFormSchema.safeParse({ ...base, fecha_emision: '2026-06-01' }).success).toBe(true);
  });
});
