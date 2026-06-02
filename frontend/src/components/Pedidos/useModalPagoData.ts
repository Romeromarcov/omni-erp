import { useQuery } from '@tanstack/react-query';
import { get, getAccessToken } from '../../services/api';
import { getSesionActiva } from '../../services/sesionService';
import type {
  MetodoPago,
  MetodoPagoEmpresaActiva,
  Moneda,
  MonedaEmpresaActiva,
  CajaVirtual,
  NotaCredito,
  CuentaBancaria,
  Datafono,
  ParametroSistema,
  Paginated,
} from './types';
import { isPaginated } from './types';

interface UseModalPagoDataProps {
  empresaId?: string;
  idCliente?: string;
  idProveedor?: string;
}

interface UseModalPagoDataReturn {
  metodos: MetodoPago[];
  monedas: Moneda[];
  cajas: CajaVirtual[];
  tasaBCV: number;
  toleranciaPositiva: number;
  permitirNegativas: boolean;
  notasCredito: NotaCredito[];
  cuentasBancarias: CuentaBancaria[];
  datafonos: Datafono[];
  cajaFisicaActual: { id_caja: string } | null;
  /** true mientras la tasa BCV no haya cargado correctamente. */
  tasaBCVLoading: boolean;
  /** Error de la query de la tasa BCV, o null si cargó bien. */
  tasaBCVError: Error | null;
  /**
   * Bandera derivada que el modal usa para bloquear "Confirmar pago":
   * true cuando la tasa BCV falló o todavía está cargando.
   */
  tasaBCVNoDisponible: boolean;
}

// ── Helpers de extracción de listas paginadas ────────────────────────────────
function toList<T>(raw: Paginated<T> | T[] | unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (isPaginated<T>(raw)) return raw.results;
  return [];
}

type TasaOficial = { valor_tasa: string | number };
type CajaRaw = {
  id_caja: string;
  nombre: string;
  moneda: { codigo_iso?: string } | string;
  moneda_codigo_iso?: string;
  activa: boolean;
  caja_fisica?: string;
};

const mapCaja = (c: CajaRaw): CajaVirtual => ({
  id_caja: c.id_caja,
  nombre: c.nombre,
  moneda: typeof c.moneda === 'object' ? (c.moneda?.codigo_iso || '') : c.moneda,
  moneda_codigo_iso: c.moneda_codigo_iso,
  id_moneda: typeof c.moneda === 'object' ? '' : c.moneda,
  activa: c.activa,
  caja_fisica: c.caja_fisica,
});

/**
 * Hook que centraliza toda la carga de datos de referencia del ModalPago:
 * métodos de pago, monedas, tasa BCV, parámetros de tolerancia, cajas
 * virtuales, notas de crédito, cuentas bancarias y datáfonos.
 *
 * Migrado a React Query: cada fuente es una query independiente con su propia
 * `queryKey` parametrizada por sus entradas y gateada con `enabled`. Esto evita
 * race conditions al desmontar el modal y deja de silenciar errores: la query
 * de la tasa BCV expone su error para poder bloquear la confirmación del pago.
 */
export function useModalPagoData({
  empresaId,
  idCliente,
  idProveedor,
}: UseModalPagoDataProps): UseModalPagoDataReturn {
  // ── Métodos de pago ────────────────────────────────────────────────────────
  const metodosQuery = useQuery<MetodoPago[]>({
    queryKey: ['metodosPago', 'empresa', empresaId ?? null],
    queryFn: async () => {
      const defsUrl = empresaId
        ? `/finanzas/metodos-pago/?id_empresa=${empresaId}&activo=true&limit=1000`
        : `/finanzas/metodos-pago/?activo=true&limit=1000`;
      if (!empresaId) {
        const defsRaw = await get<Paginated<MetodoPago> | MetodoPago[]>(defsUrl);
        return toList<MetodoPago>(defsRaw);
      }
      const activasUrl = `/finanzas/metodos-pago-empresa-activas/?empresa=${empresaId}&limit=1000`;
      const [defsRaw, activasRaw] = await Promise.all([
        get<Paginated<MetodoPago> | MetodoPago[]>(defsUrl),
        get<Paginated<MetodoPagoEmpresaActiva> | MetodoPagoEmpresaActiva[]>(activasUrl),
      ]);
      const defs = toList<MetodoPago>(defsRaw);
      const activasArr = toList<MetodoPagoEmpresaActiva>(activasRaw);
      const activasMap: Record<string, MetodoPagoEmpresaActiva> = {};
      activasArr.forEach(a => { activasMap[a.metodo_pago] = a; });
      return defs.filter(m => activasMap[m.id_metodo_pago]?.activa ?? true);
    },
  });

  // ── Monedas activas ────────────────────────────────────────────────────────
  const monedasQuery = useQuery<Moneda[]>({
    queryKey: ['monedas', 'empresa', empresaId ?? null],
    queryFn: async () => {
      const defsUrl = `/finanzas/monedas/?limit=1000`;
      if (!empresaId) {
        const defsRaw = await get<Paginated<Moneda> | Moneda[]>(defsUrl);
        return toList<Moneda>(defsRaw);
      }
      const activasUrl = `/finanzas/monedas-empresa-activas/?empresa=${empresaId}&limit=1000`;
      const [defsRaw, activasRaw] = await Promise.all([
        get<Paginated<Moneda> | Moneda[]>(defsUrl),
        get<Paginated<MonedaEmpresaActiva> | MonedaEmpresaActiva[]>(activasUrl),
      ]);
      const defs = toList<Moneda>(defsRaw);
      const activasArr = toList<MonedaEmpresaActiva>(activasRaw);
      const activasMap: Record<string, MonedaEmpresaActiva> = {};
      activasArr.forEach(a => { activasMap[a.moneda] = a; });
      return defs.filter(m => activasMap[m.id_moneda]?.activa ?? true);
    },
  });

  // ── Tasa BCV ───────────────────────────────────────────────────────────────
  const tasaBCVQuery = useQuery<number>({
    queryKey: ['tasaBCV', 'USD', 'VES'],
    queryFn: async () => {
      const data = await get<TasaOficial>('/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES');
      return data?.valor_tasa !== undefined ? Number(data.valor_tasa) : 1;
    },
  });

  // ── Parámetros de tolerancia ─────────────────────────────────────────────────
  const parametrosQuery = useQuery<{ toleranciaPositiva: number; permitirNegativas: boolean }>({
    queryKey: ['parametrosSistema', 'tolerancia', empresaId ?? null],
    enabled: !!empresaId,
    queryFn: async () => {
      const response = await get(`/configuracion/parametros-sistema/?id_empresa=${empresaId}&limit=1000`);
      const params = toList<ParametroSistema>(response);
      const pos = params.find(p => p.codigo_parametro === 'TOLERANCIA_DIFERENCIA_POSITIVA_PAGOS');
      const neg = params.find(p => p.codigo_parametro === 'PERMITIR_DIFERENCIAS_NEGATIVAS_PAGOS');
      return {
        toleranciaPositiva: pos ? (parseFloat(pos.valor_parametro) || 0.5) : 0.5,
        permitirNegativas: neg ? neg.valor_parametro.toLowerCase() === 'true' : true,
      };
    },
  });

  // ── Sesión activa (provee la caja física para cajas/datáfonos) ──────────────
  const sesionQuery = useQuery<{ id_caja: string } | null>({
    queryKey: ['sesionActiva', 'cajaFisica'],
    enabled: !!getAccessToken(),
    queryFn: async () => {
      const sesion = await getSesionActiva();
      return sesion ? sesion.caja_fisica_principal : null;
    },
  });
  const cajaFisicaActual = sesionQuery.data ?? null;

  // ── Cajas virtuales (vía sesión activa) ─────────────────────────────────────
  const cajasQuery = useQuery<CajaVirtual[]>({
    queryKey: ['cajasVirtuales', cajaFisicaActual?.id_caja ?? null],
    enabled: !!cajaFisicaActual,
    queryFn: async () => {
      const cajasRaw = await get('/finanzas/cajas/?id_caja_fisica=' + cajaFisicaActual!.id_caja);
      let arr: CajaVirtual[] = [];
      if (Array.isArray(cajasRaw)) arr = (cajasRaw as CajaRaw[]).map(mapCaja);
      else if (isPaginated<CajaRaw>(cajasRaw)) arr = cajasRaw.results.map(mapCaja);
      return arr;
    },
  });

  // ── Notas de crédito ─────────────────────────────────────────────────────────
  const notasCreditoQuery = useQuery<NotaCredito[]>({
    queryKey: ['notasCredito', empresaId ?? null, idCliente ?? null, idProveedor ?? null],
    enabled: !!empresaId && (!!idCliente || !!idProveedor),
    queryFn: async () => {
      const endpoint = idCliente
        ? `/ventas/notas-credito-cliente/?id_cliente=${idCliente}&id_empresa=${empresaId}&disponible=true`
        : `/compras/notas-credito-proveedor/?id_proveedor=${idProveedor}&id_empresa=${empresaId}&disponible=true`;
      const response = await get<Paginated<NotaCredito> | NotaCredito[]>(endpoint);
      return toList<NotaCredito>(response);
    },
  });

  // ── Cuentas bancarias ─────────────────────────────────────────────────────────
  const cuentasBancariasQuery = useQuery<CuentaBancaria[]>({
    queryKey: ['cuentasBancarias', 'empresa', empresaId ?? null],
    enabled: !!empresaId,
    queryFn: async () => {
      const response = await get<Paginated<CuentaBancaria> | CuentaBancaria[]>(
        `/finanzas/cuentas-bancarias/?id_empresa=${empresaId}&limit=1000`
      );
      return toList<CuentaBancaria>(response);
    },
  });

  // ── Datáfonos ─────────────────────────────────────────────────────────────────
  const datafonosQuery = useQuery<Datafono[]>({
    queryKey: ['datafonos', 'empresa', empresaId ?? null, cajaFisicaActual?.id_caja ?? null],
    enabled: !!empresaId && !!cajaFisicaActual,
    queryFn: async () => {
      const response = await get<Paginated<Datafono> | Datafono[]>(
        `/finanzas/datafonos/?id_empresa=${empresaId}&id_caja_fisica=${cajaFisicaActual!.id_caja}&limit=1000`
      );
      if (Array.isArray(response)) return response;
      if (response && typeof response === 'object') {
        if ('results' in response && Array.isArray(response.results)) return response.results;
        if ('data' in response && Array.isArray((response as { data?: unknown }).data)) {
          return (response as { data: Datafono[] }).data;
        }
      }
      return [];
    },
  });

  const tasaBCVError = (tasaBCVQuery.error as Error | null) ?? null;
  const tasaBCVLoading = tasaBCVQuery.isLoading;

  return {
    metodos: metodosQuery.data ?? [],
    monedas: monedasQuery.data ?? [],
    cajas: cajasQuery.data ?? [],
    tasaBCV: tasaBCVQuery.data ?? 1,
    toleranciaPositiva: parametrosQuery.data?.toleranciaPositiva ?? 0.5,
    permitirNegativas: parametrosQuery.data?.permitirNegativas ?? true,
    notasCredito: notasCreditoQuery.data ?? [],
    cuentasBancarias: cuentasBancariasQuery.data ?? [],
    datafonos: datafonosQuery.data ?? [],
    cajaFisicaActual,
    tasaBCVLoading,
    tasaBCVError,
    tasaBCVNoDisponible: tasaBCVLoading || tasaBCVError !== null,
  };
}
