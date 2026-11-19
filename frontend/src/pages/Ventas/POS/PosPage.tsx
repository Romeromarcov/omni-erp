/**
 * Sub-fase 1.G — POS de mostrador (distribuidora).
 *
 * Pantalla táctil de venta rápida a pantalla completa (sin el sidebar normal):
 *  - grilla de productos con búsqueda incremental;
 *  - lector de código de barras USB (teclado + Enter): el input de búsqueda
 *    vive siempre enfocado y al Enter busca por SKU exacto y agrega al carrito;
 *  - carrito con cantidades editables y totales con decimal.js;
 *  - cobro mixto multimoneda (PosPagoDialog) sobre la nota de venta creada en
 *    el backend (el IVA lo calcula el backend), con Idempotency-Key por pago;
 *  - exige sesión de caja abierta (PosSesionDialog ofrece abrirla);
 *  - recibo imprimible de 80mm (PosRecibo);
 *  - devoluciones de una venta por número (PosDevolucionDialog: líneas/cantidades
 *    capadas a lo disponible, reembolso por caja y recibo 80mm de devolución).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert, AppBar, Box, Button, Card, CardActionArea, CardContent, Divider,
  IconButton, Stack, TextField, Toolbar, Typography,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CloudOffIcon from '@mui/icons-material/CloudOff';
import DeleteIcon from '@mui/icons-material/Delete';
import PointOfSaleIcon from '@mui/icons-material/PointOfSale';
import ReplayIcon from '@mui/icons-material/Replay';
import SyncIcon from '@mui/icons-material/Sync';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Decimal from 'decimal.js';
import { D, subtotalLinea, toFixedStr } from '../../../lib/decimal';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos, type Producto } from '../../../services/productosService';
import { getSesionActiva } from '../../../services/sesionService';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { fetchTasaBCV } from '../../../services/tasaBCV';
import { buscarClientes, crearClienteConEmpresa } from '../../../services/clientesService';
import { post } from '../../../services/api';
import { IDEMPOTENCY_HEADER, newIdempotencyKey } from '../../../lib/idempotency';
import { pagosService } from '../../../services/pagosService';
import type { Almacen } from '../../../services/almacenesService';
import { useOnlineStatus } from '../../../hooks/useOnlineStatus';
import { useOutboxFlush } from '../../../hooks/useOutboxFlush';
import { buildVentaOfflineEnvelope } from '../../../lib/ventaOffline';
import {
  clearSyncedOutboxItems,
  discardOutboxItem,
  enqueueSale,
  listOutboxItems,
  retryOutboxItem,
  type OutboxSale,
  type SalePoster,
} from '../../../lib/salesOutbox';
import { mensajeDeError, statusDeError } from '../../../utils/api';
import PosPagoDialog from './PosPagoDialog';
import PosSesionDialog from './PosSesionDialog';
import PosRecibo, { type ReciboData } from './PosRecibo';
import PosDevolucionDialog, { type ReciboDevolucionData } from './PosDevolucionDialog';
import PosReciboDevolucion from './PosReciboDevolucion';
import PosColaOfflinePanel from './PosColaOfflinePanel';
import { subtotalCarrito, type PosCartItem, type PosPago, totalPagado } from './posTotals';

/** Nombre del cliente genérico de mostrador (se crea una vez por empresa). */
const CLIENTE_MOSTRADOR = 'Consumidor Final';

interface NotaVentaCreada {
  id_nota_venta?: string;
  numero_nota_venta?: string;
  monto_total?: number | string;
  monto_impuesto?: number | string;
  subtotal?: number | string;
}

interface SyncPushVentaResponse {
  id_nota_venta?: string;
  client_uuid?: string | null;
  numero_nota?: string;
  estado?: string;
  total?: string;
  alerta_stock_negativo?: boolean;
}

function clienteCacheKey(empresaId: string): string {
  return `pos_cliente_mostrador_${empresaId}`;
}

function leerClienteMostradorLocal(empresaId: string): string | null {
  if (!empresaId) return null;
  try {
    return localStorage.getItem(clienteCacheKey(empresaId)) || null;
  } catch {
    return null;
  }
}

function guardarClienteMostradorLocal(empresaId: string, idCliente: string): void {
  if (!empresaId || !idCliente) return;
  try {
    localStorage.setItem(clienteCacheKey(empresaId), idCliente);
  } catch {
    // Storage restringido: se mantiene el caché en memoria / TanStack.
  }
}

function esFalloConexionO5xx(err: unknown): boolean {
  if (err instanceof TypeError) return true;
  if (typeof DOMException !== 'undefined' && err instanceof DOMException && err.name === 'AbortError') {
    return true;
  }
  const status = statusDeError(err);
  if (status !== undefined) {
    return status >= 500;
  }
  if (err instanceof Error) {
    return /failed to fetch|network\s?error|err_network|load failed|fetch failed|econnrefused|offline/i.test(
      err.message,
    );
  }
  return false;
}

export default function PosPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const searchRef = useRef<HTMLInputElement>(null);
  // Clave de idempotencia de la NOTA: una por intento de venta, estable en
  // reintentos (un fallo de red tras crear la nota no la duplica — PR #86).
  const notaKeyRef = useRef<string | null>(null);

  const [busqueda, setBusqueda] = useState('');
  const [carrito, setCarrito] = useState<PosCartItem[]>([]);
  const [scanError, setScanError] = useState('');
  const [errorVenta, setErrorVenta] = useState<string | null>(null);
  const [sesionDialogOpen, setSesionDialogOpen] = useState(false);
  const [pagoDialogOpen, setPagoDialogOpen] = useState(false);
  const [devolucionDialogOpen, setDevolucionDialogOpen] = useState(false);
  const [reciboDevolucion, setReciboDevolucion] = useState<ReciboDevolucionData | null>(null);
  const [creandoNota, setCreandoNota] = useState(false);
  const [procesandoPagos, setProcesandoPagos] = useState(false);
  const [notaCreada, setNotaCreada] = useState<NotaVentaCreada | null>(null);
  const [recibo, setRecibo] = useState<ReciboData | null>(null);
  const [modoOffline, setModoOffline] = useState(false);
  const [clienteOfflineId, setClienteOfflineId] = useState<string | null>(null);
  const [colaDialogOpen, setColaDialogOpen] = useState(false);
  const [outboxItems, setOutboxItems] = useState<OutboxSale[]>([]);
  const [avisoSync, setAvisoSync] = useState<{ tipo: 'success' | 'warning'; texto: string } | null>(null);

  const { data: sesion, isLoading: cargandoSesion } = useQuery({
    queryKey: ['pos', 'sesion-activa'],
    queryFn: getSesionActiva,
  });

  const empresaId = sesion?.caja_fisica_principal?.sucursal?.empresa?.id_empresa || getEmpresaId() || '';

  const { data: productosData } = useQuery({
    queryKey: ['pos', 'productos', empresaId],
    queryFn: () => fetchProductos(empresaId),
    enabled: !!empresaId,
  });
  // fetchProductos ya devuelve un array plano (recorre todas las páginas).
  const productos: Producto[] = useMemo(() => productosData ?? [], [productosData]);

  const { data: metodos = [] } = useQuery({
    queryKey: ['pos', 'metodos-pago', empresaId],
    queryFn: () => fetchMetodosPagoEmpresaActivos(empresaId),
    enabled: !!empresaId,
  });
  const { data: monedas = [] } = useQuery({
    queryKey: ['pos', 'monedas', empresaId],
    queryFn: () => fetchMonedasEmpresaActivas(empresaId),
    enabled: !!empresaId,
  });
  const { data: tasaBcvData } = useQuery({
    queryKey: ['pos', 'tasa-bcv'],
    queryFn: () => fetchTasaBCV(),
    retry: false,
  });
  const tasaBcv = tasaBcvData?.tasa ? String(tasaBcvData.tasa) : '1';

  // Moneda del documento: la moneda país (VES) si está activa; si no, la primera.
  const monedaDocumento = useMemo(
    () => monedas.find((m) => m.codigo_iso?.toUpperCase() === 'VES') ?? monedas[0],
    [monedas],
  );
  const codigoIsoDocumento = monedaDocumento?.codigo_iso ?? 'VES';

  const productosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return productos;
    return productos.filter(
      (p) =>
        p.nombre_producto?.toLowerCase().includes(q) ||
        p.sku?.toLowerCase().includes(q),
    );
  }, [productos, busqueda]);

  const subtotal = subtotalCarrito(carrito);

  const agregarAlCarrito = (producto: Producto) => {
    setScanError('');
    setCarrito((prev) => {
      const existente = prev.find((i) => i.id_producto === producto.id_producto);
      if (existente) {
        return prev.map((i) =>
          i.id_producto === producto.id_producto
            ? { ...i, cantidad: D(i.cantidad).plus(1).toString() }
            : i,
        );
      }
      return [
        ...prev,
        {
          id_producto: producto.id_producto,
          nombre: producto.nombre_producto,
          sku: producto.sku,
          precio: String(producto.precio_venta_sugerido ?? 0),
          cantidad: '1',
        },
      ];
    });
  };

  /**
   * Lector de código de barras USB: escribe el código como teclado y emite
   * Enter. Al Enter buscamos por SKU EXACTO; si hay match se agrega al
   * carrito y se limpia el input (listo para el siguiente escaneo).
   */
  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const codigo = busqueda.trim();
    if (!codigo) return;
    const porSku = productos.find((p) => p.sku?.toLowerCase() === codigo.toLowerCase());
    if (porSku) {
      agregarAlCarrito(porSku);
      setBusqueda('');
    } else if (productosFiltrados.length === 1) {
      agregarAlCarrito(productosFiltrados[0]);
      setBusqueda('');
    } else {
      setScanError(`Sin coincidencia exacta para "${codigo}".`);
    }
  };

  const cambiarCantidad = (idProducto: string, cantidad: string) => {
    setCarrito((prev) =>
      prev.map((i) => (i.id_producto === idProducto ? { ...i, cantidad } : i)),
    );
  };

  const quitarItem = (idProducto: string) => {
    setCarrito((prev) => prev.filter((i) => i.id_producto !== idProducto));
  };

  /** Busca (o crea) el cliente genérico de mostrador y lo cachea localmente por empresa. */
  const obtenerClienteMostrador = useCallback(async (): Promise<string> => {
    const encontrados = await buscarClientes(CLIENTE_MOSTRADOR, empresaId);
    const match = encontrados.find(
      (c) => (c as { razon_social?: string }).razon_social?.toLowerCase() === CLIENTE_MOSTRADOR.toLowerCase(),
    );
    if (match?.id_cliente) {
      guardarClienteMostradorLocal(empresaId, match.id_cliente);
      return match.id_cliente;
    }
    const nuevo = await crearClienteConEmpresa({
      razon_social: CLIENTE_MOSTRADOR,
      rif: 'V000000000',
      telefono: '0000000000',
      id_empresa: empresaId,
    });
    guardarClienteMostradorLocal(empresaId, nuevo.id_cliente);
    return nuevo.id_cliente;
  }, [empresaId]);

  const { data: clienteMostradorCacheado } = useQuery({
    queryKey: ['pos', 'cliente-mostrador', empresaId],
    queryFn: obtenerClienteMostrador,
    enabled: !!empresaId && !!sesion && online,
    retry: false,
  });

  const obtenerClienteOfflineDesdeCache = (): string | null => {
    if (clienteMostradorCacheado) return clienteMostradorCacheado;
    const enQuery = queryClient.getQueryData<string>(['pos', 'cliente-mostrador', empresaId]);
    if (enQuery) return enQuery;
    const enStorage = leerClienteMostradorLocal(empresaId);
    if (enStorage) return enStorage;
    const listasClientes = queryClient.getQueriesData<unknown[]>({ queryKey: ['clientes'] });
    for (const [, lista] of listasClientes) {
      if (!Array.isArray(lista)) continue;
      const encontrado = lista.find((c) => {
        if (!c || typeof c !== 'object') return false;
        const obj = c as { razon_social?: unknown; id_cliente?: unknown };
        return (
          typeof obj.razon_social === 'string' &&
          obj.razon_social.toLowerCase() === CLIENTE_MOSTRADOR.toLowerCase() &&
          typeof obj.id_cliente === 'string' &&
          obj.id_cliente.length > 0
        );
      }) as { id_cliente: string } | undefined;
      if (encontrado) return encontrado.id_cliente;
    }
    return null;
  };

  const resolverAlmacenCacheado = (): string | undefined => {
    const almacenes = queryClient.getQueryData<Almacen[]>(['pos', 'almacenes']);
    if (!Array.isArray(almacenes) || almacenes.length === 0) return undefined;
    const activos = almacenes.filter((a) => a.id_empresa === empresaId && a.activo !== false);
    return (activos[0] ?? almacenes[0])?.id_almacen;
  };

  const refrescarColaOffline = useCallback(async () => {
    const items = await listOutboxItems();
    setOutboxItems(items);
  }, []);

  const poster = useMemo<SalePoster | null>(() => {
    if (!online || !sesion) return null;
    return (endpoint, payload, idempotencyKey) =>
      post(endpoint, payload, {
        headers: { [IDEMPOTENCY_HEADER]: idempotencyKey },
      });
  }, [online, sesion]);

  const { flushing, lastResult, flushNow } = useOutboxFlush(poster);

  useEffect(() => {
    void refrescarColaOffline();
  }, [refrescarColaOffline]);

  useEffect(() => {
    void refrescarColaOffline();
    if (!lastResult) return;
    if (lastResult.enviados > 0) {
      void queryClient.invalidateQueries({ queryKey: ['pos', 'productos'] });
      const folios = (lastResult.sincronizadas ?? [])
        .map((s) => s.numeroNota ?? s.idNotaVenta)
        .filter((v): v is string => Boolean(v));
      const conStockNeg = (lastResult.sincronizadas ?? []).some((s) => s.alertaStockNegativo);
      const detalle = folios.length > 0 ? ` (${folios.join(', ')})` : '';
      setAvisoSync({
        tipo: conStockNeg ? 'warning' : 'success',
        texto: conStockNeg
          ? `${lastResult.enviados} venta(s) sincronizada(s)${detalle} con stock negativo permitido.`
          : `${lastResult.enviados} venta(s) offline sincronizada(s)${detalle}.`,
      });
    }
  }, [lastResult, queryClient, refrescarColaOffline]);

  /** Paso 1 del cobro: crear la nota online o preparar cobro offline provisional. */
  const iniciarCobro = async () => {
    setErrorVenta(null);
    if (carrito.length === 0) return;
    if (!sesion) {
      setSesionDialogOpen(true);
      return;
    }
    // Si la nota ya se creó (reintento tras fallo de pagos), no recrearla.
    if (notaCreada?.id_nota_venta) {
      setModoOffline(false);
      setPagoDialogOpen(true);
      return;
    }
    if (!online) {
      const cachedCliente = obtenerClienteOfflineDesdeCache();
      if (!cachedCliente) {
        setErrorVenta(
          'No hay cliente de mostrador en caché local para vender sin conexión. Conéctate brevemente para sincronizar el catálogo.',
        );
        return;
      }
      if (!notaKeyRef.current) notaKeyRef.current = newIdempotencyKey();
      setClienteOfflineId(cachedCliente);
      setModoOffline(true);
      setPagoDialogOpen(true);
      return;
    }
    setCreandoNota(true);
    let idClienteResuelto: string | null = null;
    try {
      idClienteResuelto = await obtenerClienteMostrador();
      const detalles = carrito.map((item) => ({
        id_producto: item.id_producto,
        cantidad: item.cantidad,
        precio_unitario: item.precio,
        subtotal: toFixedStr(subtotalLinea(item.cantidad, item.precio)),
      }));
      const payload = {
        fecha_emision: new Date().toISOString().slice(0, 10),
        id_empresa: empresaId,
        id_sucursal: sesion.caja_fisica_principal.sucursal.id_sucursal,
        id_cliente: { id_cliente: idClienteResuelto },
        id_caja: sesion.caja_fisica_principal.id_caja,
        observaciones: 'Venta POS mostrador',
        detalles,
      };
      if (!notaKeyRef.current) notaKeyRef.current = newIdempotencyKey();
      const creada = await post<NotaVentaCreada>('/ventas/notas-venta/', payload, {
        headers: { [IDEMPOTENCY_HEADER]: notaKeyRef.current },
      });
      setNotaCreada(creada);
      setModoOffline(false);
      setPagoDialogOpen(true);
    } catch (err) {
      const falloRed = !navigator.onLine || esFalloConexionO5xx(err);
      if (falloRed) {
        const cachedCliente = idClienteResuelto ?? obtenerClienteOfflineDesdeCache();
        if (!cachedCliente) {
          setErrorVenta(
            'Sin conexión y sin cliente de mostrador en caché local. Conéctate brevemente para sincronizar el catálogo antes de vender offline.',
          );
          return;
        }
        if (!notaKeyRef.current) notaKeyRef.current = newIdempotencyKey();
        setClienteOfflineId(cachedCliente);
        setModoOffline(true);
        setPagoDialogOpen(true);
        return;
      }
      const status = statusDeError(err);
      if (status !== undefined && status >= 400 && status < 500) {
        setErrorVenta(mensajeDeError(err, 'No se pudo registrar la venta.'));
      } else {
        setErrorVenta('No se pudo registrar la venta. Revisa la conexión e intenta de nuevo.');
      }
    } finally {
      setCreandoNota(false);
    }
  };

  const totalDocumento: Decimal =
    !modoOffline && notaCreada?.monto_total != null ? D(notaCreada.monto_total) : subtotal;
  const ivaDocumento: Decimal = !modoOffline ? D(notaCreada?.monto_impuesto ?? 0) : D(0);

  /** Paso 2 del cobro: registrar pagos online o confirmar/encolar sobre atómico offline. */
  const confirmarPagos = async (pagos: PosPago[], vueltoCalculado: string) => {
    if (!modoOffline && !notaCreada?.id_nota_venta) return;
    // Defensa en profundidad: lo pagado (convertido a la moneda del
    // documento) debe cubrir el total del documento (o provisional offline).
    const pagado = totalPagado(pagos, codigoIsoDocumento);
    if (pagado.lessThan(totalDocumento)) {
      setErrorVenta('El total pagado no cubre el total de la venta. Revisa los pagos.');
      return;
    }
    setProcesandoPagos(true);
    setErrorVenta(null);
    try {
      if (modoOffline || !notaCreada?.id_nota_venta) {
        const idCliente = clienteOfflineId ?? obtenerClienteOfflineDesdeCache();
        if (!idCliente || !sesion) {
          setErrorVenta('Faltan datos locales de cliente o sesión para registrar la venta offline.');
          return;
        }
        const clientUuid = notaKeyRef.current ?? newIdempotencyKey();
        notaKeyRef.current = clientUuid;
        const idAlmacen = resolverAlmacenCacheado();
        const envelope = buildVentaOfflineEnvelope(
          {
            id_sucursal: sesion.caja_fisica_principal.sucursal.id_sucursal,
            ...(idAlmacen ? { id_almacen: idAlmacen } : {}),
            id_caja: sesion.caja_fisica_principal.id_caja,
            id_cliente: idCliente,
            detalles: carrito.map((item) => ({
              id_producto: item.id_producto,
              cantidad: String(item.cantidad),
              precio_unitario: String(item.precio),
            })),
            pagos: pagos.map((p) => ({
              id_metodo_pago: p.id_metodo_pago,
              id_moneda: p.id_moneda,
              monto: String(p.monto),
              tasa: String(p.tasa),
              ...(p.referencia ? { referencia: p.referencia } : {}),
              id_caja_fisica: sesion.caja_fisica_principal.id_caja,
            })),
            totales_cliente: {
              subtotal: toFixedStr(subtotal),
              iva: '0.00',
              total: toFixedStr(subtotal),
            },
          },
          { clientUuid },
        );

        if (online) {
          try {
            const resp = await post<SyncPushVentaResponse>(
              '/sync/push/ventas/',
              envelope as unknown as Record<string, unknown>,
              { headers: { [IDEMPOTENCY_HEADER]: envelope.client_uuid } },
            );
            if (resp.alerta_stock_negativo) {
              setAvisoSync({
                tipo: 'warning',
                texto: `Venta ${resp.numero_nota ?? ''} confirmada con stock negativo permitido.`,
              });
            }
            void queryClient.invalidateQueries({ queryKey: ['pos', 'productos'] });
            setRecibo({
              numero: resp.numero_nota ?? `POS-${envelope.client_uuid.slice(0, 8)}`,
              fecha: new Date().toLocaleString(),
              empresaNombre: sesion.caja_fisica_principal.sucursal.empresa.nombre ?? '',
              cajaNombre: sesion.caja_fisica_principal.nombre ?? '',
              items: carrito,
              subtotal: toFixedStr(subtotal),
              montoImpuesto: '0.00',
              total: resp.total != null ? toFixedStr(resp.total) : toFixedStr(subtotal),
              pagos,
              vuelto: vueltoCalculado,
              codigoIso: codigoIsoDocumento,
            });
            setPagoDialogOpen(false);
            return;
          } catch (err) {
            const status = statusDeError(err);
            if (status !== undefined && status >= 400 && status < 500) {
              setErrorVenta(mensajeDeError(err, 'La venta fue rechazada por el servidor.'));
              return;
            }
            // Fallo de red / 5xx: degradar de forma segura al outbox sin perder la venta.
          }
        }

        const folioProvisional = `POS-${envelope.client_uuid.slice(0, 8)}`;
        await enqueueSale({
          idempotencyKey: envelope.client_uuid,
          endpoint: '/sync/push/ventas/',
          payload: envelope as unknown as Record<string, unknown>,
          createdAt: Date.now(),
          estado: 'PENDIENTE',
          folioProvisional,
          totalProvisional: toFixedStr(subtotal),
          codigoIso: codigoIsoDocumento,
        });
        await refrescarColaOffline();
        setRecibo({
          numero: folioProvisional,
          provisionalOffline: true,
          fecha: new Date().toLocaleString(),
          empresaNombre: sesion.caja_fisica_principal.sucursal.empresa.nombre ?? '',
          cajaNombre: sesion.caja_fisica_principal.nombre ?? '',
          items: carrito,
          subtotal: toFixedStr(subtotal),
          montoImpuesto: '0.00',
          total: toFixedStr(subtotal),
          pagos,
          vuelto: vueltoCalculado,
          codigoIso: codigoIsoDocumento,
        });
        setPagoDialogOpen(false);
        return;
      }

      for (const pago of pagos) {
        await pagosService.createPagoDocumento(
          'NOTA_VENTA',
          notaCreada!.id_nota_venta!,
          {
            monto: pago.monto,
            id_metodo_pago: pago.id_metodo_pago,
            id_moneda: pago.id_moneda,
            tasa: pago.tasa,
            referencia: pago.referencia,
            id_caja_fisica: sesion?.caja_fisica_principal.id_caja,
          },
          pago.idempotencyKey,
        );
      }
      setRecibo({
        numero: notaCreada!.numero_nota_venta ?? '',
        fecha: new Date().toLocaleString(),
        empresaNombre: sesion?.caja_fisica_principal.sucursal.empresa.nombre ?? '',
        cajaNombre: sesion?.caja_fisica_principal.nombre ?? '',
        items: carrito,
        subtotal: toFixedStr(subtotal),
        montoImpuesto: toFixedStr(ivaDocumento),
        total: toFixedStr(totalDocumento),
        pagos,
        vuelto: vueltoCalculado,
        codigoIso: codigoIsoDocumento,
      });
      setPagoDialogOpen(false);
    } catch {
      setErrorVenta('Error al registrar los pagos. Puedes reintentar: los pagos no se duplican.');
    } finally {
      setProcesandoPagos(false);
    }
  };

  const nuevaVenta = () => {
    notaKeyRef.current = null;
    setNotaCreada(null);
    setModoOffline(false);
    setClienteOfflineId(null);
    setRecibo(null);
    setCarrito([]);
    setBusqueda('');
    setErrorVenta(null);
    searchRef.current?.focus();
  };

  const handleSincronizarAhora = async () => {
    await flushNow();
    await refrescarColaOffline();
  };

  const handleReintentar = async (idempotencyKey: string) => {
    await retryOutboxItem(idempotencyKey);
    await refrescarColaOffline();
    if (online && poster) {
      await flushNow();
      await refrescarColaOffline();
    }
  };

  const handleDescartar = async (idempotencyKey: string) => {
    await discardOutboxItem(idempotencyKey);
    await refrescarColaOffline();
  };

  const handleLimpiarSincronizadas = async () => {
    await clearSyncedOutboxItems();
    await refrescarColaOffline();
  };

  const pendientesCount = outboxItems.filter((i) => (i.estado ?? 'PENDIENTE') === 'PENDIENTE').length;
  const revisionCount = outboxItems.filter((i) => i.estado === 'REQUIERE_REVISION').length;

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', bgcolor: 'grey.100' }}>
      <AppBar position="static" color="primary">
        <Toolbar variant="dense">
          <IconButton color="inherit" edge="start" aria-label="Volver" onClick={() => navigate('/ventas/notas-venta')}>
            <ArrowBackIcon />
          </IconButton>
          <PointOfSaleIcon sx={{ mx: 1 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>POS de mostrador</Typography>
          {(outboxItems.length > 0 || !online) && (
            <Button
              color="inherit"
              size="small"
              variant={revisionCount > 0 || pendientesCount > 0 ? 'outlined' : 'text'}
              startIcon={!online ? <CloudOffIcon /> : revisionCount > 0 ? <WarningAmberIcon /> : <SyncIcon />}
              sx={{ mr: 2 }}
              onClick={() => setColaDialogOpen(true)}
              data-testid="pos-cola-offline-btn"
            >
              {`Cola offline (${pendientesCount} por confirmar / ${revisionCount} por revisar)`}
            </Button>
          )}
          <Button
            color="inherit"
            size="small"
            startIcon={<ReplayIcon />}
            sx={{ mr: 2 }}
            onClick={() => {
              if (!sesion) {
                setSesionDialogOpen(true);
                return;
              }
              setDevolucionDialogOpen(true);
            }}
            data-testid="pos-abrir-devolucion"
          >
            {t('ventas.pos.devolucion.boton')}
          </Button>
          <Typography variant="body2" data-testid="pos-estado-sesion">
            {cargandoSesion
              ? 'Verificando caja…'
              : sesion
                ? `Caja: ${sesion.caja_fisica_principal.nombre}`
                : 'Sin sesión de caja'}
          </Typography>
          {!cargandoSesion && !sesion && (
            <Button color="inherit" size="small" sx={{ ml: 1 }} onClick={() => setSesionDialogOpen(true)}>
              Abrir caja
            </Button>
          )}
        </Toolbar>
      </AppBar>

      {!online && (
        <Alert severity="warning" sx={{ mx: 2, mt: 1.5 }} data-testid="pos-offline-alerta">
          Sin conexión — las ventas se guardarán en la cola offline con folio provisional.
        </Alert>
      )}
      {revisionCount > 0 && (
        <Alert
          severity="error"
          sx={{ mx: 2, mt: 1.5 }}
          data-testid="pos-cola-alerta-revision"
          action={
            <Button color="inherit" size="small" onClick={() => setColaDialogOpen(true)}>
              Revisar
            </Button>
          }
        >
          {`${revisionCount} venta(s) offline requieren revisión.`}
        </Alert>
      )}
      {avisoSync && (
        <Alert
          severity={avisoSync.tipo}
          sx={{ mx: 2, mt: 1.5 }}
          onClose={() => setAvisoSync(null)}
          data-testid="pos-cola-alerta-sync"
        >
          {avisoSync.texto}
        </Alert>
      )}

      <Box sx={{ display: 'flex', flex: 1, gap: 2, p: 2, alignItems: 'stretch', flexDirection: { xs: 'column', md: 'row' } }}>
        {/* Columna de productos */}
        <Box sx={{ flex: 2, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <TextField
            fullWidth
            autoFocus
            inputRef={searchRef}
            placeholder="Buscar producto o escanear código de barras…"
            value={busqueda}
            onChange={(e) => { setBusqueda(e.target.value); setScanError(''); }}
            onKeyDown={handleSearchKeyDown}
            // El lector USB escribe aquí: re-enfocar al perder el foco mantiene
            // el POS siempre listo para el siguiente escaneo.
            onBlur={() => setTimeout(() => searchRef.current?.focus(), 0)}
            slotProps={{ htmlInput: { 'data-testid': 'pos-busqueda', 'aria-label': 'Buscar producto o escanear código' } }}
            sx={{ mb: 2, bgcolor: 'background.paper' }}
          />
          {scanError && <Alert severity="warning" sx={{ mb: 1 }} data-testid="pos-scan-error">{scanError}</Alert>}
          <Box
            sx={{
              display: 'grid', gap: 1.5, overflowY: 'auto',
              gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
            }}
            data-testid="pos-grilla-productos"
          >
            {productosFiltrados.map((p) => (
              <Card key={p.id_producto}>
                <CardActionArea onClick={() => agregarAlCarrito(p)} sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="subtitle2" noWrap>{p.nombre_producto}</Typography>
                    {p.sku && <Typography variant="caption" color="text.secondary">SKU: {p.sku}</Typography>}
                    <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                      {toFixedStr(p.precio_venta_sugerido ?? 0)} {codigoIsoDocumento}
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
            {productosFiltrados.length === 0 && (
              <Typography color="text.secondary">Sin productos para mostrar.</Typography>
            )}
          </Box>
        </Box>

        {/* Carrito */}
        <Box sx={{ flex: 1, minWidth: 320, display: 'flex', flexDirection: 'column', bgcolor: 'background.paper', borderRadius: 1, p: 2 }}>
          <Typography variant="h6" gutterBottom>Carrito</Typography>
          <Box sx={{ flex: 1, overflowY: 'auto' }} data-testid="pos-carrito">
            {carrito.length === 0 && (
              <Typography color="text.secondary">Escanea o toca un producto para agregarlo.</Typography>
            )}
            {carrito.map((item) => (
              <Stack key={item.id_producto} direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" noWrap>{item.nombre}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {toFixedStr(item.precio)} c/u
                  </Typography>
                </Box>
                <TextField
                  size="small"
                  value={item.cantidad}
                  onChange={(e) => cambiarCantidad(item.id_producto, e.target.value)}
                  slotProps={{ htmlInput: { inputMode: 'decimal', 'aria-label': `Cantidad ${item.nombre}`, style: { width: 56, textAlign: 'center' } } }}
                />
                <Typography variant="body2" sx={{ width: 88, textAlign: 'right' }} data-testid={`pos-linea-total-${item.id_producto}`}>
                  {toFixedStr(D(item.cantidad).times(D(item.precio)))}
                </Typography>
                <IconButton size="small" aria-label={`Quitar ${item.nombre}`} onClick={() => quitarItem(item.id_producto)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
          </Box>
          <Divider sx={{ my: 1 }} />
          <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
            <Typography>Subtotal</Typography>
            <Typography data-testid="pos-subtotal">{toFixedStr(subtotal)} {codigoIsoDocumento}</Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>
            El IVA lo calcula el sistema al cobrar.
          </Typography>
          {errorVenta && <Alert severity="error" sx={{ mb: 1 }} data-testid="pos-error">{errorVenta}</Alert>}
          <Button
            variant="contained"
            size="large"
            disabled={carrito.length === 0 || creandoNota || cargandoSesion}
            onClick={() => void iniciarCobro()}
            data-testid="pos-cobrar"
          >
            {creandoNota ? 'Registrando…' : `Cobrar ${toFixedStr(subtotal)} ${codigoIsoDocumento}`}
          </Button>
        </Box>
      </Box>

      <PosSesionDialog
        open={sesionDialogOpen}
        empresaId={empresaId}
        onClose={() => setSesionDialogOpen(false)}
        onAbierta={() => {
          setSesionDialogOpen(false);
          void queryClient.invalidateQueries({ queryKey: ['pos', 'sesion-activa'] });
        }}
      />

      <PosPagoDialog
        open={pagoDialogOpen}
        total={totalDocumento}
        montoImpuesto={ivaDocumento}
        codigoIsoDocumento={codigoIsoDocumento}
        metodos={metodos}
        monedas={monedas}
        tasaBcv={tasaBcv}
        procesando={procesandoPagos}
        modoOffline={modoOffline}
        error={errorVenta}
        onConfirm={(pagos, vueltoCalculado) => void confirmarPagos(pagos, vueltoCalculado)}
        onClose={() => setPagoDialogOpen(false)}
      />

      <PosColaOfflinePanel
        open={colaDialogOpen}
        items={outboxItems}
        online={online}
        flushing={flushing}
        onClose={() => setColaDialogOpen(false)}
        onSincronizarAhora={() => void handleSincronizarAhora()}
        onReintentar={(key) => void handleReintentar(key)}
        onDescartar={(key) => void handleDescartar(key)}
        onLimpiarSincronizadas={() => void handleLimpiarSincronizadas()}
      />

      <PosRecibo open={!!recibo} recibo={recibo} onNuevaVenta={nuevaVenta} />

      <PosDevolucionDialog
        open={devolucionDialogOpen}
        codigoIsoDocumento={codigoIsoDocumento}
        metodos={metodos}
        onClose={() => setDevolucionDialogOpen(false)}
        onRegistrada={(datos) => {
          setDevolucionDialogOpen(false);
          setReciboDevolucion(datos);
        }}
      />
      <PosReciboDevolucion
        open={!!reciboDevolucion}
        recibo={reciboDevolucion}
        empresaNombre={sesion?.caja_fisica_principal.sucursal.empresa.nombre ?? ''}
        onCerrar={() => {
          setReciboDevolucion(null);
          searchRef.current?.focus();
        }}
      />
    </Box>
  );
}
