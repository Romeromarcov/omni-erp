/**
 * FE-HIGH-7: Helpers de aritmética monetaria con decimal.js.
 *
 * Evita los errores de punto flotante de JavaScript (p. ej. 0.1 + 0.2 !== 0.3)
 * en todos los cálculos de montos antes de enviarlos al backend.
 */
import Decimal from 'decimal.js';

/** Valor que puede convertirse a Decimal. */
export type DecimalInput = Decimal | string | number | null | undefined;

/**
 * Construye un Decimal de forma segura a partir de {@link DecimalInput}
 * (`Decimal | string | number | null | undefined`).
 *
 * Cualquier valor nulo, vacío, no finito o que decimal.js no pueda interpretar cae
 * en 0 sin pasar por `Number()`, preservando la precisión decimal exacta.
 */
export const D = (x: DecimalInput): Decimal => {
  if (x === null || x === undefined || x === '') return new Decimal(0);
  try {
    const d = x instanceof Decimal ? x : new Decimal(x);
    return !d.isFinite() ? new Decimal(0) : d;
  } catch {
    // decimal.js lanza ante strings no numéricos (p. ej. 'abc'); tratarlos como 0.
    return new Decimal(0);
  }
};

/** Suma una lista de valores con precisión decimal. */
export function sumDecimals(values: DecimalInput[]): Decimal {
  return values.reduce<Decimal>((acc, v) => acc.plus(D(v)), new Decimal(0));
}

/**
 * Calcula el subtotal de una línea: cantidad * precio, restando el descuento %.
 * descuentoPorcentaje se aplica sobre el monto bruto (cantidad * precio).
 */
export function subtotalLinea(
  cantidad: DecimalInput,
  precio: DecimalInput,
  descuentoPorcentaje?: DecimalInput,
): Decimal {
  const bruto = D(cantidad).times(D(precio));
  const desc = D(descuentoPorcentaje).dividedBy(100);
  return bruto.minus(bruto.times(desc));
}

/** Formatea un valor monetario a un string con decimales fijos (por defecto 2). */
export function toFixedStr(value: DecimalInput, decimals = 2): string {
  return D(value).toFixed(decimals);
}

type IntlFormatWithString = (value: number | bigint | `${number}`) => string;

function aStringFormateable(d: Decimal, decimals: number): `${number}` {
  const redondeado = d.toDecimalPlaces(decimals);
  // Evita "-0.00" cuando un valor negativo pequeño se redondea a cero.
  return (redondeado.isZero() ? new Decimal(0).toFixed(decimals) : redondeado.toFixed(decimals)) as `${number}`;
}

/**
 * Formato decimal localizado SOLO para presentación en UI (nunca para cálculos ni payloads).
 * Usa strings decimales con `Intl.NumberFormat` (sin pasar por `toNumber()` / IEEE-754)
 * para no perder dígitos en montos grandes ni introducir ruido de coma flotante.
 */
export function formatoDecimal(
  valor: DecimalInput,
  minimumFractionDigits = 2,
  maximumFractionDigits = minimumFractionDigits,
  locale = 'es-VE',
): string {
  const d = D(valor);
  const str = aStringFormateable(d, maximumFractionDigits);
  const formatter = new Intl.NumberFormat(locale, {
    minimumFractionDigits,
    maximumFractionDigits,
  });
  return (formatter.format as IntlFormatWithString)(str);
}

/**
 * Formato de moneda SOLO para mostrar en pantalla (nunca para cálculos ni payloads).
 * Acepta {@link DecimalInput}. Vacío/nulo no muestra nada.
 * Pasa un string decimal redondeado directamente a `Intl.NumberFormat` sin pasar por `toNumber()`.
 */
export function formatoMoneda(valor: DecimalInput, moneda = 'VES', locale = 'es-VE'): string {
  if (valor === null || valor === undefined || valor === '') return '';
  const str = aStringFormateable(D(valor), 2);
  const formatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: moneda,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return (formatter.format as IntlFormatWithString)(str);
}
