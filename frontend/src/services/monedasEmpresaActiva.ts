import { get } from './api';

/**
 * Item de /finanzas/monedas-empresa-activas/.
 *
 * OJO: el serializer del backend (MonedaEmpresaActivaSerializer) expone la moneda
 * subyacente como `moneda` (= Moneda.id_moneda) y sus etiquetas como
 * `moneda_codigo_iso`/`moneda_nombre` — NO como `id_moneda`/`codigo_iso`/`nombre`.
 * Los campos legados (`id_moneda`, `codigo_iso`, `nombre`) se mantienen opcionales
 * sólo por compatibilidad con consumidores antiguos (POS); el código nuevo debe
 * usar `moneda` / `moneda_codigo_iso` / `moneda_nombre`.
 */
export interface MonedaEmpresaActiva {
  /** PK de la fila de activación (MonedaEmpresaActiva), no de la moneda. */
  id: string;
  /** PK de la moneda subyacente (Moneda.id_moneda) — el valor que consumen los FKs. */
  moneda: string;
  moneda_nombre: string;
  moneda_codigo_iso: string;
  activa: boolean;
  // Legados consumidos por el POS (components/Pedidos): el serializer real NO los
  // devuelve, pero se declaran requeridos para no romper a esos consumidores. Los
  // seeds/mocks que apuntan al POS deben proveerlos; el código nuevo usa los `moneda*`.
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
  [key: string]: unknown;
}

export async function fetchMonedasEmpresaActivas(empresa: string): Promise<MonedaEmpresaActiva[]> {
  const data = await get<MonedaEmpresaActiva[] | { results: MonedaEmpresaActiva[] }>(
    `/finanzas/monedas-empresa-activas/?empresa=${empresa}`
  );
  if (Array.isArray(data)) return data;
  if (data && 'results' in data && Array.isArray(data.results)) return data.results;
  return [];
}
