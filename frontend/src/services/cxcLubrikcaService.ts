/**
 * Servicio del subproyecto CxC Lubrikca (perfil 'cobranza').
 *
 * La app aislada está montada en el backend bajo `/cxc-lubrikca/`. Aquí se
 * tipan TODOS los endpoints: CRUD de la configuración del motor, lectura de la
 * operación (pedidos, vinculaciones, bandeja, conciliaciones) y las acciones
 * POST (registrar/recalcular/sincronizar/proponer/confirmar/conciliar/revisar)
 * + el resumen de cartera.
 *
 * Los montos/porcentajes viajan como string decimal (R-CODE-4): el backend los
 * parsea con Decimal; nunca usamos `number`. Los porcentajes son fracciones
 * (0.030000 = 3 %).
 */
import { get, post, put, patch, del } from './api';
import { toList } from '../utils/api';

const BASE = '/cxc-lubrikca';

// ── Tipos: configuración del motor ──────────────────────────────────────────

export interface DescuentoMarcaCategoria {
  id: number;
  marca: string;
  categoria: string;
  tipo_descuento: string;
  /** Fracción decimal como string (0.030000 = 3 %). */
  porcentaje: string;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface DescuentoBCVCompleto {
  id: number;
  porcentaje: string;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PromocionPrimeraCompra {
  id: number;
  producto: string;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ReglaRecurrencia {
  id: number;
  condicion: string;
  tipo_beneficio: string;
  /** String decimal. */
  valor: string;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Feriado {
  id: number;
  fecha: string;
  descripcion: string;
  tipo: string;
  activo: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface MetodoPago {
  id: number;
  codigo: string;
  nombre: string;
  moneda: string;
  tipo_tasa: string;
  es_contado: boolean;
  activo: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ConfiguracionConciliacion {
  id: number;
  /** Tolerancias como string decimal. */
  tolerance_rounding: string;
  tolerance_red: string;
  created_at?: string;
  updated_at?: string;
}

// ── Tipos: operación (lectura) ──────────────────────────────────────────────

export interface LineaPedido {
  id: string;
  pedido: string;
  linea_id: string | null;
  producto: string;
  marca: string;
  categoria: string;
  cantidad: string;
  precio_unitario: string;
  cantidad_entregada: string;
  created_at?: string;
  updated_at?: string;
}

export interface BandejaFacturacion {
  id: string;
  pedido: string;
  lista_aplicada: string | null;
  precio_base_calculado: string;
  descuentos_detalle: unknown;
  total_descuentos: string;
  ncs_calculadas: string;
  total_motor: string;
  requiere_revision: boolean;
  candidata_a_cierre: boolean;
  estado: string;
  aprobado_por: number | null;
  calculado_en: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Pedido {
  id: string;
  so_id: string;
  cliente_externo_id: string | null;
  cliente_nombre: string | null;
  vendedor_email: string | null;
  fecha: string;
  fecha_entrega: string | null;
  monto_total: string;
  lista_precios: string | null;
  es_primera_compra: boolean;
  facturada: boolean;
  factura_id: string | null;
  monto_facturado: string;
  estado_entrega: string;
  entregada_completa: boolean;
  tiene_devolucion: boolean;
  lineas?: LineaPedido[];
  bandeja?: BandejaFacturacion | null;
  created_at?: string;
  updated_at?: string;
}

export interface PrecioLista {
  id: string;
  producto: string;
  lista: string;
  precio: string;
  created_at?: string;
  updated_at?: string;
}

export interface Pago {
  id: string;
  pago_id: string;
  cliente_externo_id: string | null;
  monto: string;
  moneda: string;
  metodo_pago: string;
  fecha_pago: string;
  vendedor_email: string | null;
  vinculado: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Vinculacion {
  id: string;
  pedido: string;
  pago: string;
  monto_aplicado: string;
  hora_pago_confirmada: string;
  tasa_bcv_aplicada: string | null;
  tasa_binance_aplicada: string | null;
  es_tasa_heredada: boolean;
  moneda_abono: string | null;
  tipo_tasa_abono: string | null;
  equiv_usd_bcv: string | null;
  equiv_usd_binance: string | null;
  equiv_ves_bcv: string | null;
  equiv_ves_binance: string | null;
  estado: string;
  confirmado_por: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface Conciliacion {
  id: string;
  pedido: string;
  total_motor: string;
  monto_facturado: string;
  ncs: string;
  diferencia: string;
  resultado: 'verde' | 'amarillo' | 'rojo' | string;
  revisado_por: number | null;
  conciliado_en: string | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Resumen de cartera (acción `conciliaciones/resumen`). Las claves coinciden
 * EXACTAMENTE con `services/conciliacion.py::resumen_cartera`.
 */
export interface ResumenCartera {
  por_resultado: { verde: number; amarillo: number; rojo: number };
  total_conciliados: number;
  total_facturados: number;
  facturados_sin_conciliar: number;
  pedidos_con_devolucion: number;
  cartera_atascada: number;
  bandejas_candidatas_sin_aprobar: number;
  diferencia_total: string;
}

// ── Payloads de acciones ─────────────────────────────────────────────────────

export interface RegistrarVinculacionPayload {
  pedido: string;
  pago: string;
  monto_aplicado: string;
  hora_pago_confirmada: string;
  es_tasa_heredada?: boolean;
}

export interface ConfirmarCierrePayload {
  aprobado: boolean;
  comentarios?: string;
}

export interface ConciliarPayload {
  pedido: string;
}

export interface SincronizarResultado {
  [recurso: string]: number;
}

// ── Helpers CRUD genéricos por recurso ───────────────────────────────────────

function crud<T>(recurso: string) {
  const path = `${BASE}/${recurso}/`;
  return {
    list: async (): Promise<T[]> => toList<T>(await get<unknown>(path)),
    create: (data: Partial<T>): Promise<T> =>
      post<T>(path, data as Record<string, unknown>),
    update: (id: number | string, data: Partial<T>): Promise<T> =>
      put<T>(`${path}${id}/`, data as Record<string, unknown>),
    patch: (id: number | string, data: Partial<T>): Promise<T> =>
      patch<T>(`${path}${id}/`, data as Record<string, unknown>),
    remove: (id: number | string): Promise<void> => del<void>(`${path}${id}/`),
  };
}

const descuentosMarca = crud<DescuentoMarcaCategoria>('descuentos-marca-categoria');
const descuentosBcv = crud<DescuentoBCVCompleto>('descuentos-bcv-completo');
const promociones = crud<PromocionPrimeraCompra>('promociones-primera-compra');
const recurrencia = crud<ReglaRecurrencia>('reglas-recurrencia');
const feriados = crud<Feriado>('feriados');
const metodosPago = crud<MetodoPago>('metodos-pago');
const configConciliacion = crud<ConfiguracionConciliacion>('config-conciliacion');

// ── Servicio ─────────────────────────────────────────────────────────────────

export const cxcLubrikcaService = {
  // Config: Descuentos Marca/Categoría
  listDescuentosMarca: descuentosMarca.list,
  crearDescuentoMarca: descuentosMarca.create,
  actualizarDescuentoMarca: descuentosMarca.update,
  patchDescuentoMarca: descuentosMarca.patch,
  eliminarDescuentoMarca: descuentosMarca.remove,

  // Config: Descuento BCV-Completo
  listDescuentosBcv: descuentosBcv.list,
  crearDescuentoBcv: descuentosBcv.create,
  actualizarDescuentoBcv: descuentosBcv.update,
  patchDescuentoBcv: descuentosBcv.patch,
  eliminarDescuentoBcv: descuentosBcv.remove,

  // Config: Promociones primera compra
  listPromociones: promociones.list,
  crearPromocion: promociones.create,
  actualizarPromocion: promociones.update,
  patchPromocion: promociones.patch,
  eliminarPromocion: promociones.remove,

  // Config: Reglas de recurrencia
  listReglasRecurrencia: recurrencia.list,
  crearReglaRecurrencia: recurrencia.create,
  actualizarReglaRecurrencia: recurrencia.update,
  patchReglaRecurrencia: recurrencia.patch,
  eliminarReglaRecurrencia: recurrencia.remove,

  // Config: Feriados
  listFeriados: feriados.list,
  crearFeriado: feriados.create,
  actualizarFeriado: feriados.update,
  patchFeriado: feriados.patch,
  eliminarFeriado: feriados.remove,

  // Config: Métodos de pago
  listMetodosPago: metodosPago.list,
  crearMetodoPago: metodosPago.create,
  actualizarMetodoPago: metodosPago.update,
  patchMetodoPago: metodosPago.patch,
  eliminarMetodoPago: metodosPago.remove,

  // Config: Tolerancias de conciliación
  listConfigConciliacion: configConciliacion.list,
  crearConfigConciliacion: configConciliacion.create,
  actualizarConfigConciliacion: configConciliacion.update,
  patchConfigConciliacion: configConciliacion.patch,
  eliminarConfigConciliacion: configConciliacion.remove,

  // ── Operación: Pedidos ─────────────────────────────────────────────────────
  listPedidos: async (): Promise<Pedido[]> =>
    toList<Pedido>(await get<unknown>(`${BASE}/pedidos/`)),
  recalcularPedido: (id: string): Promise<BandejaFacturacion> =>
    post<BandejaFacturacion>(`${BASE}/pedidos/${id}/recalcular/`, {}),
  sincronizarPedidos: (desde?: string): Promise<SincronizarResultado> =>
    post<SincronizarResultado>(`${BASE}/pedidos/sincronizar/`, desde ? { desde } : {}),

  // ── Operación: Líneas de pedido ────────────────────────────────────────────
  listLineasPedido: async (): Promise<LineaPedido[]> =>
    toList<LineaPedido>(await get<unknown>(`${BASE}/lineas-pedido/`)),

  // ── Operación: Precios de lista ────────────────────────────────────────────
  listPreciosLista: async (): Promise<PrecioLista[]> =>
    toList<PrecioLista>(await get<unknown>(`${BASE}/precios-lista/`)),

  // ── Operación: Pagos ───────────────────────────────────────────────────────
  listPagos: async (): Promise<Pago[]> =>
    toList<Pago>(await get<unknown>(`${BASE}/pagos/`)),

  // ── Operación: Vinculaciones ───────────────────────────────────────────────
  listVinculaciones: async (): Promise<Vinculacion[]> =>
    toList<Vinculacion>(await get<unknown>(`${BASE}/vinculaciones/`)),
  registrarVinculacion: (payload: RegistrarVinculacionPayload): Promise<Vinculacion> =>
    post<Vinculacion>(
      `${BASE}/vinculaciones/registrar/`,
      payload as unknown as Record<string, unknown>,
    ),

  // ── Operación: Bandeja de facturación ──────────────────────────────────────
  listBandeja: async (): Promise<BandejaFacturacion[]> =>
    toList<BandejaFacturacion>(await get<unknown>(`${BASE}/bandeja/`)),
  proponerCierre: (id: string): Promise<{ solicitud: string | null; detail?: string }> =>
    post<{ solicitud: string | null; detail?: string }>(
      `${BASE}/bandeja/${id}/proponer/`,
      {},
    ),
  confirmarCierre: (id: string, payload: ConfirmarCierrePayload): Promise<BandejaFacturacion> =>
    post<BandejaFacturacion>(
      `${BASE}/bandeja/${id}/confirmar/`,
      payload as unknown as Record<string, unknown>,
    ),

  // ── Operación: Conciliaciones ──────────────────────────────────────────────
  listConciliaciones: async (): Promise<Conciliacion[]> =>
    toList<Conciliacion>(await get<unknown>(`${BASE}/conciliaciones/`)),
  conciliar: (payload: ConciliarPayload): Promise<Conciliacion> =>
    post<Conciliacion>(
      `${BASE}/conciliaciones/conciliar/`,
      payload as unknown as Record<string, unknown>,
    ),
  revisarConciliacion: (id: string): Promise<Conciliacion> =>
    post<Conciliacion>(`${BASE}/conciliaciones/${id}/revisar/`, {}),
  getResumen: (): Promise<ResumenCartera> =>
    get<ResumenCartera>(`${BASE}/conciliaciones/resumen/`),
};
