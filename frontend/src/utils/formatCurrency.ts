import { D, type DecimalInput, formatoMoneda } from '../lib/decimal';

/**
 * Formatea un valor monetario usando aritmética Decimal (sin `parseFloat` / float).
 * Ante `null`, `undefined`, vacío o texto no numérico formatea `0.00` de forma segura.
 */
export function formatCurrency(
  value: DecimalInput,
  currency: string = 'USD',
  locale: string = 'en-US',
): string {
  const monto = value === null || value === undefined || value === '' ? D(0) : value;
  return formatoMoneda(monto, currency, locale);
}
