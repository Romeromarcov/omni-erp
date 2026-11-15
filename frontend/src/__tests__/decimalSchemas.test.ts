import { describe, expect, it } from 'vitest';
import { D, formatoMoneda } from '../lib/decimal';
import { decimalEntre, decimalNoNegativo, decimalPositivo } from '../schemas/decimal.schemas';
import {
  detalleNotaCreditoFiscalSchema,
  detalleNotaCreditoVentaSchema,
  detalleDevolucionVentaSchema,
} from '../schemas/ventas.schemas';

const mensajes = (r: { success: boolean; error?: { issues: { message: string }[] } }) =>
  r.success ? [] : (r.error?.issues ?? []).map((i) => i.message);

describe('decimalPositivo', () => {
  const s = decimalPositivo('Obligatorio', 'Debe ser mayor a 0');

  it.each(['1', '0.0001', '10.50', '12345678901234.5678', ' 7 '])('acepta %j', (v) => {
    expect(s.safeParse(v).success).toBe(true);
  });

  it('devuelve el MISMO string, sin pasar por number (sin espacios en los extremos)', () => {
    expect(s.parse(' 7.50 ')).toBe('7.50');
  });

  it.each(['0', '0.00', '-3', 'abc', '1e3', '1,5', '1.2.3', '', '  ', '+5', '1 000', '.5', '5.'])(
    'rechaza %j',
    (v) => {
      expect(s.safeParse(v).success).toBe(false);
    },
  );

  it('usa el mensaje de "obligatorio" para vacío y el de valor para el resto', () => {
    expect(mensajes(s.safeParse(''))).toContain('Obligatorio');
    expect(mensajes(s.safeParse('0'))).toContain('Debe ser mayor a 0');
    expect(mensajes(s.safeParse('abc'))).toContain('Debe ser mayor a 0');
  });
});

describe('decimalNoNegativo', () => {
  const s = decimalNoNegativo('Obligatorio', 'No puede ser negativo');

  it.each(['0', '0.00', '19.99', '999999999999999.9999'])('acepta %j', (v) => {
    expect(s.safeParse(v).success).toBe(true);
  });

  it('un negativo recibe el mensaje de negativo, no uno de formato', () => {
    expect(mensajes(s.safeParse('-1'))).toEqual(expect.arrayContaining(['No puede ser negativo']));
    expect(s.safeParse('-0.01').success).toBe(false);
  });

  it.each(['abc', '1e2', '1,5', ''])('rechaza %j', (v) => {
    expect(s.safeParse(v).success).toBe(false);
  });
});

describe('decimalEntre', () => {
  const s = decimalEntre(0, 100, {
    requerido: 'Obligatorio',
    invalido: 'Debe ser un número',
    bajoElMinimo: 'No puede ser negativo',
    sobreElMaximo: 'No puede superar 100',
  });

  it.each(['0', '50', '100', '99.99', '0.5'])('acepta %j', (v) => {
    expect(s.safeParse(v).success).toBe(true);
  });

  it('cada causa conserva su propio mensaje', () => {
    expect(mensajes(s.safeParse('150'))).toEqual(['No puede superar 100']);
    expect(mensajes(s.safeParse('-5'))).toEqual(['No puede ser negativo']);
    expect(mensajes(s.safeParse('100.01'))).toEqual(['No puede superar 100']);
    expect(mensajes(s.safeParse('abc'))).toEqual(['Debe ser un número']);
    expect(mensajes(s.safeParse(''))).toContain('Obligatorio');
  });
});

describe('esquemas de detalle (R-CODE-4: el monto viaja como string)', () => {
  const idProducto = 'p-1';

  it('nota de crédito de venta: conserva cantidad y precio exactos', () => {
    const r = detalleNotaCreditoVentaSchema.parse({
      id_producto: idProducto,
      cantidad: '2.5',
      precio_unitario: '12345678901234.5678',
    });
    expect(r.cantidad).toBe('2.5');
    expect(r.precio_unitario).toBe('12345678901234.5678');
    expect(typeof r.precio_unitario).toBe('string');
  });

  it('con number se perdería precisión; con el esquema nuevo no', () => {
    const monto = '12345678901234.5678'; // 18 cifras significativas, cabe en DecimalField(18, 4)
    expect(String(Number(monto))).not.toBe(monto); // el float lo deforma
    const r = detalleNotaCreditoVentaSchema.parse({ id_producto: idProducto, cantidad: '1', precio_unitario: monto });
    expect(D(r.precio_unitario).times(D(r.cantidad)).toFixed()).toBe(monto);
  });

  it('nota de crédito fiscal: valida descuento con sus mensajes originales', () => {
    const base = { id_producto: idProducto, cantidad: '1', precio_unitario: '10' };
    expect(detalleNotaCreditoFiscalSchema.safeParse({ ...base, descuento_porcentaje: '10' }).success).toBe(true);
    expect(mensajes(detalleNotaCreditoFiscalSchema.safeParse({ ...base, descuento_porcentaje: '150' }))).toContain(
      'El descuento no puede superar 100',
    );
    expect(mensajes(detalleNotaCreditoFiscalSchema.safeParse({ ...base, descuento_porcentaje: '-1' }))).toContain(
      'El descuento no puede ser negativo',
    );
  });

  it('devolución: cantidad > 0 y precio >= 0, con los mensajes de siempre', () => {
    const ok = detalleDevolucionVentaSchema.safeParse({
      id_producto: idProducto,
      cantidad_devuelta: '3',
      precio_unitario: '0',
      estado_producto: 'BUENO',
      accion_inventario: 'REINTEGRAR',
    });
    expect(ok.success).toBe(true);

    const mal = detalleDevolucionVentaSchema.safeParse({
      id_producto: idProducto,
      cantidad_devuelta: '0',
      precio_unitario: '-2',
      estado_producto: 'BUENO',
      accion_inventario: 'REINTEGRAR',
    });
    const msgs = mensajes(mal);
    expect(msgs).toContain('La cantidad debe ser mayor a 0');
    expect(msgs).toContain('El precio unitario no puede ser negativo');
  });

  it('rechaza un number: el contrato del formulario es string', () => {
    const r = detalleNotaCreditoVentaSchema.safeParse({ id_producto: idProducto, cantidad: 2, precio_unitario: 5 });
    expect(r.success).toBe(false);
  });
});

describe('formatoMoneda (solo presentación)', () => {
  it('formatea el string decimal de la API en es-VE / VES', () => {
    const txt = formatoMoneda('1234.5');
    expect(txt).toMatch(/1\.234,50/);
  });

  it('vacío o nulo no muestra nada', () => {
    expect(formatoMoneda(undefined)).toBe('');
    expect(formatoMoneda(null)).toBe('');
    expect(formatoMoneda('')).toBe('');
  });

  it('un valor no numérico se muestra como 0 (D() lo trata como 0)', () => {
    expect(formatoMoneda('abc')).toMatch(/0,00/);
  });
});
