import { describe, expect, it } from 'vitest';

import { buildVentaOfflineEnvelope, type VentaOfflineInput } from '../ventaOffline';

function inputValido(): VentaOfflineInput {
  return {
    id_sucursal: 'suc-1',
    id_caja: 'caja-1',
    id_cliente: 'cli-1',
    detalles: [{ id_producto: 'p1', cantidad: '2', precio_unitario: '3.50' }],
    pagos: [{ id_metodo_pago: 'm1', id_moneda: 'usd', monto: '7.00' }],
    totales_cliente: { subtotal: '7.00', iva: '0.00', total: '7.00' },
  };
}

describe('buildVentaOfflineEnvelope', () => {
  it('arma el sobre con client_uuid y fecha_local inyectables', () => {
    const now = new Date('2026-06-19T10:00:00.000Z');
    const sobre = buildVentaOfflineEnvelope(inputValido(), { clientUuid: 'uuid-1', now });
    expect(sobre.client_uuid).toBe('uuid-1');
    expect(sobre.fecha_local).toBe('2026-06-19T10:00:00.000Z');
    expect(sobre.id_sucursal).toBe('suc-1');
    expect(sobre.detalles).toHaveLength(1);
    expect(sobre.pagos).toHaveLength(1);
    expect(sobre.totales_cliente.total).toBe('7.00');
  });

  it('genera un client_uuid cuando no se inyecta', () => {
    const sobre = buildVentaOfflineEnvelope(inputValido());
    expect(sobre.client_uuid).toBeTruthy();
    expect(typeof sobre.client_uuid).toBe('string');
  });

  it('hace copias defensivas (no comparte referencias con el input)', () => {
    const input = inputValido();
    const sobre = buildVentaOfflineEnvelope(input);
    expect(sobre.detalles).not.toBe(input.detalles);
    expect(sobre.detalles[0]).not.toBe(input.detalles[0]);
    expect(sobre.pagos[0]).not.toBe(input.pagos[0]);
    expect(sobre.totales_cliente).not.toBe(input.totales_cliente);
  });

  it('lanza si no hay líneas', () => {
    const input = { ...inputValido(), detalles: [] };
    expect(() => buildVentaOfflineEnvelope(input)).toThrow(/al menos una línea/);
  });

  it('lanza si no hay pagos', () => {
    const input = { ...inputValido(), pagos: [] };
    expect(() => buildVentaOfflineEnvelope(input)).toThrow(/al menos un pago/);
  });

  it('preserva los montos como string (R-CODE-4)', () => {
    const sobre = buildVentaOfflineEnvelope(inputValido());
    expect(sobre.detalles[0].precio_unitario).toBe('3.50');
    expect(sobre.pagos[0].monto).toBe('7.00');
    expect(typeof sobre.totales_cliente.iva).toBe('string');
  });
});
