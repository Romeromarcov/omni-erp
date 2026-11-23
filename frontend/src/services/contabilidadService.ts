/**
 * Servicio de Contabilidad (workstream F + Ola B1) — plan de cuentas,
 * diarios contables, períodos/cierre, libro de asientos, reversión y mapeos.
 *
 * Endpoints del backend (`apps/contabilidad`):
 *   GET/POST /contabilidad/plan-cuentas/
 *   GET/POST /contabilidad/diarios/  ·  PATCH /{id}/
 *   GET      /contabilidad/periodos-contables/
 *   POST     /contabilidad/periodos-contables/cerrar/
 *   POST     /contabilidad/periodos-contables/{id}/reabrir/
 *   POST     /contabilidad/periodos-contables/cerrar-ejercicio/
 *   GET      /contabilidad/asientos-contables/?estado_asiento=&fecha_asiento=
 *   GET      /contabilidad/asientos-contables/{id}/
 *   POST     /contabilidad/asientos-contables/{id}/revertir/
 *   GET      /contabilidad/detalles-asiento/?id_asiento=
 *   GET/POST /contabilidad/mapeos-contables/  ·  PATCH /{id}/
 *   GET      /contabilidad/mapeos-contables/tipos-asiento/
 *   GET      /contabilidad/reportes/balance-comprobacion/
 *   GET      /contabilidad/reportes/estado-resultados/
 *   GET      /contabilidad/reportes/balance-general/
 *   GET      /contabilidad/reportes/libro-mayor-auxiliar/
 *
 * Todos los montos viajan como STRING decimal (R-CODE-4) — nunca number.
 */
import { del, fetchBlob, get, patch, post } from './api';
import { toList, type PaginatedResponse } from '../utils/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type TipoCuenta = 'ACTIVO' | 'PASIVO' | 'PATRIMONIO' | 'INGRESO' | 'GASTO' | 'COSTO';
export type Naturaleza = 'DEUDORA' | 'ACREEDORA';
export type EstadoAsiento = 'BORRADOR' | 'APROBADO' | 'ANULADO';
export type TipoDiario = 'VENTAS' | 'COMPRAS' | 'BANCO' | 'CAJA' | 'NOMINA' | 'VARIOS';
export type EstadoPeriodo = 'ABIERTO' | 'CERRADO';
export type AmbitoContable = 'FISCAL' | 'GERENCIAL';
export type AmbitoReporte = 'CONSOLIDADO' | 'FISCAL' | 'GERENCIAL';
export type MonedaReporte = 'BASE' | 'PAIS' | 'REFERENCIA';
export type TipoCentroCosto =
  | 'OPERATIVO'
  | 'ADMINISTRATIVO'
  | 'COMERCIAL'
  | 'LOGISTICA'
  | 'PRODUCCION';

export interface CentroCosto {
  id_centro_costo: string;
  id_empresa: string;
  codigo: string;
  nombre: string;
  tipo: TipoCentroCosto | string;
  tipo_display?: string;
  id_padre: string | null;
  padre_nombre?: string | null;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion?: string;
}

export interface CentroCostoPayload {
  id_empresa: string;
  codigo: string;
  nombre: string;
  tipo: string;
  id_padre?: string | null;
  activo?: boolean;
}

export interface CuentaContable {
  id_cuenta_contable: string;
  id_empresa: string;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: TipoCuenta | string;
  naturaleza: Naturaleza | string;
  id_cuenta_padre: string | null;
  nivel: number;
  activo: boolean;
  fecha_creacion: string;
}

export interface CrearCuentaPayload {
  id_empresa: string;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: string;
  naturaleza: string;
  id_cuenta_padre?: string | null;
  nivel: number;
}

export interface DetalleAsiento {
  id_detalle_asiento: string;
  id_asiento: string;
  id_cuenta_contable: string;
  id_contacto?: string | null;
  contacto_nombre?: string | null;
  id_centro_costo?: string | null;
  centro_costo_nombre?: string | null;
  /** Montos como string decimal (R-CODE-4). */
  debe: string;
  haber: string;
  debe_base?: string | null;
  haber_base?: string | null;
  debe_pais?: string | null;
  haber_pais?: string | null;
  debe_referencia?: string | null;
  haber_referencia?: string | null;
  tasa_bcv_aplicada?: string | null;
  tasa_referencia_aplicada?: string | null;
  descripcion_detalle: string | null;
  fecha_creacion: string;
}

export interface AsientoContable {
  id_asiento: string;
  id_empresa: string;
  id_diario?: string | null;
  diario_nombre?: string | null;
  ambito?: AmbitoContable | string;
  ambito_display?: string;
  asiento_revertido?: string | null;
  contra_asiento_id?: string | null;
  es_cierre?: boolean;
  fecha_asiento: string;
  numero_asiento: string;
  descripcion: string;
  id_documento_origen: string | null;
  nombre_modelo_origen: string | null;
  estado_asiento: EstadoAsiento | string;
  fecha_creacion: string;
  /** Líneas embebidas en el detalle del asiento. */
  detalles?: DetalleAsiento[];
}

export interface RevertirAsientoPayload {
  fecha_reversion?: string | null;
  motivo?: string;
}

export interface DiarioContable {
  id_diario: string;
  id_empresa: string;
  codigo: string;
  nombre: string;
  tipo: TipoDiario | string;
  tipo_display?: string;
  ambito?: AmbitoContable | string;
  ambito_display?: string;
  prefijo_secuencia: string;
  siguiente_numero: number;
  cuenta_defecto_debe: string | null;
  cuenta_defecto_debe_nombre?: string | null;
  cuenta_defecto_haber: string | null;
  cuenta_defecto_haber_nombre?: string | null;
  id_cuenta_bancaria?: string | null;
  id_caja?: string | null;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion?: string;
}

export interface DiarioContablePayload {
  id_empresa: string;
  codigo: string;
  nombre: string;
  tipo: string;
  ambito?: AmbitoContable | string;
  prefijo_secuencia?: string;
  siguiente_numero?: number;
  cuenta_defecto_debe?: string | null;
  cuenta_defecto_haber?: string | null;
  id_cuenta_bancaria?: string | null;
  id_caja?: string | null;
  activo?: boolean;
}

export interface PeriodoContable {
  id_periodo: string;
  id_empresa: string;
  anio: number;
  mes: number;
  estado: EstadoPeriodo | string;
  estado_display?: string;
  fecha_cierre: string | null;
  cerrado_por: string | null;
  cerrado_por_username?: string | null;
  asiento_cierre: string | null;
  asiento_cierre_numero?: string | null;
  observaciones: string;
  activo: boolean;
  fecha_creacion: string;
  fecha_actualizacion?: string;
}

export interface CerrarPeriodoPayload {
  id_empresa: string;
  anio: number;
  mes: number;
  observaciones?: string;
}

export interface CerrarEjercicioPayload {
  id_empresa: string;
  anio: number;
  cuenta_resultado_acumulado: string;
  fecha_cierre?: string | null;
}

export interface CerrarEjercicioResponse {
  anio: number;
  asiento_cierre: AsientoContable | null;
  resultado_ejercicio: string;
  cantidad_cuentas_saldadas: number;
  periodos_cerrados: PeriodoContable[];
}

export interface MapeoContable {
  id_mapeo: string;
  id_empresa: string;
  id_diario?: string | null;
  diario_nombre?: string | null;
  tipo_asiento: string;
  tipo_asiento_display?: string;
  cuenta_debe: string;
  cuenta_debe_nombre?: string;
  cuenta_haber: string;
  cuenta_haber_nombre?: string;
  descripcion_plantilla: string;
  activo: boolean;
  fecha_creacion: string;
}

export interface MapeoContablePayload {
  id_empresa: string;
  id_diario?: string | null;
  tipo_asiento: string;
  cuenta_debe: string;
  cuenta_haber: string;
  descripcion_plantilla?: string;
  activo?: boolean;
}

export interface TipoAsientoChoice {
  value: string;
  label: string;
}

export interface AsientosFiltros {
  estado?: string;
  fechaDesde?: string;
  fechaHasta?: string;
}

// ── Reportes financieros canónicos (PR-14 · Ola B2) ──────────────────────────

export type TipoReporteContable =
  | 'balance-comprobacion'
  | 'estado-resultados'
  | 'balance-general'
  | 'libro-mayor-auxiliar';

export type FormatoExportReporte = 'csv' | 'pdf';

export interface ReporteContableMeta {
  empresa_id: string;
  moneda_base: string;
  moneda_base_simbolo: string;
  incluir_equivalentes_usd: boolean;
  usd_disponible: boolean;
  tasa_usd: string | null;
  tasa_usd_inversa?: boolean;
  usd_mensaje: string;
  ambito?: AmbitoReporte | string;
  moneda_reporte?: MonedaReporte | string;
  id_centro_costo?: string | null;
  centro_costo_nombre?: string;
}

export interface BalanceComprobacionCuenta {
  id_cuenta_contable: string;
  id_cuenta_padre: string | null;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: TipoCuenta | string;
  naturaleza: Naturaleza | string;
  nivel: number;
  debe_inicial: string;
  haber_inicial: string;
  saldo_inicial: string;
  saldo_inicial_deudor: string;
  saldo_inicial_acreedor: string;
  debe: string;
  haber: string;
  debe_periodo: string;
  haber_periodo: string;
  debe_final_acum: string;
  haber_final_acum: string;
  saldo: string;
  saldo_final_deudor: string;
  saldo_final_acreedor: string;
  debe_inicial_usd?: string | null;
  haber_inicial_usd?: string | null;
  saldo_inicial_usd?: string | null;
  debe_usd?: string | null;
  haber_usd?: string | null;
  debe_final_acum_usd?: string | null;
  haber_final_acum_usd?: string | null;
  saldo_usd?: string | null;
}

export interface BalanceComprobacionReport extends ReporteContableMeta {
  fecha_desde: string | null;
  fecha_hasta: string | null;
  id_diario: string | null;
  diario_nombre: string;
  cuentas: BalanceComprobacionCuenta[];
  total_debe_inicial: string;
  total_haber_inicial: string;
  total_saldo_inicial_deudor: string;
  total_saldo_inicial_acreedor: string;
  total_debe: string;
  total_haber: string;
  total_debe_periodo: string;
  total_haber_periodo: string;
  total_debe_final_acum: string;
  total_haber_final_acum: string;
  total_saldo_final_deudor: string;
  total_saldo_final_acreedor: string;
  cuadrado: boolean;
  total_debe_usd?: string | null;
  total_haber_usd?: string | null;
}

export interface EstadoFinancieroCuenta {
  id_cuenta_contable: string;
  id_cuenta_padre: string | null;
  codigo_cuenta: string;
  nombre_cuenta: string;
  tipo_cuenta: TipoCuenta | string;
  naturaleza: Naturaleza | string;
  nivel: number;
  debe: string;
  haber: string;
  saldo: string;
  saldo_usd?: string | null;
}

export interface EstadoResultadosReport extends ReporteContableMeta {
  fecha_desde: string;
  fecha_hasta: string;
  ingresos: EstadoFinancieroCuenta[];
  costos: EstadoFinancieroCuenta[];
  gastos: EstadoFinancieroCuenta[];
  total_ingresos: string;
  total_costos: string;
  total_gastos: string;
  utilidad_bruta: string;
  resultado_neto: string;
  total_ingresos_usd?: string | null;
  total_costos_usd?: string | null;
  total_gastos_usd?: string | null;
  utilidad_bruta_usd?: string | null;
  resultado_neto_usd?: string | null;
}

export interface BalanceGeneralReport extends ReporteContableMeta {
  fecha_corte: string;
  activos: EstadoFinancieroCuenta[];
  pasivos: EstadoFinancieroCuenta[];
  patrimonio: EstadoFinancieroCuenta[];
  total_activos: string;
  total_pasivos: string;
  total_patrimonio: string;
  resultado_periodo: string;
  total_pasivo_patrimonio_y_resultado: string;
  ecuacion_cuadrada: boolean;
  total_activos_usd?: string | null;
  total_pasivos_usd?: string | null;
  total_patrimonio_usd?: string | null;
  resultado_periodo_usd?: string | null;
  total_pasivo_patrimonio_y_resultado_usd?: string | null;
}

export interface LibroMayorMovimiento {
  id_detalle_asiento: string;
  id_asiento: string;
  ambito?: AmbitoContable | string;
  fecha_asiento: string;
  numero_asiento: string;
  descripcion_asiento: string;
  descripcion_detalle: string;
  id_diario: string | null;
  diario_codigo: string;
  diario_nombre: string;
  id_cuenta_contable: string;
  codigo_cuenta: string;
  nombre_cuenta: string;
  id_contacto: string | null;
  contacto_nombre: string;
  id_centro_costo?: string | null;
  centro_costo_nombre?: string;
  debe: string;
  haber: string;
  saldo_corrido: string;
  debe_usd?: string | null;
  haber_usd?: string | null;
  saldo_corrido_usd?: string | null;
}

export interface LibroMayorAuxiliarReport extends ReporteContableMeta {
  fecha_desde: string | null;
  fecha_hasta: string | null;
  id_cuenta_contable: string | null;
  cuenta_label: string;
  id_contacto: string | null;
  contacto_label: string;
  id_diario: string | null;
  diario_label: string;
  limit: number;
  saldo_inicial: string;
  total_debe: string;
  total_haber: string;
  saldo_final: string;
  truncado: boolean;
  movimientos: LibroMayorMovimiento[];
  saldo_inicial_usd?: string | null;
  total_debe_usd?: string | null;
  total_haber_usd?: string | null;
  saldo_final_usd?: string | null;
}

export interface ContactoContableItem {
  id_contacto: string;
  nombre_completo?: string;
  nombre?: string;
  rif?: string;
}

export interface ReporteBalanceComprobacionFiltros {
  empresa_id: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  id_diario?: string;
  incluir_equivalentes_usd?: boolean;
  ambito?: AmbitoReporte;
  moneda?: MonedaReporte;
  id_centro_costo?: string;
}

export interface ReporteEstadoResultadosFiltros {
  empresa_id: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  incluir_equivalentes_usd?: boolean;
  ambito?: AmbitoReporte;
  moneda?: MonedaReporte;
  id_centro_costo?: string;
}

export interface ReporteBalanceGeneralFiltros {
  empresa_id: string;
  fecha_corte?: string;
  incluir_equivalentes_usd?: boolean;
  ambito?: AmbitoReporte;
  moneda?: MonedaReporte;
  id_centro_costo?: string;
}

export interface ReporteLibroMayorFiltros {
  empresa_id: string;
  id_cuenta_contable?: string;
  id_contacto?: string;
  id_diario?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  limit?: number;
  incluir_equivalentes_usd?: boolean;
  ambito?: AmbitoReporte;
  moneda?: MonedaReporte;
  id_centro_costo?: string;
}

function buildReporteQuery(
  filtros: Record<string, string | number | boolean | undefined>,
  formato?: FormatoExportReporte,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filtros)) {
    if (value === undefined || value === '' || value === false) continue;
    params.set(key, String(value));
  }
  if (formato) {
    params.set('formato', formato);
  }
  return params.toString();
}

const BASE = '/contabilidad';

function paginada<T>(response: PaginatedResponse<T> | T[]): PaginatedResponse<T> {
  if (response && typeof response === 'object' && 'results' in response) return response;
  const arr = toList<T>(response);
  return { count: arr.length, next: null, previous: null, results: arr };
}

// ── Service ────────────────────────────────────────────────────────────────

export const contabilidadService = {
  /** Plan de cuentas completo (orden por código → permite armar la jerarquía). */
  getPlanCuentas: async (): Promise<CuentaContable[]> => {
    const response = await get<CuentaContable[] | PaginatedResponse<CuentaContable>>(
      `${BASE}/plan-cuentas/?page_size=1000`,
    );
    return toList<CuentaContable>(response);
  },

  crearCuenta: async (payload: CrearCuentaPayload): Promise<CuentaContable> => {
    return post<CuentaContable>(`${BASE}/plan-cuentas/`, payload as unknown as Record<string, unknown>);
  },

  /** Libro de asientos paginado con filtros por estado y rango de fechas. */
  getAsientosPaginated: async (
    page = 1,
    pageSize = 20,
    filtros: AsientosFiltros = {},
  ): Promise<PaginatedResponse<AsientoContable>> => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filtros.estado) params.set('estado_asiento', filtros.estado);
    if (filtros.fechaDesde) params.set('fecha_asiento__gte', filtros.fechaDesde);
    if (filtros.fechaHasta) params.set('fecha_asiento__lte', filtros.fechaHasta);
    const response = await get<PaginatedResponse<AsientoContable> | AsientoContable[]>(
      `${BASE}/asientos-contables/?${params.toString()}`,
    );
    return paginada(response);
  },

  getAsiento: async (id: string): Promise<AsientoContable> => {
    return get<AsientoContable>(`${BASE}/asientos-contables/${id}/`);
  },

  revertirAsiento: async (
    idAsiento: string,
    payload: RevertirAsientoPayload = {},
  ): Promise<AsientoContable> => {
    return post<AsientoContable>(
      `${BASE}/asientos-contables/${idAsiento}/revertir/`,
      payload as Record<string, unknown>,
    );
  },

  /** Líneas debe/haber de un asiento (fallback si el detalle no las embebe). */
  getDetallesAsiento: async (asientoId: string): Promise<DetalleAsiento[]> => {
    const response = await get<DetalleAsiento[] | PaginatedResponse<DetalleAsiento>>(
      `${BASE}/detalles-asiento/?id_asiento=${asientoId}`,
    );
    return toList<DetalleAsiento>(response);
  },

  // ── Diarios contables ────────────────────────────────────────────────────

  getDiarios: async (filtros: { tipo?: string } = {}): Promise<DiarioContable[]> => {
    const params = new URLSearchParams({ page_size: '200' });
    if (filtros.tipo) params.set('tipo', filtros.tipo);
    const response = await get<DiarioContable[] | PaginatedResponse<DiarioContable>>(
      `${BASE}/diarios/?${params.toString()}`,
    );
    return toList<DiarioContable>(response);
  },

  crearDiario: async (payload: DiarioContablePayload): Promise<DiarioContable> => {
    return post<DiarioContable>(`${BASE}/diarios/`, payload as unknown as Record<string, unknown>);
  },

  actualizarDiario: async (id: string, payload: Partial<DiarioContablePayload>): Promise<DiarioContable> => {
    return patch<DiarioContable>(`${BASE}/diarios/${id}/`, payload as Record<string, unknown>);
  },

  // ── Períodos contables y cierre de ejercicio ─────────────────────────────

  getPeriodosContables: async (anio?: number): Promise<PeriodoContable[]> => {
    const params = new URLSearchParams({ page_size: '200' });
    if (anio) params.set('anio', String(anio));
    const response = await get<PeriodoContable[] | PaginatedResponse<PeriodoContable>>(
      `${BASE}/periodos-contables/?${params.toString()}`,
    );
    return toList<PeriodoContable>(response);
  },

  cerrarPeriodo: async (payload: CerrarPeriodoPayload): Promise<PeriodoContable> => {
    return post<PeriodoContable>(
      `${BASE}/periodos-contables/cerrar/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  reabrirPeriodo: async (idPeriodo: string, motivo = ''): Promise<PeriodoContable> => {
    return post<PeriodoContable>(`${BASE}/periodos-contables/${idPeriodo}/reabrir/`, { motivo });
  },

  cerrarEjercicio: async (payload: CerrarEjercicioPayload): Promise<CerrarEjercicioResponse> => {
    return post<CerrarEjercicioResponse>(
      `${BASE}/periodos-contables/cerrar-ejercicio/`,
      payload as unknown as Record<string, unknown>,
    );
  },

  // ── Mapeos contables ─────────────────────────────────────────────────────

  getMapeos: async (): Promise<MapeoContable[]> => {
    const response = await get<MapeoContable[] | PaginatedResponse<MapeoContable>>(
      `${BASE}/mapeos-contables/`,
    );
    return toList<MapeoContable>(response);
  },

  getTiposAsiento: async (): Promise<TipoAsientoChoice[]> => {
    const response = await get<TipoAsientoChoice[]>(`${BASE}/mapeos-contables/tipos-asiento/`);
    return toList<TipoAsientoChoice>(response);
  },

  crearMapeo: async (payload: MapeoContablePayload): Promise<MapeoContable> => {
    return post<MapeoContable>(`${BASE}/mapeos-contables/`, payload as unknown as Record<string, unknown>);
  },

  actualizarMapeo: async (id: string, payload: Partial<MapeoContablePayload>): Promise<MapeoContable> => {
    return patch<MapeoContable>(`${BASE}/mapeos-contables/${id}/`, payload as Record<string, unknown>);
  },

  // ── Reportes financieros canónicos (PR-14 · Ola B2) ──────────────────────

  getBalanceComprobacion: async (
    filtros: ReporteBalanceComprobacionFiltros,
  ): Promise<BalanceComprobacionReport> => {
    const qs = buildReporteQuery({ ...filtros });
    return get<BalanceComprobacionReport>(`${BASE}/reportes/balance-comprobacion/?${qs}`);
  },

  getEstadoResultados: async (
    filtros: ReporteEstadoResultadosFiltros,
  ): Promise<EstadoResultadosReport> => {
    const qs = buildReporteQuery({ ...filtros });
    return get<EstadoResultadosReport>(`${BASE}/reportes/estado-resultados/?${qs}`);
  },

  getBalanceGeneral: async (
    filtros: ReporteBalanceGeneralFiltros,
  ): Promise<BalanceGeneralReport> => {
    const qs = buildReporteQuery({ ...filtros });
    return get<BalanceGeneralReport>(`${BASE}/reportes/balance-general/?${qs}`);
  },

  getLibroMayorAuxiliar: async (
    filtros: ReporteLibroMayorFiltros,
  ): Promise<LibroMayorAuxiliarReport> => {
    const qs = buildReporteQuery({ ...filtros });
    return get<LibroMayorAuxiliarReport>(`${BASE}/reportes/libro-mayor-auxiliar/?${qs}`);
  },

  exportarReporteBlob: async (
    tipo: TipoReporteContable,
    formato: FormatoExportReporte,
    filtros: Record<string, string | number | boolean | undefined>,
  ): Promise<Blob> => {
    const qs = buildReporteQuery(filtros, formato);
    return fetchBlob(`${BASE}/reportes/${tipo}/?${qs}`, {
      headers: { Accept: '*/*' },
    });
  },

  getContactosSelector: async (): Promise<ContactoContableItem[]> => {
    const response = await get<ContactoContableItem[] | PaginatedResponse<ContactoContableItem>>(
      '/core/contactos/?page_size=200',
    );
    return toList<ContactoContableItem>(response);
  },

  // ── Centros de costo analíticos (Plan 09 · PR-36) ────────────────────────

  listCentrosCosto: async (): Promise<CentroCosto[]> => {
    const response = await get<CentroCosto[] | PaginatedResponse<CentroCosto>>(
      `${BASE}/centros-costo/?page_size=200`,
    );
    return toList<CentroCosto>(response);
  },

  createCentroCosto: async (payload: CentroCostoPayload): Promise<CentroCosto> => {
    return post<CentroCosto>(`${BASE}/centros-costo/`, payload as unknown as Record<string, unknown>);
  },

  updateCentroCosto: async (
    id: string,
    payload: Partial<CentroCostoPayload>,
  ): Promise<CentroCosto> => {
    return patch<CentroCosto>(`${BASE}/centros-costo/${id}/`, payload as Record<string, unknown>);
  },

  deleteCentroCosto: async (id: string): Promise<void> => {
    await del<void>(`${BASE}/centros-costo/${id}/`);
  },
};
