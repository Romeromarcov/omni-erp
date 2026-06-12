/**
 * Sub-fase 1.G — Devoluciones POS.
 *
 * Cliente del backend de devoluciones de una venta de mostrador:
 *   GET  /ventas/notas-venta/?numero_nota=...        — buscar la venta por número exacto
 *   GET  /ventas/notas-venta/{id}/devoluciones/      — estado devolvible por línea
 *   POST /ventas/notas-venta/{id}/devolver/          — registrar la devolución (idempotente)
 *
 * El POST lleva SIEMPRE `Idempotency-Key` (es dinero): un reintento con la
 * misma clave no duplica la devolución ni el egreso de caja.
 */
import { get, post } from './api';
import { IDEMPOTENCY_HEADER } from '../lib/idempotency';

export interface VentaDevolvible {
  id_nota_venta: string;
  numero_nota: string;
  estado: string;
  fecha_nota: string;
  fiscal: boolean;
  numero_factura: string | null;
}

export interface LineaDevolvible {
  id_detalle: string;
  id_producto: string;
  nombre_producto: string;
  sku: string;
  /** Montos/cantidades como string (R-CODE-4 — se operan con decimal.js). */
  precio_unitario: string;
  cantidad_vendida: string;
  cantidad_devuelta: string;
  cantidad_disponible: string;
}

export interface DevolucionResumen {
  id_devolucion: string;
  numero_devolucion: string;
  fecha_devolucion: string;
  motivo: string;
  estado: string;
  monto_total: string;
}

export interface EstadoDevolucionesVenta {
  venta: VentaDevolvible;
  lineas: LineaDevolvible[];
  devoluciones: DevolucionResumen[];
}

export interface DevolucionCreada {
  devolucion: {
    id_devolucion: string;
    numero_devolucion: string;
    fecha_devolucion: string;
    estado: string;
    motivo: string;
    monto_total: string;
  };
  nota_credito_fiscal: {
    id_nota_credito_fiscal: string;
    numero_nota_credito: string;
    numero_control: string;
    base_imponible: string;
    monto_iva: string;
    monto_total: string;
  } | null;
  nota_credito_venta: {
    id_nota_credito: string;
    numero_nota_credito: string;
    monto_total: string;
  } | null;
  pago_id: string;
  monto_reembolsado: string;
  caja_fisica: string;
  movimientos_inventario: number;
  asiento_id: string | null;
  asiento_iva_id: string | null;
}

interface NotaVentaBusqueda {
  id_nota_venta: string;
  numero_nota: string;
  estado: string;
}

/** Busca la venta original por número exacto (lector/teclado del POS). */
export async function buscarVentaPorNumero(numero: string): Promise<NotaVentaBusqueda | null> {
  const q = encodeURIComponent(numero.trim());
  const resp = await get<{ results: NotaVentaBusqueda[] } | NotaVentaBusqueda[]>(
    `/ventas/notas-venta/?numero_nota=${q}`,
  );
  const lista = Array.isArray(resp) ? resp : resp?.results ?? [];
  return lista[0] ?? null;
}

/** Estado devolvible de la venta: líneas con vendido/devuelto/disponible. */
export async function getEstadoDevoluciones(idNotaVenta: string): Promise<EstadoDevolucionesVenta> {
  return get<EstadoDevolucionesVenta>(`/ventas/notas-venta/${idNotaVenta}/devoluciones/`);
}

export interface DevolverPayload {
  almacen_id: string;
  id_metodo_pago: string;
  lineas: Array<{ id_detalle: string; cantidad: string }>;
  motivo?: string;
  observaciones?: string;
}

/** Registra la devolución (stock + NC + egreso de caja + asiento, atómico). */
export async function devolverVenta(
  idNotaVenta: string,
  payload: DevolverPayload,
  idempotencyKey: string,
): Promise<DevolucionCreada> {
  return post<DevolucionCreada>(
    `/ventas/notas-venta/${idNotaVenta}/devolver/`,
    payload as unknown as Record<string, unknown>,
    { headers: { [IDEMPOTENCY_HEADER]: idempotencyKey } },
  );
}
