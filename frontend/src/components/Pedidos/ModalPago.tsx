import React, { useState, useEffect, useMemo } from 'react';

// Componentes de UI (suponiendo que usas Material-UI o similar)
import {
  Modal, Box, Typography, TextField, Button, Select, MenuItem,
  FormControl, InputLabel, IconButton, List, ListItem, ListItemText,
  Divider, Paper
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';

// Servicios
import { get } from '../../services/api';
import { getSesionActiva } from '../../services/sesionService';
import DeleteIcon from '@mui/icons-material/Delete';

// Servicios para métodos, monedas y tasas
// Puedes crear estos servicios en src/services si no existen
// import { fetchMetodosPagoEmpresaActivos } from '../../services/metodosPagoEmpresaActiva';
// import { fetchMonedasEmpresaActivas } from '../../services/monedasEmpresaActiva';
// import { get } from '../../services/api';

interface MetodoPago {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
}
// Activación de método por empresa
type MetodoPagoEmpresaActiva = {
  id?: number;
  empresa: string;
  metodo_pago: string; // id de MetodoPago
  activa: boolean;
};
interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
  es_base?: boolean;
  es_pais?: boolean;
}
// Activación de moneda por empresa
type MonedaEmpresaActiva = {
  id?: number;
  empresa: string;
  moneda: string; // id de Moneda
  activa: boolean;
};
export interface Pago {
  id_metodo_pago: string;
  id_moneda: string;
  monto: number;
  referencia?: string;
  tasa: number;
  tipo_tasa?: string;
  // calculados (no obligatorios en payload hacia backend, pero útiles en UI)
  monto_base?: number;
  monto_pais?: number;
  observaciones?: string;
  id_caja_fisica?: string;
  id_caja_virtual?: string;
  id_cuenta_bancaria?: string;
  id_datafono?: string;
  banco_destino?: string;
  // Campos de compatibilidad
  metodo?: string;
  moneda?: string;
}

// Respuesta paginada genérica
type Paginated<T> = { results: T[]; count?: number; next?: string | null; previous?: string | null };

// Type guard genérico
function isPaginated<T>(data: unknown): data is Paginated<T> {
  return !!data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results);
}

interface ParametroSistema {
  id_parametro: string;
  codigo_parametro: string;
  valor_parametro: string;
  tipo_dato: string;
}

// Interface para las cajas virtuales que retorna la API
interface CajaVirtual {
  id_caja: string;
  nombre: string;
  moneda: string; // código ISO de la moneda
  moneda_codigo_iso?: string; // alias para compatibilidad
  id_moneda: string; // ID de la moneda
  activa: boolean;
  caja_fisica?: string;
}

// (sin alias)
// Export NotaCredito type for use in other components
export interface NotaCredito {
  id_nota_credito: string;
  numero_nota: string;
  monto_disponible: number;
  id_moneda: string;
  fecha_emision: string;
  fecha_vencimiento?: string;
  descripcion?: string;
}

interface CuentaBancaria {
  id_cuenta_bancaria: string;
  nombre_cuenta: string;
  numero_cuenta: string;
  id_moneda: string;
  id_banco: string;
  nombre_banco: string;
  metodos_pago?: string[]; // IDs de métodos de pago aceptados
  monedas?: string[]; // IDs de monedas aceptadas
}

interface Datafono {
  id_datafono: string;
  nombre: string;
  id_moneda: string;
  id_cuenta_bancaria: string;
  metodos_pago?: string[]; // IDs de métodos de pago aceptados
  monedas?: string[]; // IDs de monedas aceptadas
}

interface ModalPagoProps {
  open: boolean;
  monto: number; // Monto total del documento, siempre en moneda BASE
  onClose: () => void;
  onConfirm: (pagos: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => void;
  empresaId?: string;
  tipoDocumento?: 'PEDIDO' | 'CXP' | 'GASTO' | 'NOTA_VENTA' | 'FACTURA' | 'NOMINA' | 'IMPUESTO' | 'COTIZACION';
  idDocumento?: string;
  idCliente?: string; // Para notas de crédito de clientes
  idProveedor?: string; // Para notas de crédito de proveedores
  tipoOperacionInicial?: 'INGRESO' | 'EGRESO'; // Para determinar si es ingreso o egreso inicialmente
}

const ModalPago: React.FC<ModalPagoProps> = ({
  open,
  monto,
  onClose,
  onConfirm,
  empresaId,
  tipoDocumento,
  // @ts-expect-error - idDocumento se mantiene por consistencia de interfaz pero no se usa actualmente
  idDocumento,
  idCliente,
  idProveedor,
  tipoOperacionInicial
}) => {
  const [metodos, setMetodos] = useState<MetodoPago[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [cajas, setCajas] = useState<CajaVirtual[]>([]);
  const [tasaBCV, setTasaBCV] = useState<number>(1);
  const [pagos, setPagos] = useState<Pago[]>([]);
  const [form, setForm] = useState<Pago>({
    id_metodo_pago: '',
    id_moneda: '',
    monto: 0,
    referencia: '',
    tasa: 1,
    tipo_tasa: 'OFICIAL_BCV',
    id_caja_fisica: '',
    id_caja_virtual: '',
    id_cuenta_bancaria: '',
    id_datafono: '',
    // Campos de compatibilidad
    metodo: '',
    moneda: ''
  });

  // Parámetros de tolerancia
  const [toleranciaPositiva, setToleranciaPositiva] = useState<number>(0.50);
  const [permitirNegativas, setPermitirNegativas] = useState<boolean>(true);

  // Nuevos estados para funcionalidades adicionales
  const [tipoOperacion, setTipoOperacion] = useState<'INGRESO' | 'EGRESO'>(tipoOperacionInicial || 'INGRESO');
  const [notasCredito, setNotasCredito] = useState<NotaCredito[]>([]);
  const [notasCreditoSeleccionadas, setNotasCreditoSeleccionadas] = useState<NotaCredito[]>([]);
  const [mostrarVueltos, setMostrarVueltos] = useState<boolean>(false);
  const [vuelto, setVuelto] = useState<Pago | null>(null);
  const [cuentasBancarias, setCuentasBancarias] = useState<CuentaBancaria[]>([]);
  const [datafonos, setDatafonos] = useState<Datafono[]>([]);
  const [cajaFisicaActual, setCajaFisicaActual] = useState<{ id_caja: string } | null>(null);

  // Cargar métodos de pago (definiciones) y aplicar activaciones si hay empresaId
  useEffect(() => {
    // Traer definiciones de métodos y activaciones por empresa; filtrar por activas
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
          const defs: MetodoPago[] = Array.isArray(defsRaw)
            ? defsRaw
            : isPaginated<MetodoPago>(defsRaw)
              ? defsRaw.results
              : [];
          const activasArr: MetodoPagoEmpresaActiva[] = Array.isArray(activasRaw)
            ? activasRaw
            : isPaginated<MetodoPagoEmpresaActiva>(activasRaw)
              ? activasRaw.results
              : [];
          const activasMap: Record<string, MetodoPagoEmpresaActiva> = {};
          activasArr.forEach(a => { activasMap[a.metodo_pago] = a; });
          // Por defecto si no hay registro de activación, considerar activo (coincide con otras pantallas)
          const filtrados = defs.filter(m => (activasMap[m.id_metodo_pago]?.activa ?? true));
          setMetodos(filtrados);
        })
        .catch((err: Error) => console.error('Error al cargar métodos de pago:', err));
    } else {
      get<Paginated<MetodoPago> | MetodoPago[]>(defsUrl)
        .then(defsRaw => {
          const defs: MetodoPago[] = Array.isArray(defsRaw)
            ? defsRaw
            : isPaginated<MetodoPago>(defsRaw)
              ? defsRaw.results
              : [];
          setMetodos(defs);
        })
        .catch((err: Error) => console.error('Error al cargar métodos de pago:', err));
    }
  }, [empresaId]);

  // Cargar monedas activas
  useEffect(() => {
    // Necesitamos definiciones de monedas y activaciones por empresa; luego filtramos por activas
    const defsUrl = `/finanzas/monedas/?limit=1000`;
    if (empresaId) {
      const activasUrl = `/finanzas/monedas-empresa-activas/?empresa=${empresaId}&limit=1000`;
      Promise.all([
        get<Paginated<Moneda> | Moneda[]>(defsUrl),
        get<Paginated<MonedaEmpresaActiva> | MonedaEmpresaActiva[]>(activasUrl),
      ])
        .then(([defsRaw, activasRaw]) => {
          const defs: Moneda[] = Array.isArray(defsRaw)
            ? defsRaw
            : isPaginated<Moneda>(defsRaw)
              ? defsRaw.results
              : [];
          const activasArr: MonedaEmpresaActiva[] = Array.isArray(activasRaw)
            ? activasRaw
            : isPaginated<MonedaEmpresaActiva>(activasRaw)
              ? activasRaw.results
              : [];
          const activasMap: Record<string, MonedaEmpresaActiva> = {};
          activasArr.forEach(a => { activasMap[a.moneda] = a; });
          const filtradas = defs.filter(m => (activasMap[m.id_moneda]?.activa ?? true));
          setMonedas(filtradas);
        })
        .catch((err: Error) => console.error('Error al cargar monedas:', err));
    } else {
      get<Paginated<Moneda> | Moneda[]>(defsUrl)
        .then(defsRaw => {
          const defs: Moneda[] = Array.isArray(defsRaw)
            ? defsRaw
            : isPaginated<Moneda>(defsRaw)
              ? defsRaw.results
              : [];
          setMonedas(defs);
        })
        .catch((err: Error) => console.error('Error al cargar monedas:', err));
    }
  }, [empresaId]);

  // Cargar tasa de cambio oficial BCV (global)
  useEffect(() => {
    // Obtener tasa BCV USD->VES (ruta alineada con resto del frontend)
    type TasaOficial = { valor_tasa: string | number; fecha_tasa?: string };
    get<TasaOficial>(`/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES`)
      .then((data) => {
        if (data && (data.valor_tasa !== undefined)) setTasaBCV(Number(data.valor_tasa));
      }).catch((err: Error) => console.error('Error al cargar tasa BCV:', err));
  }, []);

  // Cargar parámetros de tolerancia
  useEffect(() => {
    if (empresaId) {
      get(`/configuracion/parametros-sistema/?id_empresa=${empresaId}&limit=1000`)
        .then((response) => {
          const params: ParametroSistema[] = Array.isArray(response)
            ? response as ParametroSistema[]
            : isPaginated<ParametroSistema>(response)
              ? (response as Paginated<ParametroSistema>).results
              : [];
          const paramPositivo = params.find((p: ParametroSistema) => p.codigo_parametro === 'TOLERANCIA_DIFERENCIA_POSITIVA_PAGOS');
          const paramNegativo = params.find((p: ParametroSistema) => p.codigo_parametro === 'PERMITIR_DIFERENCIAS_NEGATIVAS_PAGOS');

          if (paramPositivo) {
            setToleranciaPositiva(parseFloat(paramPositivo.valor_parametro) || 0.50);
          }
          if (paramNegativo) {
            setPermitirNegativas(paramNegativo.valor_parametro.toLowerCase() === 'true');
          }
        })
        .catch((err: Error) => console.error('Error al cargar parámetros de tolerancia:', err));
    }
  }, [empresaId]);

  // Actualiza el valor inicial de la tasa en el formulario solo si el tipo de tasa es BCV
  useEffect(() => {
    setForm(f => f.tipo_tasa === 'OFICIAL_BCV' ? { ...f, tasa: tasaBCV } : f);
  }, [tasaBCV]);

  // Sugerir cuenta bancaria, datafono o caja virtual automáticamente cuando cambia el método de pago
  useEffect(() => {
    if (form.id_metodo_pago && cuentasBancarias.length > 0 && datafonos.length > 0 && cajas.length > 0) {
      // Buscar cuenta bancaria que acepte este método de pago y moneda
      const cuentaCompatible = cuentasBancarias.find(cuenta => {
        const metodoCompatible = cuenta.metodos_pago?.includes(form.id_metodo_pago);
        const monedaCompatible = cuenta.monedas?.includes(form.id_moneda);
        return metodoCompatible && monedaCompatible;
      });

      if (cuentaCompatible) {
        setForm(f => ({
          ...f,
          id_cuenta_bancaria: cuentaCompatible.id_cuenta_bancaria,
          id_datafono: '', // Limpiar datafono si se selecciona cuenta bancaria
          id_caja_virtual: '' // Limpiar caja virtual si se selecciona cuenta bancaria
        }));
        return;
      }

      // Si no hay cuenta bancaria compatible, buscar datafono
      const datafonoCompatible = datafonos.find(datafono => {
        const metodoCompatible = datafono.metodos_pago?.includes(form.id_metodo_pago);
        const monedaCompatible = datafono.monedas?.includes(form.id_moneda);
        return metodoCompatible && monedaCompatible;
      });

      if (datafonoCompatible) {
        setForm(f => ({
          ...f,
          id_datafono: datafonoCompatible.id_datafono,
          id_cuenta_bancaria: '', // Limpiar cuenta bancaria si se selecciona datafono
          id_caja_virtual: '' // Limpiar caja virtual si se selecciona datafono
        }));
        return;
      }

      // Si no hay cuenta bancaria ni datafono compatible, buscar caja virtual para efectivo
      const metodo = metodos.find(m => m.id_metodo_pago === form.id_metodo_pago);
      if (metodo && metodo.tipo_metodo?.toLowerCase().includes('efectivo')) {
        // Buscar caja virtual que tenga la misma moneda que el formulario
        const cajaCompatible = cajas.find(caja =>
          caja.moneda_codigo_iso === form.moneda
        );

        if (cajaCompatible) {
          setForm(f => ({
            ...f,
            id_caja_virtual: cajaCompatible.id_caja,
            id_cuenta_bancaria: '', // Limpiar cuenta bancaria si se selecciona caja virtual
            id_datafono: '' // Limpiar datafono si se selecciona caja virtual
          }));
          return;
        }
      }

      // Si no hay sugerencias automáticas, limpiar todos los campos
      setForm(f => ({
        ...f,
        id_cuenta_bancaria: '',
        id_datafono: '',
        id_caja_virtual: ''
      }));
    }
  }, [form.id_metodo_pago, form.metodo, form.id_moneda, form.moneda, cuentasBancarias, datafonos, cajas, metodos]);

  // Set defaults for first compatible entity when method and currency change
  useEffect(() => {
    if (form.id_metodo_pago && form.id_moneda && metodos.length > 0 && monedas.length > 0) {
      const metodo = metodos.find(m => m.id_metodo_pago === form.id_metodo_pago);
      if (metodo) {
        const monedaSeleccionada = monedas.find(m => m.id_moneda === form.id_moneda);
        const codigoMoneda = monedaSeleccionada?.codigo_iso;

        // Calculate compatible entities
        const cuentasCompatibles = cuentasBancarias.filter(cuenta =>
          cuenta.metodos_pago?.includes(form.id_metodo_pago) &&
          (!codigoMoneda || cuenta.monedas?.includes(form.id_moneda))
        );
        const datafonosCompatibles = datafonos.filter(datafono => {
          const compatibleMetodo = datafono.metodos_pago?.includes(form.id_metodo_pago);
          const compatibleMoneda = !codigoMoneda || datafono.monedas?.includes(form.id_moneda);
          return compatibleMetodo && compatibleMoneda;
        });
        const cajasCompatibles = cajas.filter(caja => {
          return !form.id_moneda || caja.id_moneda === form.id_moneda;
        });

        // Set defaults for first compatible if not already set
        setForm(f => ({
          ...f,
          id_cuenta_bancaria: cuentasCompatibles.length > 0 && !f.id_cuenta_bancaria ? cuentasCompatibles[0].id_cuenta_bancaria : f.id_cuenta_bancaria,
          id_datafono: datafonosCompatibles.length > 0 && !f.id_datafono ? datafonosCompatibles[0].id_datafono : f.id_datafono,
          id_caja_virtual: cajasCompatibles.length > 0 && !f.id_caja_virtual ? cajasCompatibles[0].id_caja : f.id_caja_virtual
        }));
      }
    }
  }, [form.id_metodo_pago, form.id_moneda, cuentasBancarias, datafonos, cajas, metodos, monedas]);

  // Cargar cajas virtuales a partir de la sesión activa
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    getSesionActiva().then((sesion) => {
      if (!sesion) return;
      setCajaFisicaActual(sesion.caja_fisica_principal);
      get('/finanzas/cajas/?id_caja_fisica=' + sesion.caja_fisica_principal.id_caja)
        .then((cajasRaw: unknown) => {
          type CajaRaw = { id_caja: string; nombre: string; moneda: { codigo_iso?: string } | string; moneda_codigo_iso?: string; activa: boolean; caja_fisica?: string };
          const mapCaja = (caja: CajaRaw): CajaVirtual => ({
            id_caja: caja.id_caja,
            nombre: caja.nombre,
            moneda: typeof caja.moneda === 'object' ? (caja.moneda?.codigo_iso || '') : caja.moneda,
            moneda_codigo_iso: caja.moneda_codigo_iso,
            id_moneda: typeof caja.moneda === 'object' ? '' : caja.moneda,
            activa: caja.activa,
            caja_fisica: caja.caja_fisica,
          });
          let cajasArray: CajaVirtual[] = [];
          if (Array.isArray(cajasRaw)) {
            cajasArray = (cajasRaw as CajaRaw[]).map(mapCaja);
          } else if (isPaginated<CajaRaw>(cajasRaw)) {
            cajasArray = cajasRaw.results.map(mapCaja);
          }
          if (cajasArray.length > 0) setCajas(cajasArray);
        })
        .catch((err: Error) => console.error('Error al cargar cajas virtuales:', err));
    }).catch((err: Error) => console.error('Error al cargar sesión activa:', err));
  }, []);

  // Determinar tipo de operación basado en el tipo de documento
  useEffect(() => {
    if (tipoDocumento) {
      // Documentos que generan ingresos
      const documentosIngreso = ['PEDIDO', 'NOTA_VENTA', 'FACTURA'];
      // Documentos que generan egresos
      const documentosEgreso = ['CXP', 'GASTO', 'REEMBOLSO_GASTO', 'NOMINA', 'IMPUESTO'];

      if (documentosIngreso.includes(tipoDocumento)) {
        setTipoOperacion('INGRESO');
      } else if (documentosEgreso.includes(tipoDocumento)) {
        setTipoOperacion('EGRESO');
      }
    }
  }, [tipoDocumento]);

  // Cargar notas de crédito del cliente o proveedor
  useEffect(() => {
    if ((idCliente || idProveedor) && empresaId) {
      const endpoint = idCliente
        ? `/ventas/notas-credito-cliente/?id_cliente=${idCliente}&id_empresa=${empresaId}&disponible=true`
        : `/compras/notas-credito-proveedor/?id_proveedor=${idProveedor}&id_empresa=${empresaId}&disponible=true`;

      get<Paginated<NotaCredito> | NotaCredito[]>(endpoint)
        .then((response) => {
          const notas: NotaCredito[] = Array.isArray(response)
            ? response
            : isPaginated<NotaCredito>(response)
              ? response.results
              : [];
          setNotasCredito(notas);
        })
        .catch((err: Error) => console.error('Error al cargar notas de crédito:', err));
    }
  }, [idCliente, idProveedor, empresaId]);

  // Cargar cuentas bancarias de la empresa
  useEffect(() => {
    if (!empresaId) return;
    get<Paginated<CuentaBancaria> | CuentaBancaria[]>(`/finanzas/cuentas-bancarias/?id_empresa=${empresaId}&limit=1000`)
      .then((response) => {
        const cuentas: CuentaBancaria[] = Array.isArray(response)
          ? response
          : isPaginated<CuentaBancaria>(response)
            ? response.results
            : [];
        setCuentasBancarias(cuentas);
      })
      .catch((err: Error) => console.error('Error al cargar cuentas bancarias:', err));
  }, [empresaId]);

  // Cargar datafonos de la empresa y caja física
  useEffect(() => {
    if (!empresaId || !cajaFisicaActual) return;
    get<Paginated<Datafono> | Datafono[]>(`/finanzas/datafonos/?id_empresa=${empresaId}&id_caja_fisica=${cajaFisicaActual.id_caja}&limit=1000`)
      .then((response) => {
        let datafonosList: Datafono[] = [];
        if (Array.isArray(response)) {
          datafonosList = response;
        } else if (response && typeof response === 'object') {
          if ('results' in response && Array.isArray(response.results)) {
            datafonosList = response.results;
          } else if ('data' in response && Array.isArray((response as { data?: unknown }).data)) {
            datafonosList = (response as { data: Datafono[] }).data;
          }
        }
        setDatafonos(datafonosList);
      })
      .catch((err: Error) => console.error('Error al cargar datafonos:', err));
  }, [empresaId, cajaFisicaActual]);

  // Identificar moneda base y país
  const monedaBase = useMemo(() => {
    // Preferir flag es_base; fallback por código ISO USD
    return monedas.find(m => m.es_base) || monedas.find(m => m.codigo_iso?.toUpperCase() === 'USD');
  }, [monedas]);
  const monedaPais = useMemo(() => {
    // Preferir flag es_pais; fallback por código ISO VES
    return monedas.find(m => m.es_pais) || monedas.find(m => m.codigo_iso?.toUpperCase() === 'VES');
  }, [monedas]);

  // Función para conversión exacta
  const conversiones = useMemo(() => (monto: number, tasa: number, monedaId: string) => {
    if (!monedaBase || !monedaPais) return { base: 0, pais: 0 };
    // Si la moneda es la base
    if (monedaId === monedaBase.codigo_iso) {
      // Usar la tasa seleccionada para convertir a moneda país
      return { base: monto, pais: monto * tasa };
    }
    // Si la moneda es la país
    if (monedaId === monedaPais.codigo_iso) {
      // Usar la tasa seleccionada para convertir a moneda base
      return { base: monto / tasa, pais: monto };
    }
    // Si es otra moneda: se asume que la tasa es respecto a la moneda BASE
    const base = monto / tasa;
    const pais = base * tasaBCV; // Seguimos usando BCV para llevar base -> país
    return { base, pais };
  }, [monedaBase, monedaPais, tasaBCV]);

  // Calcular totales en ambas monedas
  const totalPagadoBase = useMemo(() => {
    return pagos.reduce((acc, p) => acc + (p.monto_base || 0), 0);
  }, [pagos]);

  // Calcular totales incluyendo notas de crédito
  const totalNotasCreditoBase = useMemo(() => {
    return notasCreditoSeleccionadas.reduce((total, nota) => {
      const tasaConversion = nota.id_moneda === monedaBase?.id_moneda ? 1 :
        nota.id_moneda === monedaPais?.id_moneda ? (1 / tasaBCV) : tasaBCV;
      return total + (nota.monto_disponible * tasaConversion);
    }, 0);
  }, [notasCreditoSeleccionadas, monedaBase, monedaPais, tasaBCV]);

  const totalPagadoConNotasBase = totalPagadoBase + totalNotasCreditoBase;
  const saldoRestanteConNotasBase = monto - totalPagadoConNotasBase;

  // Función para determinar si una diferencia es aceptable
  const esDiferenciaAceptable = (diferencia: number) => {
    // Permitir si la diferencia es positiva y menor o igual a la tolerancia configurada
    if (diferencia > 0) {
      return diferencia <= toleranciaPositiva;
    }
    // Permitir diferencias negativas si está configurado para permitirlas
    return permitirNegativas;
  };

  const handleAddPago = () => {
    // Validaciones básicas
    if (!form.id_metodo_pago || !form.id_moneda || !form.monto || form.monto <= 0) {
      alert('Por favor, complete todos los campos obligatorios del pago.');
      return;
    }

    // Validaciones específicas por tipo de método
    const metodo = metodos.find(m => m.id_metodo_pago === form.id_metodo_pago);
    if (!metodo) {
      alert('Método de pago no válido.');
      return;
    }

    const tipoMetodo = metodo.tipo_metodo?.toLowerCase() || '';

    // Para métodos en efectivo, se requiere caja virtual
    if ((tipoMetodo.includes('efectivo') || tipoMetodo.includes('cash')) && !form.id_caja_virtual) {
      alert('Para pagos en efectivo, debe seleccionar una caja virtual.');
      return;
    }

    // Para transferencias, cheques, etc., se requiere cuenta bancaria
    if ((tipoMetodo.includes('transferencia') || tipoMetodo.includes('cheque') || tipoMetodo.includes('banco')) && !form.id_cuenta_bancaria) {
      alert('Para este método de pago, debe seleccionar una cuenta bancaria.');
      return;
    }

    // Para tarjetas, débito, crédito, se requiere datafono
    if ((tipoMetodo.includes('tarjeta') || tipoMetodo.includes('debito') || tipoMetodo.includes('credito')) && !form.id_datafono) {
      alert('Para pagos con tarjeta, debe seleccionar un datafono.');
      return;
    }

    // Si no es ninguno de los anteriores, al menos una entidad debe estar seleccionada
    if (!form.id_caja_virtual && !form.id_cuenta_bancaria && !form.id_datafono) {
      alert('Debe seleccionar al menos una entidad financiera para el pago.');
      return;
    }

    const conv = conversiones(form.monto, form.tasa, form.moneda || '');
    setPagos([...pagos, { ...form, monto_base: conv.base, monto_pais: conv.pais }]);
    setForm({
      id_metodo_pago: '',
      id_moneda: '',
      monto: 0,
      referencia: '',
      tasa: tasaBCV,
      tipo_tasa: 'OFICIAL_BCV',
      id_caja_fisica: '',
      id_caja_virtual: '',
      id_cuenta_bancaria: '',
      id_datafono: '',
      banco_destino: '',
      // Campos de compatibilidad
      metodo: '',
      moneda: ''
    });
  };

  // Handler para eliminar pago
  const handleRemovePago = (idx: number) => {
    setPagos(pagos.filter((_, i) => i !== idx));
  };

  // Handler para cambiar campos del pago actual
  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | SelectChangeEvent<string>) => {
    const { name, value } = e.target;
    if (name === 'tasa') {
      // Si el usuario edita la tasa, marcar como manual para no sobrescribir con futuros cambios del BCV
      setForm(f => ({ ...f, tasa: Number(value), tipo_tasa: 'MANUAL' }));
      return;
    }
    if (name === 'id_moneda') {
      // Cuando cambia la moneda, actualizar tanto id_moneda como moneda (código ISO)
      const monedaSeleccionada = monedas.find(m => m.id_moneda === value);
      setForm(f => ({
        ...f,
        id_moneda: value,
        moneda: monedaSeleccionada?.codigo_iso || value
      }));
      return;
    }
    if (name === 'id_metodo_pago') {
      // Cuando cambia el método de pago, actualizar tanto id_metodo_pago como metodo (para compatibilidad)
      const metodoSeleccionado = metodos.find(m => m.id_metodo_pago === value);
      setForm(f => ({
        ...f,
        id_metodo_pago: value,
        metodo: metodoSeleccionado?.nombre_metodo || value
      }));
      return;
    }
    setForm(f => ({ ...f, [name]: name === 'monto' ? Number(value) : value }));
  };

  // Función para determinar campos dinámicos basados en método de pago
  const getCamposDinamicos = (metodoId: string) => {
    const metodo = metodos.find(m => m.id_metodo_pago === metodoId);
    if (!metodo) return null;

    const tipoMetodo = metodo.tipo_metodo?.toLowerCase() || '';
    // Determinar qué entidades son compatibles con este método y moneda
    const monedaSeleccionada = monedas.find(m => m.id_moneda === form.id_moneda);
    const codigoMoneda = monedaSeleccionada?.codigo_iso;

    const cuentasCompatibles = cuentasBancarias.filter(cuenta =>
      cuenta.metodos_pago?.includes(metodoId) &&
      (!codigoMoneda || cuenta.monedas?.includes(form.id_moneda))
    );
    const datafonosCompatibles = datafonos.filter(datafono => {
      const compatibleMetodo = datafono.metodos_pago?.includes(metodoId);
      const compatibleMoneda = !codigoMoneda || datafono.monedas?.includes(form.id_moneda);
      return compatibleMetodo && compatibleMoneda;
    });
    const cajasCompatibles = cajas.filter(caja => {
      // Para todos los métodos, filtrar por moneda de la caja
      return !form.id_moneda || caja.id_moneda === form.id_moneda;
    });

    return (
      <>
        {/* Caja Virtual - para métodos en efectivo con cajas disponibles */}
        {(tipoMetodo.includes('efectivo') || tipoMetodo.includes('cash')) && cajasCompatibles.length > 0 && (
          <Box sx={{ width: { xs: '100%', md: '20%' } }}>
            <FormControl fullWidth>
              <InputLabel>Caja Virtual</InputLabel>
              <Select name="id_caja_virtual" value={form.id_caja_virtual} onChange={handleFormChange}>
                {cajasCompatibles.map((c: CajaVirtual) => <MenuItem key={c.id_caja} value={c.id_caja}>{c.nombre} ({c.moneda_codigo_iso})</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
        )}

        {/* Cuenta Bancaria - si hay cuentas disponibles y compatibles */}
        {cuentasCompatibles.length > 0 && (
          <Box sx={{ width: { xs: '100%', md: '20%' } }}>
            <FormControl fullWidth>
              <InputLabel>Cuenta Bancaria</InputLabel>
              <Select name="id_cuenta_bancaria" value={form.id_cuenta_bancaria || ''} onChange={handleFormChange}>
                <MenuItem value="">
                  <em>Seleccionar cuenta bancaria</em>
                </MenuItem>
                {cuentasCompatibles.map((cuenta) => {
                  const moneda = monedas.find(m => m.id_moneda === cuenta.id_moneda);
                  return <MenuItem key={cuenta.id_cuenta_bancaria} value={cuenta.id_cuenta_bancaria}>
                    {cuenta.nombre_banco} - {cuenta.numero_cuenta} ({moneda?.codigo_iso || cuenta.id_moneda})
                  </MenuItem>;
                })}
              </Select>
            </FormControl>
          </Box>
        )}

        {/* Datafono - si hay datafonos disponibles y compatibles */}
        {datafonosCompatibles.length > 0 && (tipoMetodo.includes('tarjeta') || tipoMetodo.includes('debito') || tipoMetodo.includes('credito')) && (
          <Box sx={{ width: { xs: '100%', md: '20%' } }}>
            <FormControl fullWidth>
              <InputLabel>Datafono</InputLabel>
              <Select name="id_datafono" value={form.id_datafono || ''} onChange={handleFormChange}>
                <MenuItem value="">
                  <em>Seleccionar datafono</em>
                </MenuItem>
                {datafonosCompatibles.map((datafono) => {
                  const moneda = monedas.find(m => m.id_moneda === datafono.id_moneda);
                  return <MenuItem key={datafono.id_datafono} value={datafono.id_datafono}>
                    {datafono.nombre} ({moneda?.codigo_iso || datafono.id_moneda})
                  </MenuItem>;
                })}
              </Select>
            </FormControl>
          </Box>
        )}

        {/* Banco Destino - solo para métodos bancarios */}
        {(tipoMetodo.includes('transferencia') || tipoMetodo.includes('banco') || tipoMetodo.includes('cheque')) && (
          <Box sx={{ width: { xs: '100%', md: '20%' } }}>
            <TextField
              fullWidth
              label="Banco Destino (opcional)"
              name="banco_destino"
              value={form.banco_destino}
              onChange={handleFormChange}
            />
          </Box>
        )}
      </>
    );
  };

  // Función para calcular si hay vuelto disponible
  const calcularVueltoDisponible = () => {
    const totalPagado = pagos.reduce((acc, p) => acc + (p.monto_base || 0), 0);
    const totalNotasCredito = notasCreditoSeleccionadas.reduce((total, nota) => {
      const tasaConversion = nota.id_moneda === monedaBase?.id_moneda ? 1 :
        nota.id_moneda === monedaPais?.id_moneda ? (1 / tasaBCV) : tasaBCV;
      return total + (nota.monto_disponible * tasaConversion);
    }, 0);

    return Math.max(0, (totalPagado + totalNotasCredito) - monto);
  };

  // Handler para configurar vuelto
  const handleConfigurarVuelto = () => {
    const vueltoDisponible = calcularVueltoDisponible();
    if (vueltoDisponible > 0) {
      setMostrarVueltos(true);
      // Por defecto, dar vuelto en moneda del país (VES en Venezuela)
      const monedaVuelto = monedaPais?.codigo_iso || 'VES';
      const tasaVuelto = monedaVuelto === monedaBase?.codigo_iso ? 1 : tasaBCV;

      setVuelto({
        id_metodo_pago: 'efectivo', // Asumir efectivo para vuelto
        id_moneda: monedaVuelto,
        monto: vueltoDisponible / tasaVuelto,
        tasa: tasaVuelto,
        referencia: 'Vuelto automático',
        observaciones: `Vuelto generado automáticamente por pago excedente`,
        id_caja_virtual: form.id_caja_virtual, // Usar la misma caja
      });
    }
  };

  if (!open) return null;

  return (
    <Modal open={open} onClose={onClose}>
      <Paper sx={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '80%',
        maxWidth: 900,
        bgcolor: 'background.paper',
        boxShadow: 24,
        p: 4,
        maxHeight: '90vh',
        overflowY: 'auto'
      }}>
        <Typography variant="h5" component="h2" gutterBottom>
          Registrar Pago (Validación al Confirmar)
        </Typography>
        <Divider sx={{ my: 2 }} />

        {/* Selector de Tipo de Operación */}
        <Box sx={{ mb: 3 }}>
          <FormControl fullWidth>
            <InputLabel>Tipo de Operación</InputLabel>
            <Select
              value={tipoOperacion}
              onChange={(e) => setTipoOperacion(e.target.value as 'INGRESO' | 'EGRESO')}
              label="Tipo de Operación"
            >
              <MenuItem value="INGRESO">INGRESO</MenuItem>
              <MenuItem value="EGRESO">EGRESO</MenuItem>
            </Select>
          </FormControl>
          <Typography variant="caption" color="textSecondary" sx={{ mt: 1 }}>
            {tipoDocumento && `Detectado automáticamente del documento: ${tipoDocumento}`}
          </Typography>
        </Box>
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
          gap: 2,
          mb: 3,
        }}>
          <Box>
            <Typography variant="h6">Total Documento:</Typography>
            <Typography variant="body1">{monedaBase?.codigo_iso} {monto.toFixed(2)}</Typography>
            <Typography variant="body2" color="textSecondary">
              {monedaPais?.codigo_iso} {(monto * tasaBCV).toFixed(2)}
            </Typography>
          </Box>
          <Box>
            <Typography variant="h6" color={esDiferenciaAceptable(saldoRestanteConNotasBase) ? "success.main" : "error"}>
              Total Pagos + Notas Crédito:
            </Typography>
            <Typography variant="body1" color={esDiferenciaAceptable(saldoRestanteConNotasBase) ? "success.main" : "error"}>
              {monedaBase?.codigo_iso} {totalPagadoConNotasBase.toFixed(2)}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {monedaPais?.codigo_iso} {(totalPagadoConNotasBase * tasaBCV).toFixed(2)}
            </Typography>
            {notasCreditoSeleccionadas.length > 0 && (
              <Typography variant="caption" color="info.main">
                Incluye {notasCreditoSeleccionadas.length} nota(s) de crédito
              </Typography>
            )}
          </Box>
        </Box>

        {/* Resumen de Diferencia */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" color={esDiferenciaAceptable(saldoRestanteConNotasBase) ? "success.main" : "error"}>
            Diferencia Total (Validación al Confirmar):
          </Typography>
          <Typography variant="body1" color={esDiferenciaAceptable(saldoRestanteConNotasBase) ? "success.main" : "error"}>
            {monedaBase?.codigo_iso} {saldoRestanteConNotasBase.toFixed(2)}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {monedaPais?.codigo_iso} {(saldoRestanteConNotasBase * tasaBCV).toFixed(2)}
          </Typography>
          {saldoRestanteConNotasBase < 0 && esDiferenciaAceptable(saldoRestanteConNotasBase) && (
            <Typography variant="caption" color="success.main">
              ✅ Diferencia negativa aceptable
            </Typography>
          )}
          {saldoRestanteConNotasBase > toleranciaPositiva && (
            <Typography variant="caption" color="error">
              ❌ Diferencia positiva excesiva (&gt; {toleranciaPositiva.toFixed(2)})
            </Typography>
          )}
          {saldoRestanteConNotasBase >= 0 && saldoRestanteConNotasBase <= toleranciaPositiva && (
            <Typography variant="caption" color="success.main">
              ✅ Dentro de tolerancia positiva (≤ {toleranciaPositiva.toFixed(2)})
            </Typography>
          )}
        </Box>

        {/* Sección de Notas de Crédito */}
        {notasCredito.length > 0 && (
          <Box sx={{ mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Notas de Crédito Disponibles
            </Typography>
            <List dense>
              {notasCredito.map((nota) => (
                <ListItem key={nota.id_nota_credito}>
                  <ListItemText
                    primary={`${nota.numero_nota} - ${monedas.find(m => m.id_moneda === nota.id_moneda)?.codigo_iso} ${nota.monto_disponible.toFixed(2)}`}
                    secondary={`Emisión: ${new Date(nota.fecha_emision).toLocaleDateString()}${nota.fecha_vencimiento ? ` | Vence: ${new Date(nota.fecha_vencimiento).toLocaleDateString()}` : ''}`}
                  />
                  <Button
                    size="small"
                    variant={notasCreditoSeleccionadas.some(nc => nc.id_nota_credito === nota.id_nota_credito) ? "contained" : "outlined"}
                    onClick={() => {
                      setNotasCreditoSeleccionadas(prev =>
                        prev.some(nc => nc.id_nota_credito === nota.id_nota_credito)
                          ? prev.filter(nc => nc.id_nota_credito !== nota.id_nota_credito)
                          : [...prev, nota]
                      );
                    }}
                  >
                    {notasCreditoSeleccionadas.some(nc => nc.id_nota_credito === nota.id_nota_credito) ? 'Seleccionada' : 'Seleccionar'}
                  </Button>
                </ListItem>
              ))}
            </List>
            {notasCreditoSeleccionadas.length > 0 && (
              <Typography variant="body2" color="primary" sx={{ mt: 1 }}>
                Total notas de crédito seleccionadas: {monedaBase?.codigo_iso} {
                  notasCreditoSeleccionadas.reduce((total, nota) => {
                    const tasaConversion = nota.id_moneda === monedaBase?.id_moneda ? 1 :
                      nota.id_moneda === monedaPais?.id_moneda ? (1 / tasaBCV) : tasaBCV;
                    return total + (nota.monto_disponible * tasaConversion);
                  }, 0).toFixed(2)
                }
              </Typography>
            )}
          </Box>
        )}

        {/* Formulario para nuevo pago */}
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          <Box sx={{ width: { xs: '100%', md: '20%' } }}>
            <FormControl fullWidth>
              <InputLabel>Método</InputLabel>
              <Select name="id_metodo_pago" value={form.id_metodo_pago} onChange={handleFormChange}>
                {metodos.map(m => <MenuItem key={m.id_metodo_pago} value={m.id_metodo_pago}>{m.nombre_metodo}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <FormControl fullWidth>
              <InputLabel>Moneda</InputLabel>
              <Select name="id_moneda" value={form.id_moneda} onChange={handleFormChange}>
                {monedas.map(m => <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <TextField fullWidth label={`Tasa → ${monedaBase?.codigo_iso || 'BASE'}`} name="tasa" type="number" value={form.tasa} onChange={handleFormChange} />
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <TextField fullWidth label="Monto" name="monto" type="number" value={form.monto} onChange={handleFormChange} />
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <TextField fullWidth label="Referencia" name="referencia" value={form.referencia} onChange={handleFormChange} />
          </Box>

          {/* Campos dinámicos basados en método de pago y moneda */}
          {form.id_metodo_pago && form.id_moneda && getCamposDinamicos(form.id_metodo_pago)}

          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <Button
              fullWidth
              variant="contained"
              onClick={handleAddPago}
              disabled={
                !form.id_metodo_pago ||
                !form.id_moneda ||
                !form.monto ||
                form.monto <= 0
              }
            >
              Agregar
            </Button>
          </Box>
        </Box>

        {/* Sección de Vuelto */}
        {calcularVueltoDisponible() > 0 && (
          <Box sx={{ mb: 3, p: 2, bgcolor: 'warning.light', borderRadius: 1 }}>
            <Typography variant="h6" color="warning.dark" gutterBottom>
              💰 Vuelto Disponible: {monedaBase?.codigo_iso} {calcularVueltoDisponible().toFixed(2)}
            </Typography>
            {!mostrarVueltos ? (
              <Button variant="outlined" color="warning" onClick={handleConfigurarVuelto}>
                Configurar Vuelto
              </Button>
            ) : (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center', mt: 2 }}>
                <Typography variant="body2">Entregar vuelto en:</Typography>
                <FormControl sx={{ minWidth: 120 }}>
                  <InputLabel>Moneda</InputLabel>
                  <Select
                    value={vuelto?.id_moneda || ''}
                    onChange={(e) => setVuelto(prev => prev ? { ...prev, id_moneda: e.target.value } : null)}
                    size="small"
                  >
                    {monedas.map(m => <MenuItem key={m.id_moneda} value={m.codigo_iso}>{m.codigo_iso}</MenuItem>)}
                  </Select>
                </FormControl>
                <TextField
                  label="Monto"
                  type="number"
                  value={vuelto?.monto || 0}
                  onChange={(e) => setVuelto(prev => prev ? { ...prev, monto: Number(e.target.value) } : null)}
                  size="small"
                  sx={{ width: 120 }}
                />
                <TextField
                  label="Tasa"
                  type="number"
                  value={vuelto?.tasa || 1}
                  onChange={(e) => setVuelto(prev => prev ? { ...prev, tasa: Number(e.target.value) } : null)}
                  size="small"
                  sx={{ width: 100 }}
                />
                <Button
                  variant="contained"
                  color="success"
                  size="small"
                  onClick={() => {
                    if (vuelto) {
                      // Aquí se podría agregar lógica adicional para procesar el vuelto
                    }
                  }}
                >
                  Confirmar Vuelto
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setMostrarVueltos(false)}
                >
                  Cancelar
                </Button>
              </Box>
            )}
          </Box>
        )}

        {/* Lista de pagos agregados */}
        <List sx={{ mt: 3 }}>
          {pagos.map((p, idx) => (
            <ListItem
              key={idx}
              divider
              secondaryAction={
                <IconButton edge="end" aria-label="delete" onClick={() => handleRemovePago(idx)}>
                  <DeleteIcon />
                </IconButton>
              }
            >
              <ListItemText
                primary={`${metodos.find(m => m.id_metodo_pago === p.id_metodo_pago)?.nombre_metodo} - ${p.referencia}`}
                secondary={`Monto: ${monedas.find(m => m.codigo_iso === p.moneda)?.codigo_iso} ${p.monto.toFixed(2)} | Base: ${monedaBase?.codigo_iso} ${p.monto_base?.toFixed(2)} | País: ${monedaPais?.codigo_iso} ${p.monto_pais?.toFixed(2)}`}
              />
            </ListItem>
          ))}
        </List>

        <Divider sx={{ my: 2 }} />

        {/* Botones de acción */}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 3 }}>
          <Button onClick={onClose} sx={{ mr: 1 }}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={() => {
              // Validar que el total de pagos cumpla con las reglas de tolerancia
              if (!esDiferenciaAceptable(saldoRestanteConNotasBase)) {
                alert(`El total de pagos tiene una diferencia que excede la tolerancia configurada (${toleranciaPositiva.toFixed(2)}). No se pueden confirmar los pagos.`);
                return;
              }
              onConfirm(pagos, vuelto ? [vuelto] : undefined, notasCreditoSeleccionadas);
            }}
            disabled={pagos.length === 0 && notasCreditoSeleccionadas.length === 0}
          >
            Confirmar pagos
          </Button>
        </Box>
      </Paper>
    </Modal>
  );
};

export default ModalPago;


