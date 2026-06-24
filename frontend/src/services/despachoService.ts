import { get, post, fetchBlob, API_URL } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────

/**
 * Estados de la máquina de estados del Despacho (espejo del modelo backend):
 *   PENDIENTE → EN_RUTA   → ENTREGADO
 *   PENDIENTE → CANCELADO
 *   EN_RUTA   → DEVUELTO
 * ENTREGADO / DEVUELTO / CANCELADO son terminales.
 */
export type EstadoDespacho =
  | 'PENDIENTE'
  | 'EN_RUTA'
  | 'ENTREGADO'
  | 'DEVUELTO'
  | 'CANCELADO';

/**
 * Transiciones válidas por estado actual — réplica exacta de
 * `Despacho.TRANSICIONES` del backend. La UI usa esto para habilitar SOLO los
 * botones de transición permitidos en el estado vigente (defensa en
 * profundidad: el backend re-valida).
 */
export const TRANSICIONES_DESPACHO: Record<EstadoDespacho, readonly EstadoDespacho[]> = {
  PENDIENTE: ['EN_RUTA', 'CANCELADO'],
  EN_RUTA: ['ENTREGADO', 'DEVUELTO'],
  ENTREGADO: [],
  DEVUELTO: [],
  CANCELADO: [],
};

/** True si la máquina de estados permite pasar `actual` → `destino`. */
export function puedeTransicionar(actual: EstadoDespacho, destino: EstadoDespacho): boolean {
  // eslint-disable-next-line security/detect-object-injection -- FP: `actual` está restringido al union EstadoDespacho (Record exhaustivo verificado por TS); el `?? false` cubre estados fuera del union.
  return TRANSICIONES_DESPACHO[actual]?.includes(destino) ?? false;
}

/** Línea de despacho (DetalleDespacho). Solo lectura por API. */
export interface DetalleDespacho {
  id_detalle_despacho: string;
  id_despacho: string;
  id_producto: string;
  nombre_producto?: string;
  cantidad_despachada: string;
  id_unidad_medida: string;
  unidad_medida?: string;
  lote?: string | null;
  fecha_vencimiento?: string | null;
  observaciones?: string | null;
}

/**
 * Despacho (encabezado). Los timestamps de transición y el estado son
 * read-only en el serializer: el estado solo cambia vía las acciones de
 * transición (máquina de estados). Las cantidades viajan como string para no
 * perder precisión del DecimalField (R-CODE-4).
 */
export interface Despacho {
  id_despacho: string;
  id_empresa: string;
  numero_despacho: string;
  id_nota_venta?: string | null;
  numero_nota_venta?: string | null;
  id_pedido?: string | null;
  fecha_despacho: string;
  id_almacen_origen: string;
  nombre_almacen?: string | null;
  direccion_destino: string;
  id_transportista?: number | null;
  estado_despacho: EstadoDespacho;
  fecha_entrega_estimada?: string | null;
  fecha_en_ruta?: string | null;
  fecha_entrega_real?: string | null;
  fecha_devolucion?: string | null;
  fecha_cancelacion?: string | null;
  observaciones?: string | null;
  referencia_externa?: string | null;
  detalles?: DetalleDespacho[];
  activo?: boolean;
  fecha_creacion?: string;
  fecha_actualizacion?: string;
}

/** Línea solicitada al crear un despacho parcial desde la venta. */
export interface LineaDespachoInput {
  id_producto: string;
  cantidad: string;
}

/**
 * Payload de POST /despachos/desde-nota-venta/. Whitelist explícita de campos
 * (CTF-005). Sin `lineas` se despacha todo lo pendiente de la nota.
 */
export interface DespachoDesdeNotaVentaPayload {
  id_nota_venta: string;
  almacen_id: string;
  direccion_entrega: string;
  id_transportista?: number | null;
  fecha_entrega_estimada?: string | null;
  observaciones?: string;
  lineas?: LineaDespachoInput[];
}

const BASE = '/despacho';

// ── Despachos (CRUD parcial + transiciones de estado + PDF) ───────────────────

export const despachoService = {
  getAll: async (params?: {
    empresa?: string;
    estado?: string;
    transportista?: string;
    notaVenta?: string;
  }): Promise<Despacho[]> => {
    const qs = new URLSearchParams();
    if (params?.empresa) qs.set('empresa', params.empresa);
    if (params?.estado) qs.set('estado', params.estado);
    if (params?.transportista) qs.set('id_transportista', params.transportista);
    if (params?.notaVenta) qs.set('id_nota_venta', params.notaVenta);
    const query = qs.toString();
    const response = await get<PaginatedResponse<Despacho> | Despacho[]>(
      `${BASE}/despachos/${query ? '?' + query : ''}`,
    );
    return toList<Despacho>(response);
  },

  getById: async (id: string): Promise<Despacho> => get<Despacho>(`${BASE}/despachos/${id}/`),

  /** Crea un despacho PENDIENTE desde una NotaVenta ENTREGADA/FACTURADA. */
  desdeNotaVenta: async (payload: DespachoDesdeNotaVentaPayload): Promise<Despacho> =>
    post<Despacho>(
      `${BASE}/despachos/desde-nota-venta/`,
      payload as unknown as Record<string, unknown>,
    ),

  /** PENDIENTE → EN_RUTA. Body opcional: {id_transportista}. */
  iniciarRuta: async (id: string, transportistaId?: number | null): Promise<Despacho> =>
    post<Despacho>(
      `${BASE}/despachos/${id}/iniciar-ruta/`,
      transportistaId ? { id_transportista: transportistaId } : {},
    ),

  /** EN_RUTA → ENTREGADO. Receptor obligatorio; documento/firma opcionales. */
  entregar: async (
    id: string,
    datos: { receptor: string; documento_receptor?: string; firma_base64?: string },
  ): Promise<Despacho> => {
    const body: Record<string, unknown> = { receptor: datos.receptor };
    if (datos.documento_receptor) body.documento_receptor = datos.documento_receptor;
    if (datos.firma_base64) body.firma_base64 = datos.firma_base64;
    return post<Despacho>(`${BASE}/despachos/${id}/entregar/`, body);
  },

  /** EN_RUTA → DEVUELTO. Motivo obligatorio. */
  devolver: async (id: string, motivo: string): Promise<Despacho> =>
    post<Despacho>(`${BASE}/despachos/${id}/devolver/`, { motivo }),

  /** PENDIENTE → CANCELADO. Motivo obligatorio. */
  cancelar: async (id: string, motivo: string): Promise<Despacho> =>
    post<Despacho>(`${BASE}/despachos/${id}/cancelar/`, { motivo }),

  /** URL absoluta del PDF de la nota de entrega (para abrir en una pestaña). */
  pdfUrl: (id: string): string => `${API_URL}${BASE}/despachos/${id}/pdf/`,

  /** Descarga el PDF de la nota de entrega disparando el guardado en el navegador. */
  descargarPdf: async (id: string, numeroDespacho?: string): Promise<void> => {
    const blob = await fetchBlob(`${BASE}/despachos/${id}/pdf/`, {
      headers: { Accept: 'application/pdf' },
    });
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl;
    a.download = `nota_entrega_${numeroDespacho ?? id}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(objUrl);
  },
};

// ── Detalles de despacho (líneas; solo lectura) ───────────────────────────────

export const detalleDespachoService = {
  getAll: async (params?: { despacho?: string }): Promise<DetalleDespacho[]> => {
    const qs = params?.despacho ? `?id_despacho=${encodeURIComponent(params.despacho)}` : '';
    const response = await get<PaginatedResponse<DetalleDespacho> | DetalleDespacho[]>(
      `${BASE}/detalles-despacho/${qs}`,
    );
    const lista = toList<DetalleDespacho>(response);
    return params?.despacho ? lista.filter((d) => d.id_despacho === params.despacho) : lista;
  },
};
