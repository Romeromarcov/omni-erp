/**
 * Normaliza ítems de MetodoPagoEmpresaActiva y MonedaEmpresaActiva para consumir
 * SIEMPRE el contrato real del serializer backend (`metodo_pago`/`nombre` y
 * `moneda`/`moneda_codigo_iso`/`moneda_nombre`) manteniendo fallback legado
 * para mocks históricos en tests.
 */
import type { MetodoPagoEmpresaActiva } from '../../../services/metodosPagoEmpresaActiva';
import type { MonedaEmpresaActiva } from '../../../services/monedasEmpresaActiva';

/** UUID real de MetodoPago (PK para FKs, no el PK de la fila de activación). */
export function idMetodoPagoReal(metodo: MetodoPagoEmpresaActiva): string {
  return metodo.metodo_pago ?? metodo.id;
}

/** Etiqueta visible del método de pago. */
export function nombreMetodoPagoReal(metodo: MetodoPagoEmpresaActiva): string {
  return metodo.nombre ?? metodo.nombre_metodo ?? '';
}

/** UUID real de Moneda (PK para FKs, no el PK de la fila de activación). */
export function idMonedaReal(moneda: MonedaEmpresaActiva): string {
  return moneda.moneda ?? moneda.id_moneda;
}

/** Código ISO de la moneda. */
export function codigoIsoMonedaReal(moneda: MonedaEmpresaActiva): string {
  return moneda.moneda_codigo_iso ?? moneda.codigo_iso ?? '';
}
