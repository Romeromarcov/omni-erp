/**
 * Contrato del "sobre" de venta POS offline — ADR-012 / CTF-008 Nivel 2.
 *
 * Una venta creada sin red se arma como UNA unidad atómica identificada por un
 * `client_uuid` (UUIDv7/aleatorio) generado en el dispositivo. Pagos y detalles
 * viajan DENTRO del sobre (no referencian un `id_nota_venta` que aún no existe);
 * al reconectar, el outbox reenvía el sobre completo y el backend lo aplica
 * atómicamente e idempotente por `client_uuid`.
 *
 * Este módulo es SOLO el contrato + un constructor PURO (sin red, sin cálculo
 * fiscal: el servidor es la autoridad de IVA/total — `totales_cliente` es
 * provisional y solo sirve para el recibo y una verificación defensiva). No está
 * cableado al POS todavía; eso es un PR posterior (ver plan en ADR-012).
 *
 * Dinero SIEMPRE como string para no perder precisión (R-CODE-4).
 */
import { newIdempotencyKey } from './idempotency';

export interface VentaOfflineDetalle {
  id_producto: string;
  /** Cantidad como string (sin float). */
  cantidad: string;
  /** Precio unitario como string (sin float). */
  precio_unitario: string;
}

export interface VentaOfflinePago {
  id_metodo_pago: string;
  id_moneda: string;
  /** Monto como string (sin float). */
  monto: string;
}

export interface VentaOfflineTotales {
  subtotal: string;
  iva: string;
  total: string;
}

export interface VentaOfflineEnvelope {
  /** Identidad estable de la venta; clave de idempotencia de todo el sobre. */
  client_uuid: string;
  /** Marca de tiempo local (ISO con offset) en que se creó la venta offline. */
  fecha_local: string;
  id_sucursal: string;
  id_caja: string;
  id_cliente: string;
  detalles: VentaOfflineDetalle[];
  pagos: VentaOfflinePago[];
  /** Totales calculados en el cliente: PROVISIONALES (el servidor recalcula). */
  totales_cliente: VentaOfflineTotales;
}

export interface VentaOfflineInput {
  id_sucursal: string;
  id_caja: string;
  id_cliente: string;
  detalles: VentaOfflineDetalle[];
  pagos: VentaOfflinePago[];
  totales_cliente: VentaOfflineTotales;
}

export interface BuildOptions {
  /** Inyectable para tests/determinismo; por defecto genera uno nuevo. */
  clientUuid?: string;
  /** Inyectable para tests; por defecto `new Date()`. */
  now?: Date;
}

/**
 * Construye el sobre de venta offline a partir de los datos del POS.
 * Función pura: no toca red ni recalcula dinero. Lanza si la venta es inválida
 * (sin líneas o sin pagos), para no encolar sobres que el backend rechazaría.
 */
export function buildVentaOfflineEnvelope(
  input: VentaOfflineInput,
  opts: BuildOptions = {},
): VentaOfflineEnvelope {
  if (!input.detalles || input.detalles.length === 0) {
    throw new Error('La venta offline requiere al menos una línea.');
  }
  if (!input.pagos || input.pagos.length === 0) {
    throw new Error('La venta offline requiere al menos un pago.');
  }
  const now = opts.now ?? new Date();
  return {
    client_uuid: opts.clientUuid ?? newIdempotencyKey(),
    fecha_local: now.toISOString(),
    id_sucursal: input.id_sucursal,
    id_caja: input.id_caja,
    id_cliente: input.id_cliente,
    // Copias defensivas para que el sobre no comparta referencias mutables.
    detalles: input.detalles.map((d) => ({ ...d })),
    pagos: input.pagos.map((p) => ({ ...p })),
    totales_cliente: { ...input.totales_cliente },
  };
}
