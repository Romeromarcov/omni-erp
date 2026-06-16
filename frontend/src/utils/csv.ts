/**
 * Utilidades para exportar datos tabulares a CSV en el navegador.
 *
 * `toCsv` es puro (testeable); `downloadCsv` arma el blob y dispara la descarga.
 * Todos los valores se entrecomillan y se escapan las comillas dobles (RFC 4180).
 * Para dinero, pasar el valor como string crudo (R-CODE-4): nunca reformatear
 * vía Number()/float, que perdería precisión.
 */

type CsvCell = string | number | null | undefined;

function csvCell(value: CsvCell): string {
  return `"${(value ?? '').toString().replace(/"/g, '""')}"`;
}

/** Construye el contenido CSV (encabezado + filas). */
export function toCsv(headers: string[], rows: CsvCell[][]): string {
  return [headers, ...rows].map((r) => r.map(csvCell).join(',')).join('\n');
}

/** Construye y dispara la descarga de un CSV en el navegador. */
export function downloadCsv(filename: string, headers: string[], rows: CsvCell[][]): void {
  // BOM UTF-8 para que Excel respete acentos/símbolos.
  const csv = '﻿' + toCsv(headers, rows);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
