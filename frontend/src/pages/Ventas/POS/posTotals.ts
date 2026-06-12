/**
 * Sub-fase 1.G — POS de mostrador: aritmética monetaria del carrito y del
 * cobro mixto multimoneda, SIEMPRE con decimal.js (R-CODE-4). El IVA NO se
 * calcula aquí: lo devuelve el backend al crear la nota de venta.
 */
import Decimal from 'decimal.js';
import { D, sumDecimals } from '../../../lib/decimal';

export interface PosCartItem {
  id_producto: string;
  nombre: string;
  sku?: string;
  /** Precio unitario como string para no perder precisión en inputs. */
  precio: string;
  /** Cantidad como string (editable en UI). */
  cantidad: string;
}

export interface PosPago {
  /** Clave de idempotencia generada UNA vez al agregar el pago (PR #86/#89). */
  idempotencyKey: string;
  id_metodo_pago: string;
  nombre_metodo: string;
  id_moneda: string;
  codigo_iso: string;
  monto: string;
  /** Tasa USD→VES vigente al registrar el pago (1 si no aplica). */
  tasa: string;
  referencia?: string;
}

/** Total de una línea del carrito: cantidad × precio. */
export function lineaTotal(item: Pick<PosCartItem, 'cantidad' | 'precio'>): Decimal {
  return D(item.cantidad).times(D(item.precio));
}

/** Subtotal del carrito (sin IVA — el IVA lo calcula el backend). */
export function subtotalCarrito(items: PosCartItem[]): Decimal {
  return sumDecimals(items.map((i) => lineaTotal(i)));
}

/**
 * Convierte el monto de un pago a la moneda del documento.
 * Convención del proyecto (ModalPago): `tasa` es siempre la tasa base→país
 * (USD→VES). Si el pago está en la moneda del documento no se convierte; si
 * el documento está en VES y el pago en otra moneda, se multiplica por tasa;
 * en el caso inverso se divide.
 */
export function montoEnDocumento(
  pago: Pick<PosPago, 'monto' | 'tasa' | 'codigo_iso'>,
  codigoIsoDocumento: string,
): Decimal {
  const monto = D(pago.monto);
  if (pago.codigo_iso === codigoIsoDocumento) return monto;
  const tasa = D(pago.tasa);
  if (tasa.isZero()) return new Decimal(0);
  // Documento en moneda país (VES): pago en divisa × tasa.
  if (codigoIsoDocumento === 'VES') return monto.times(tasa);
  // Documento en divisa (USD): pago en VES ÷ tasa.
  if (pago.codigo_iso === 'VES') return monto.dividedBy(tasa);
  return monto;
}

/** Total pagado expresado en la moneda del documento. */
export function totalPagado(pagos: PosPago[], codigoIsoDocumento: string): Decimal {
  return sumDecimals(pagos.map((p) => montoEnDocumento(p, codigoIsoDocumento)));
}

/** Restante por pagar (>= 0) en la moneda del documento. */
export function restantePorPagar(
  total: Decimal,
  pagos: PosPago[],
  codigoIsoDocumento: string,
): Decimal {
  const restante = total.minus(totalPagado(pagos, codigoIsoDocumento));
  return restante.isNegative() ? new Decimal(0) : restante;
}

/** Vuelto (>= 0) en la moneda del documento. */
export function vuelto(total: Decimal, pagos: PosPago[], codigoIsoDocumento: string): Decimal {
  const v = totalPagado(pagos, codigoIsoDocumento).minus(total);
  return v.isNegative() ? new Decimal(0) : v;
}
