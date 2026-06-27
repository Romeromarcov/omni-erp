import { get, patch } from './api';

/**
 * Item de /finanzas/metodos-pago-empresa-activas/.
 *
 * OJO: el serializer del backend (MetodoPagoEmpresaActivaSerializer) expone:
 *   - `id`           = PK de la fila de activación (NO del método de pago),
 *   - `metodo_pago`  = MetodoPago.id_metodo_pago (el valor que consumen los FKs),
 *   - `nombre`       = metodo_pago.nombre_metodo.
 * Los campos legados (`nombre_metodo`, `monedas`) se mantienen opcionales sólo por
 * compatibilidad con consumidores antiguos (POS); el código nuevo debe usar
 * `metodo_pago` (valor del FK) y `nombre` (etiqueta).
 */
export interface MetodoPagoEmpresaActiva {
  /** PK de la fila de activación (MetodoPagoEmpresaActiva), no del método. */
  id: string;
  /** PK del método de pago subyacente (MetodoPago.id_metodo_pago) — el valor que consumen los FKs. */
  metodo_pago: string;
  /** Nombre del método de pago (source = metodo_pago.nombre_metodo). */
  nombre: string;
  activa: boolean;
  // Legados consumidos por el POS (components/Pedidos): el serializer real NO los
  // devuelve, pero se declaran requeridos para no romper a esos consumidores. Los
  // seeds/mocks que apuntan al POS deben proveerlos; el código nuevo usa `metodo_pago`/`nombre`.
  nombre_metodo: string;
  monedas: string[];
  [key: string]: unknown;
}

export async function fetchMetodosPagoEmpresaActivos(empresa: string): Promise<MetodoPagoEmpresaActiva[]> {
  const data = await get<MetodoPagoEmpresaActiva[] | { results: MetodoPagoEmpresaActiva[] }>(
    `/finanzas/metodos-pago-empresa-activas/?empresa=${empresa}`
  );
  if (Array.isArray(data)) return data;
  if (data && 'results' in data && Array.isArray(data.results)) return data.results;
  return [];
}

export async function updateMonedasMetodoPagoEmpresaActiva(id: string, monedas: string[]): Promise<unknown> {
  return patch(`/finanzas/metodos-pago-empresa-activas/${id}/`, { monedas });
}
