// Utilidad para validación fuzzy de duplicados usando RapidFuzz
import Fuse from 'fuse.js';
import type { Moneda } from '../pages/Finanzas/Monedas/MonedaListPage';
// No hay export de MetodoPago, así que se define aquí
export interface MetodoPago {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
  activo: boolean;
  es_generico?: boolean;
  es_publico?: boolean;
  empresa?: string | null;
}

export function isSimilar(a: string, b: string, threshold = 65): boolean {
  if (!a || !b) return false;
  // Usar Fuse internamente para comparar dos strings
  const fuse = new Fuse([b], { includeScore: true, threshold: 1, keys: [] });
  const result = fuse.search(a.trim());
  if (result.length === 0) return false;
  // Score de Fuse: 0 = exacto, 1 = nada que ver. Convertimos a porcentaje similar a rapidfuzz
  const score = result[0].score ?? 1;
  const similarity = Math.round((1 - score) * 100);
  return similarity >= threshold;
}

export function findSimilarMoneda(moneda: Partial<Moneda>, lista: Moneda[], threshold = 65): Moneda | undefined {
  return lista.find(m =>
    ((moneda.nombre && isSimilar(moneda.nombre, m.nombre, threshold)) ||
     (moneda.codigo_iso && isSimilar(moneda.codigo_iso, m.codigo_iso, threshold))) &&
    moneda.tipo_moneda === m.tipo_moneda
  );
}

export function findSimilarMetodoPago(metodo: Partial<MetodoPago>, lista: MetodoPago[], threshold = 65): MetodoPago | undefined {
  return lista.find(m =>
    (metodo.nombre_metodo && isSimilar(metodo.nombre_metodo, m.nombre_metodo, threshold)) &&
    metodo.tipo_metodo === m.tipo_metodo
  );
}
