import { ETIQUETAS_BOT, type Ingesta } from '../../services/botsIngestService';

export const texto = (v: unknown): string => (v === null || v === undefined ? '' : String(v));

/** Resumen de una línea del borrador: «Taller X · 100 USD». */
export function resumenIngesta(i: Pick<Ingesta, 'payload'>): string {
  const p = i.payload;
  const quien =
    texto(p.cliente) ||
    texto(p.nombre) ||
    texto(p.proveedor) ||
    texto(p.titulo) ||
    texto(p.rif);
  const valorMonto = p.monto !== undefined && p.monto !== null ? p.monto : p.monto_total;
  const monto =
    valorMonto !== undefined && valorMonto !== null
      ? ` · ${texto(valorMonto)} ${texto(p.moneda)}`.trimEnd()
      : '';
  return `${quien || '—'}${monto}`;
}

export function etiquetaBot(codigo: string): string {
  return ETIQUETAS_BOT.get(codigo) ?? codigo;
}

export function formatearHaceSegundos(segundos: number | null): string {
  if (segundos === null || segundos < 0) return 'Sin latidos';
  if (segundos < 60) return `Hace ${segundos} s`;
  const min = Math.floor(segundos / 60);
  if (min < 60) return `Hace ${min} min`;
  const horas = Math.floor(min / 60);
  if (horas < 24) return `Hace ${horas} h`;
  return `Hace ${Math.floor(horas / 24)} d`;
}
