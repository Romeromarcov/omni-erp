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
 * Construye un Decimal de forma segura a partir de string | number | Decimal | null | undefined.
 *
 * Acepta `unknown` porque con zod 4 los campos `z.coerce` tienen entrada tipada `unknown`
 * (los valores de formulario). El comportamiento no cambia: cualquier valor que decimal.js
 * no pueda interpretar cae en el `catch` y se trata como 0; no se convierte vía `Number()`,
 * así que no se pierde precisión decimal.
 */
export const D = (x: unknown): Decimal => {
  if (x === null || x === undefined || x === '') return new Decimal(0);
  try {
    const d = new Decimal(x as Decimal.Value);
    return d.isNaN() ? new Decimal(0) : d;
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
  cantidad: string | number | null | undefined,
  precio: string | number | null | undefined,
  descuentoPorcentaje?: string | number | null | undefined,
): Decimal {
  const bruto = D(cantidad).times(D(precio));
  const desc = D(descuentoPorcentaje).dividedBy(100);
  return bruto.minus(bruto.times(desc));
}

/** Formatea un valor monetario a un string con decimales fijos (por defecto 2). */
export function toFixedStr(value: Decimal | string | number, decimals = 2): string {
  return (value instanceof Decimal ? value : D(value)).toFixed(decimals);
}

/**
 * Formato de moneda SOLO para mostrar en pantalla (nunca para cálculos ni payloads).
 * Acepta el string decimal que devuelve la API. Vacío/nulo no muestra nada.
 */
export function formatoMoneda(valor: DecimalInput, moneda = 'VES', locale = 'es-VE'): string {
  if (valor === null || valor === undefined || valor === '') return '';
  return D(valor).toNumber().toLocaleString(locale, { style: 'currency', currency: moneda });
}
