import { API_URL, get, post } from './api';
import { IDEMPOTENCY_HEADER, newIdempotencyKey } from '../lib/idempotency';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Tipos compartidos ────────────────────────────────────────────────────────

export interface EquivalenciasTrimonetarias {
  base?: string | null;
  base_iso?: string | null;
  pais_fiscal?: string | null;
  pais_fiscal_iso?: string | null;
  referencia?: string | null;
  referencia_iso?: string | null;
  monto_origen?: string | null;
}

export interface MonedaOpcion {
  id_moneda: string;
  codigo_iso: string;
  nombre: string;
  simbolo: string;
}

export interface MetodoPagoOpcion {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
}

// ── Portal Vendedores SFA ────────────────────────────────────────────────────

export interface CarteraClienteItem {
  id_cliente: string;
  razon_social: string;
  rif: string;
  tipo_cliente: string;
  limite_credito: string;
  saldo_pendiente: string;
  cuentas_vencidas: number;
  bloquear_por_mora: boolean;
}

export interface CatalogoProductoPortalItem {
  id_producto: string;
  sku: string;
  codigo_barras: string;
  nombre_producto: string;
  stock_disponible: string;
  precio: string;
  moneda_precio: string;
  equivalencias_trimonetarias: EquivalenciasTrimonetarias;
}

export type ResultadoVisitaGPS =
  | 'EFECTIVA'
  | 'COBRANZA'
  | 'SIN_STOCK'
  | 'CERRADO'
  | 'REPROGRAMADA';

export interface CheckinVendedorPayload {
  id_cliente: string;
  latitud: string;
  longitud: string;
  precision_m?: string | null;
  resultado?: ResultadoVisitaGPS;
  notas?: string;
}

export interface CheckinVendedorResponse {
  id_visita: string;
  fecha_visita: string;
  distancia_cliente_m: string | null;
  resultado: string;
}

export interface LineaPedidoPortalPayload {
  id_producto: string;
  cantidad: string;
}

export interface PedidoVendedorPayload {
  id_cliente: string;
  observaciones?: string;
  referencia_externa?: string;
  lineas: LineaPedidoPortalPayload[];
}

export interface PedidoPortalResponse {
  id_pedido: string;
  numero_pedido: string;
  estado: string;
  total_estimado: string;
}

export interface CobroVendedorPayload {
  id_cliente: string;
  monto: string;
  id_moneda: string;
  id_metodo_pago: string;
  tasa?: string;
  referencia?: string;
  comprobante_url?: string;
  observaciones?: string;
}

export interface CobroVendedorResponse {
  id_pago_portal: string;
  estado: string;
  monto: string;
  moneda: string;
}

export interface EsquemaComisionPortal {
  id_esquema_comision: string;
  porcentaje_base: string;
  meta_mensual_monto: string;
  bono_meta_porcentaje: string;
  modalidad_devengo: string;
}

export interface ComisionRecientePortal {
  id_comision_venta: string;
  nota_venta: string;
  monto: string;
  estado: string;
  origen_devengo: string;
  fecha_devengo: string;
}

export interface MetasComisionesResponse {
  empresa_id: string;
  total_devengado: string;
  total_liquidado: string;
  esquemas: EsquemaComisionPortal[];
  comisiones: ComisionRecientePortal[];
}

// ── Portal Clientes Self-Service (OTP) ───────────────────────────────────────

export type CanalOTPPortal = 'WHATSAPP' | 'EMAIL';

export interface SolicitarOTPPayload {
  rif: string;
  id_empresa?: string | null;
  canal?: CanalOTPPortal;
  destino?: string;
}

export interface SolicitarOTPResponse {
  id_token?: string;
  canal?: string;
  destino_enmascarado?: string;
  expira_en?: string;
  detail?: string;
}

export interface VerificarOTPPayload {
  id_token?: string | null;
  rif: string;
  codigo: string;
  id_empresa?: string | null;
}

export interface PortalClienteIdentidad {
  id_cliente: string;
  razon_social: string;
  rif: string;
  empresa_id: string;
  empresa_nombre: string;
}

export interface PortalClienteSession {
  session_token: string;
  expira_en: string;
  cliente: PortalClienteIdentidad;
}

export interface FacturaPortalResumen {
  id_factura: string;
  numero_factura: string;
  numero_control: string;
  fecha_emision: string;
  monto_total: string;
  moneda: string;
  estado: string;
  pdf_url: string;
}

export interface NotaVentaPortalResumen {
  id_nota_venta: string;
  numero_nota: string;
  fecha_nota: string;
  estado: string;
  ambito: string;
  pdf_url: string;
}

export interface PagoPortalResumen {
  id_pago_portal: string;
  monto: string;
  moneda: string;
  referencia: string;
  estado: string;
  fecha_creacion: string;
}

export interface PortalClienteResumenResponse {
  cliente: {
    id_cliente: string;
    razon_social: string;
    rif: string;
  };
  estado_cuenta_trimonetario: {
    saldo_pendiente: string;
    equivalencias: EquivalenciasTrimonetarias;
    documentos_pendientes: number;
    cuentas_vencidas: number;
  };
  facturas_fiscales: FacturaPortalResumen[];
  notas_venta: NotaVentaPortalResumen[];
  pagos_reportados: PagoPortalResumen[];
}

export interface PagoPortalClientePayload {
  monto: string;
  id_moneda: string;
  id_metodo_pago: string;
  tasa?: string;
  referencia?: string;
  comprobante_url?: string;
  texto_comprobante_ocr?: string;
  observaciones?: string;
}

export interface PagoPortalClienteResponse {
  id_pago_portal: string;
  estado: string;
  monto: string;
  referencia: string;
  ocr_extraido: Record<string, unknown>;
}

export interface PedidoPortalClientePayload {
  observaciones?: string;
  lineas: LineaPedidoPortalPayload[];
}

export interface TrackingDespachoClienteItem {
  id_despacho: string;
  numero_despacho: string;
  estado_despacho: string;
  fecha_despacho: string;
  token_tracking: string | null;
  parada_estado: string | null;
  eta_estimada: string | null;
  tracking_url_publico: string | null;
}

export interface PortalClienteTrackingResponse {
  despachos: TrackingDespachoClienteItem[];
}

// ── Portal Conductores TMS ───────────────────────────────────────────────────

export interface ParadaPortalConductor {
  id_parada: string;
  secuencia: number;
  estado: string;
  despacho_numero: string;
  direccion_texto: string;
  latitud: string | null;
  longitud: string | null;
  eta_estimada: string | null;
  waze_url: string | null;
  google_maps_url: string | null;
}

export interface RutaPortalConductor {
  id_ruta: string;
  codigo: string;
  estado: string;
  fecha_ruta: string;
  vehiculo_placa: string | null;
  paradas: ParadaPortalConductor[];
}

export interface EscanearBultoPayload {
  codigo_bulto: string;
  observacion?: string;
}

export interface EscanearBultoResponse {
  id_parada: string;
  codigo_bulto: string;
  verificado: boolean;
}

export interface CobroEnSitioPayload {
  monto: string;
  id_metodo_pago: string;
  id_moneda: string;
  tasa?: string;
  referencia?: string;
}

export interface RegistrarEPODPayload {
  resultado: 'ENTREGADA' | 'ENTREGA_PARCIAL' | 'RECHAZADA';
  receptor_nombre?: string;
  receptor_cedula?: string;
  firma_base64?: string;
  foto_url?: string;
  latitud?: string | null;
  longitud?: string | null;
  observaciones?: string;
  motivo_rechazo?: string;
  cobro?: CobroEnSitioPayload | null;
}

export interface RegistrarEPODResponse {
  parada: Record<string, unknown>;
  despacho_estado: string;
  pago_id: string | null;
  ruta_completada: boolean;
}

// ── Helpers URL y sesión aislada del Portal de Clientes ──────────────────────

const PORTAL_CLIENTE_SESSION_KEY = 'omni_portal_cliente_session_v1';

/**
 * Valida esquemas seguros (`http:` / `https:`) antes de exponer enlaces externos
 * o de descarga desde respuestas del backend. Si la ruta inicia con `/api/`, la
 * resuelve contra el origen base configurado en `API_URL`.
 */
export function safeExternalUrl(rawUrl: string | null | undefined): string | undefined {
  const clean = (rawUrl ?? '').trim();
  if (!clean || /[\r\n\0]/.test(clean)) return undefined;
  try {
    if (clean.startsWith('/api/')) {
      const origin = API_URL.replace(/\/api\/?$/, '');
      const full = new URL(clean, origin.startsWith('http') ? origin : 'http://localhost:8000');
      return full.protocol === 'http:' || full.protocol === 'https:' ? full.toString() : undefined;
    }
    const parsed = new URL(clean);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.toString() : undefined;
  } catch {
    return undefined;
  }
}

export function getPortalClienteSession(): PortalClienteSession | null {
  try {
    const raw = window.sessionStorage.getItem(PORTAL_CLIENTE_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PortalClienteSession;
    return parsed?.session_token ? parsed : null;
  } catch {
    return null;
  }
}

export function setPortalClienteSession(session: PortalClienteSession): void {
  try {
    window.sessionStorage.setItem(PORTAL_CLIENTE_SESSION_KEY, JSON.stringify(session));
  } catch {
    /* sessionStorage puede estar restringido en modo privado */
  }
}

export function clearPortalClienteSession(): void {
  try {
    window.sessionStorage.removeItem(PORTAL_CLIENTE_SESSION_KEY);
  } catch {
    /* noop */
  }
}

function buildQuery(params: Record<string, string | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v && v.trim()) sp.set(k, v.trim());
  }
  const q = sp.toString();
  return q ? `?${q}` : '';
}

async function portalClienteRequest<T>(
  endpoint: string,
  options: {
    method?: 'GET' | 'POST';
    token?: string;
    body?: Record<string, unknown>;
    idempotent?: boolean;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (options.token) {
    headers['X-Portal-Cliente-Token'] = options.token;
  }
  if (options.body) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.idempotent) {
    headers['Idempotency-Key'] = newIdempotencyKey();
  }

  const res = await fetch(`${API_URL}${endpoint}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const msg =
      (typeof data.detail === 'string' && data.detail) ||
      (typeof data.error === 'string' && data.error) ||
      Object.values(data)
        .flat()
        .find((v) => typeof v === 'string') ||
      `Error ${res.status}`;
    const err = new Error(String(msg)) as Error & { status?: number; data?: unknown };
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data as T;
}

// ── Servicios exportados ─────────────────────────────────────────────────────

export const portalVendedorService = {
  getCartera: (empresaId?: string, todos?: boolean) =>
    get<{ empresa_id: string; clientes: CarteraClienteItem[] }>(
      `/ventas/portal-vendedor/cartera/${buildQuery({
        empresa: empresaId,
        todos: todos ? '1' : undefined,
      })}`,
    ),

  getCatalogo: (q?: string, empresaId?: string) =>
    get<{ empresa_id: string; productos: CatalogoProductoPortalItem[] }>(
      `/ventas/portal-vendedor/catalogo/${buildQuery({ q, empresa: empresaId })}`,
    ),

  registrarCheckin: (payload: CheckinVendedorPayload) =>
    post<CheckinVendedorResponse>(
      '/ventas/portal-vendedor/checkin/',
      payload as unknown as Record<string, unknown>,
      { headers: { [IDEMPOTENCY_HEADER]: newIdempotencyKey() } },
    ),

  crearPedido: (payload: PedidoVendedorPayload) =>
    post<PedidoPortalResponse>(
      '/ventas/portal-vendedor/pedidos/',
      payload as unknown as Record<string, unknown>,
      { headers: { [IDEMPOTENCY_HEADER]: newIdempotencyKey() } },
    ),

  reportarCobro: (payload: CobroVendedorPayload) =>
    post<CobroVendedorResponse>(
      '/ventas/portal-vendedor/cobros/',
      payload as unknown as Record<string, unknown>,
      { headers: { [IDEMPOTENCY_HEADER]: newIdempotencyKey() } },
    ),

  getMetasComisiones: (empresaId?: string) =>
    get<MetasComisionesResponse>(
      `/ventas/portal-vendedor/metas-comisiones/${buildQuery({ empresa: empresaId })}`,
    ),

  getMonedasCatalogo: async (): Promise<MonedaOpcion[]> => {
    const res = await get<MonedaOpcion[] | PaginatedResponse<MonedaOpcion>>('/finanzas/monedas/');
    return toList(res);
  },

  getMetodosPagoCatalogo: async (): Promise<MetodoPagoOpcion[]> => {
    const res = await get<MetodoPagoOpcion[] | PaginatedResponse<MetodoPagoOpcion>>(
      '/finanzas/metodos-pago/',
    );
    return toList(res);
  },
};

export const portalClienteService = {
  solicitarOtp: (payload: SolicitarOTPPayload) =>
    portalClienteRequest<SolicitarOTPResponse>('/ventas/portal-cliente/auth/solicitar-otp/', {
      method: 'POST',
      body: payload as unknown as Record<string, unknown>,
    }),

  verificarOtp: (payload: VerificarOTPPayload) =>
    portalClienteRequest<PortalClienteSession>('/ventas/portal-cliente/auth/verificar-otp/', {
      method: 'POST',
      body: payload as unknown as Record<string, unknown>,
    }),

  getResumen: (token: string) =>
    portalClienteRequest<PortalClienteResumenResponse>('/ventas/portal-cliente/resumen/', {
      method: 'GET',
      token,
    }),

  reportarPago: (token: string, payload: PagoPortalClientePayload) =>
    portalClienteRequest<PagoPortalClienteResponse>('/ventas/portal-cliente/pagos/', {
      method: 'POST',
      token,
      body: payload as unknown as Record<string, unknown>,
      idempotent: true,
    }),

  crearPedido: (token: string, payload: PedidoPortalClientePayload) =>
    portalClienteRequest<PedidoPortalResponse>('/ventas/portal-cliente/pedidos/', {
      method: 'POST',
      token,
      body: payload as unknown as Record<string, unknown>,
      idempotent: true,
    }),

  getTracking: (token: string) =>
    portalClienteRequest<PortalClienteTrackingResponse>('/ventas/portal-cliente/tracking/', {
      method: 'GET',
      token,
    }),
};

export const portalConductorService = {
  getMisRutas: (params?: { conductor?: string; empresa?: string }) =>
    get<{ empresa_id: string; rutas: RutaPortalConductor[] }>(
      `/despacho/portal-conductor/mis-rutas/${buildQuery({
        conductor: params?.conductor,
        empresa: params?.empresa,
      })}`,
    ),

  escanearBulto: (paradaId: string, payload: EscanearBultoPayload) =>
    post<EscanearBultoResponse>(
      `/despacho/portal-conductor/paradas/${paradaId}/escanear-bulto/`,
      payload as unknown as Record<string, unknown>,
      { headers: { [IDEMPOTENCY_HEADER]: newIdempotencyKey() } },
    ),

  registrarEpod: (paradaId: string, payload: RegistrarEPODPayload) =>
    post<RegistrarEPODResponse>(
      `/despacho/portal-conductor/paradas/${paradaId}/epod/`,
      payload as unknown as Record<string, unknown>,
      { headers: { [IDEMPOTENCY_HEADER]: newIdempotencyKey() } },
    ),
};
