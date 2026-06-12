import { describe, it, expect } from 'vitest';
import { isSimilar, findSimilarMoneda, findSimilarMetodoPago } from '../utils/fuzzyDuplicate';
import type { MetodoPago } from '../utils/fuzzyDuplicate';
import type { Moneda } from '../pages/Finanzas/Monedas/MonedaListPage';

function moneda(overrides: Partial<Moneda>): Moneda {
  return {
    id_moneda: 'm1',
    tipo_moneda: 'fiat',
    codigo_iso: 'USD',
    nombre: 'Dólar',
    simbolo: '$',
    decimales: 2,
    activo: true,
    ...overrides,
  };
}

function metodo(overrides: Partial<MetodoPago>): MetodoPago {
  return {
    id_metodo_pago: 'mp1',
    nombre_metodo: 'Efectivo',
    tipo_metodo: 'efectivo',
    activo: true,
    ...overrides,
  };
}

describe('isSimilar', () => {
  it('devuelve true para strings idénticos', () => {
    expect(isSimilar('Efectivo', 'Efectivo')).toBe(true);
  });

  it('devuelve true para strings casi idénticos (typo)', () => {
    expect(isSimilar('Efectivo', 'Efectiv')).toBe(true);
  });

  it('devuelve false para strings completamente distintos', () => {
    expect(isSimilar('Transferencia bancaria', 'zzzzqqqq')).toBe(false);
  });

  it('devuelve false cuando alguno de los strings está vacío', () => {
    expect(isSimilar('', 'Efectivo')).toBe(false);
    expect(isSimilar('Efectivo', '')).toBe(false);
  });

  it('respeta el threshold: con threshold 100 solo acepta match exacto', () => {
    expect(isSimilar('Efectivo', 'Efectivo', 100)).toBe(true);
    expect(isSimilar('Efectivoz', 'Efectivo', 100)).toBe(false);
  });
});

describe('findSimilarMoneda', () => {
  const lista: Moneda[] = [
    moneda({ id_moneda: 'usd', codigo_iso: 'USD', nombre: 'Dólar Americano', tipo_moneda: 'fiat' }),
    moneda({ id_moneda: 'btc', codigo_iso: 'BTC', nombre: 'Bitcoin', tipo_moneda: 'crypto' }),
  ];

  it('encuentra una moneda con nombre similar y mismo tipo', () => {
    const dup = findSimilarMoneda({ nombre: 'Dólar Americano', tipo_moneda: 'fiat' }, lista);
    expect(dup?.id_moneda).toBe('usd');
  });

  it('encuentra una moneda por código ISO igual', () => {
    const dup = findSimilarMoneda({ codigo_iso: 'BTC', tipo_moneda: 'crypto' }, lista);
    expect(dup?.id_moneda).toBe('btc');
  });

  it('NO marca duplicado si el tipo de moneda difiere aunque el nombre coincida', () => {
    const dup = findSimilarMoneda({ nombre: 'Bitcoin', tipo_moneda: 'fiat' }, lista);
    expect(dup).toBeUndefined();
  });

  it('devuelve undefined si no hay nada parecido', () => {
    const dup = findSimilarMoneda({ nombre: 'xqzwk', codigo_iso: 'XQZ', tipo_moneda: 'fiat' }, lista);
    expect(dup).toBeUndefined();
  });
});

describe('findSimilarMetodoPago', () => {
  const lista: MetodoPago[] = [
    metodo({ id_metodo_pago: 'efe', nombre_metodo: 'Efectivo USD', tipo_metodo: 'efectivo' }),
    metodo({ id_metodo_pago: 'tra', nombre_metodo: 'Transferencia', tipo_metodo: 'transferencia' }),
  ];

  it('encuentra un método con nombre similar y mismo tipo', () => {
    const dup = findSimilarMetodoPago({ nombre_metodo: 'Efectivo USD', tipo_metodo: 'efectivo' }, lista);
    expect(dup?.id_metodo_pago).toBe('efe');
  });

  it('NO marca duplicado si el tipo de método difiere', () => {
    const dup = findSimilarMetodoPago({ nombre_metodo: 'Transferencia', tipo_metodo: 'efectivo' }, lista);
    expect(dup).toBeUndefined();
  });

  it('devuelve undefined sin nombre_metodo', () => {
    const dup = findSimilarMetodoPago({ tipo_metodo: 'efectivo' }, lista);
    expect(dup).toBeUndefined();
  });
});
