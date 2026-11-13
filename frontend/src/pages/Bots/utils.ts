import type { Ingesta } from '../../services/botsIngestService';

export const texto = (v: unknown): string => (v === null || v === undefined ? '' : String(v));

/** Resumen de una línea del borrador: «Taller X · 100 USD». */
export function resumenIngesta(i: Pick<Ingesta, 'payload'>): string {
  const p = i.payload;
  const quien = texto(p.cliente) || texto(p.nombre) || texto(p.proveedor) || texto(p.rif);
  const monto = p.monto !== undefined && p.monto !== null ? ` · ${texto(p.monto)} ${texto(p.moneda)}`.trimEnd() : '';
  return `${quien || '—'}${monto}`;
}
