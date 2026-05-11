import { useState, useEffect } from 'react';
import { get } from '../../services/api';
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
}

/**
 * Hook que centraliza toda la carga de datos de referencia del ModalPago:
 * métodos de pago, monedas, tasa BCV, parámetros de tolerancia, cajas
 * virtuales, notas de crédito, cuentas bancarias y datáfonos.
 */
export function useModalPagoData({
  empresaId,
  idCliente,
  idProveedor,
}: UseModalPagoDataProps): UseModalPagoDataReturn {
  const [metodos, setMetodos] = useState<MetodoPago[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [cajas, setCajas] = useState<CajaVirtual[]>([]);
  const [tasaBCV, setTasaBCV] = useState<number>(1);
  const [toleranciaPositiva, setToleranciaPositiva] = useState<number>(0.5);
  const [permitirNegativas, setPermitirNegativas] = useState<boolean>(true);
  const [notasCredito, setNotasCredito] = useState<NotaCredito[]>([]);
  const [cuentasBancarias, setCuentasBancarias] = useState<CuentaBancaria[]>([]);
  const [datafonos, setDatafonos] = useState<Datafono[]>([]);
  const [cajaFisicaActual, setCajaFisicaActual] = useState<{ id_caja: string } | null>(null);

  // ── Métodos de pago ──────────────────────────────────────────────────────
  useEffect(() => {
    const defsUrl = empresaId
      ? `/finanzas/metodos-pago/?id_empresa=${empresaId}&activo=true&limit=1000`
      : `/finanzas/metodos-pago/?activo=true&limit=1000`;

    if (empresaId) {
      const activasUrl = `/finanzas/metodos-pago-empresa-activas/?empresa=${empresaId}&limit=1000`;
      Promise.all([
        get<Paginated<MetodoPago> | MetodoPago[]>(defsUrl),
        get<Paginated<MetodoPagoEmpresaActiva> | MetodoPagoEmpresaActiva[]>(activasUrl),
      ])
        .then(([defsRaw, activasRaw]) => {
          const defs = Array.isArray(defsRaw) ? defsRaw : isPaginated<MetodoPago>(defsRaw) ? defsRaw.results : [];
          const activasArr = Array.isArray(activasRaw) ? activasRaw : isPaginated<MetodoPagoEmpresaActiva>(activasRaw) ? activasRaw.results : [];
          const activasMap: Record<string, MetodoPagoEmpresaActiva> = {};
          activasArr.forEach(a => { activasMap[a.metodo_pago] = a; });
          setMetodos(defs.filter(m => activasMap[m.id_metodo_pago]?.activa ?? true));
        })
        .catch((err: Error) => console.error('Error al cargar métodos de pago:', err));
    } else {
      get<Paginated<MetodoPago> | MetodoPago[]>(defsUrl)
        .then(defsRaw => {
          setMetodos(Array.isArray(defsRaw) ? defsRaw : isPaginated<MetodoPago>(defsRaw) ? defsRaw.results : []);
        })
        .catch((err: Error) => console.error('Error al cargar métodos de pago:', err));
    }
  }, [empresaId]);

  // ── Monedas activas ──────────────────────────────────────────────────────
  useEffect(() => {
    const defsUrl = `/finanzas/monedas/?limit=1000`;
    if (empresaId) {
      const activasUrl = `/finanzas/monedas-empresa-activas/?empresa=${empresaId}&limit=1000`;
      Promise.all([
        get<Paginated<Moneda> | Moneda[]>(defsUrl),
        get<Paginated<MonedaEmpresaActiva> | MonedaEmpresaActiva[]>(activasUrl),
      ])
        .then(([defsRaw, activasRaw]) => {
          const defs = Array.isArray(defsRaw) ? defsRaw : isPaginated<Moneda>(defsRaw) ? defsRaw.results : [];
          const activasArr = Array.isArray(activasRaw) ? activasRaw : isPaginated<MonedaEmpresaActiva>(activasRaw) ? activasRaw.results : [];
          const activasMap: Record<string, MonedaEmpresaActiva> = {};
          activasArr.forEach(a => { activasMap[a.moneda] = a; });
          setMonedas(defs.filter(m => activasMap[m.id_moneda]?.activa ?? true));
        })
        .catch((err: Error) => console.error('Error al cargar monedas:', err));
    } else {
      get<Paginated<Moneda> | Moneda[]>(defsUrl)
        .then(defsRaw => {
          setMonedas(Array.isArray(defsRaw) ? defsRaw : isPaginated<Moneda>(defsRaw) ? defsRaw.results : []);
        })
        .catch((err: Error) => console.error('Error al cargar monedas:', err));
    }
  }, [empresaId]);

  // ── Tasa BCV ─────────────────────────────────────────────────────────────
  useEffect(() => {
    type TasaOficial = { valor_tasa: string | number };
    get<TasaOficial>('/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES')
      .then(data => { if (data?.valor_tasa !== undefined) setTasaBCV(Number(data.valor_tasa)); })
      .catch((err: Error) => console.error('Error al cargar tasa BCV:', err));
  }, []);

  // ── Parámetros de tolerancia ──────────────────────────────────────────────
  useEffect(() => {
    if (!empresaId) return;
    get(`/configuracion/parametros-sistema/?id_empresa=${empresaId}&limit=1000`)
      .then(response => {
        const params: ParametroSistema[] = Array.isArray(response)
          ? response as ParametroSistema[]
          : isPaginated<ParametroSistema>(response) ? (response as Paginated<ParametroSistema>).results : [];
        const pos = params.find(p => p.codigo_parametro === 'TOLERANCIA_DIFERENCIA_POSITIVA_PAGOS');
        const neg = params.find(p => p.codigo_parametro === 'PERMITIR_DIFERENCIAS_NEGATIVAS_PAGOS');
        if (pos) setToleranciaPositiva(parseFloat(pos.valor_parametro) || 0.5);
        if (neg) setPermitirNegativas(neg.valor_parametro.toLowerCase() === 'true');
      })
      .catch((err: Error) => console.error('Error al cargar parámetros de tolerancia:', err));
  }, [empresaId]);

  // ── Cajas virtuales (vía sesión activa) ───────────────────────────────────
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    getSesionActiva()
      .then(sesion => {
        if (!sesion) return;
        setCajaFisicaActual(sesion.caja_fisica_principal);
        get('/finanzas/cajas/?id_caja_fisica=' + sesion.caja_fisica_principal.id_caja)
          .then((cajasRaw: unknown) => {
            type CajaRaw = { id_caja: string; nombre: string; moneda: { codigo_iso?: string } | string; moneda_codigo_iso?: string; activa: boolean; caja_fisica?: string };
            const mapCaja = (c: CajaRaw): CajaVirtual => ({
              id_caja: c.id_caja,
              nombre: c.nombre,
              moneda: typeof c.moneda === 'object' ? (c.moneda?.codigo_iso || '') : c.moneda,
              moneda_codigo_iso: c.moneda_codigo_iso,
              id_moneda: typeof c.moneda === 'object' ? '' : c.moneda,
              activa: c.activa,
              caja_fisica: c.caja_fisica,
            });
            let arr: CajaVirtual[] = [];
            if (Array.isArray(cajasRaw)) arr = (cajasRaw as CajaRaw[]).map(mapCaja);
            else if (isPaginated<CajaRaw>(cajasRaw)) arr = cajasRaw.results.map(mapCaja);
            if (arr.length > 0) setCajas(arr);
          })
          .catch((err: Error) => console.error('Error al cargar cajas virtuales:', err));
      })
      .catch((err: Error) => console.error('Error al cargar sesión activa:', err));
  }, []);

  // ── Notas de crédito ─────────────────────────────────────────────────────
  useEffect(() => {
    if ((!idCliente && !idProveedor) || !empresaId) return;
    const endpoint = idCliente
      ? `/ventas/notas-credito-cliente/?id_cliente=${idCliente}&id_empresa=${empresaId}&disponible=true`
      : `/compras/notas-credito-proveedor/?id_proveedor=${idProveedor}&id_empresa=${empresaId}&disponible=true`;
    get<Paginated<NotaCredito> | NotaCredito[]>(endpoint)
      .then(response => {
        setNotasCredito(Array.isArray(response) ? response : isPaginated<NotaCredito>(response) ? response.results : []);
      })
      .catch((err: Error) => console.error('Error al cargar notas de crédito:', err));
  }, [idCliente, idProveedor, empresaId]);

  // ── Cuentas bancarias ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!empresaId) return;
    get<Paginated<CuentaBancaria> | CuentaBancaria[]>(`/finanzas/cuentas-bancarias/?id_empresa=${empresaId}&limit=1000`)
      .then(response => {
        setCuentasBancarias(Array.isArray(response) ? response : isPaginated<CuentaBancaria>(response) ? response.results : []);
      })
      .catch((err: Error) => console.error('Error al cargar cuentas bancarias:', err));
  }, [empresaId]);

  // ── Datáfonos ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!empresaId || !cajaFisicaActual) return;
    get<Paginated<Datafono> | Datafono[]>(`/finanzas/datafonos/?id_empresa=${empresaId}&id_caja_fisica=${cajaFisicaActual.id_caja}&limit=1000`)
      .then(response => {
        let list: Datafono[] = [];
        if (Array.isArray(response)) {
          list = response;
        } else if (response && typeof response === 'object') {
          if ('results' in response && Array.isArray(response.results)) list = response.results;
          else if ('data' in response && Array.isArray((response as { data?: unknown }).data)) list = (response as { data: Datafono[] }).data;
        }
        setDatafonos(list);
      })
      .catch((err: Error) => console.error('Error al cargar datáfonos:', err));
  }, [empresaId, cajaFisicaActual]);

  return {
    metodos,
    monedas,
    cajas,
    tasaBCV,
    toleranciaPositiva,
    permitirNegativas,
    notasCredito,
    cuentasBancarias,
    datafonos,
    cajaFisicaActual,
  };
}
