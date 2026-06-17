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
import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert, AppBar, Box, Button, Card, CardActionArea, CardContent, Divider,
  IconButton, Stack, TextField, Toolbar, Typography,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DeleteIcon from '@mui/icons-material/Delete';
import PointOfSaleIcon from '@mui/icons-material/PointOfSale';
import ReplayIcon from '@mui/icons-material/Replay';
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
import PosPagoDialog from './PosPagoDialog';
import PosSesionDialog from './PosSesionDialog';
import PosRecibo, { type ReciboData } from './PosRecibo';
import PosDevolucionDialog, { type ReciboDevolucionData } from './PosDevolucionDialog';
import PosReciboDevolucion from './PosReciboDevolucion';
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

export default function PosPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
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
  const productos: Producto[] = useMemo(() => {
    if (!productosData) return [];
    return Array.isArray(productosData) ? productosData : productosData.results ?? [];
  }, [productosData]);

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

  /** Busca (o crea) el cliente genérico de mostrador. */
  const obtenerClienteMostrador = async (): Promise<string> => {
    const encontrados = await buscarClientes(CLIENTE_MOSTRADOR, empresaId);
    const match = encontrados.find(
      (c) => (c as { razon_social?: string }).razon_social?.toLowerCase() === CLIENTE_MOSTRADOR.toLowerCase(),
    );
    if (match?.id_cliente) return match.id_cliente;
    const nuevo = await crearClienteConEmpresa({
      razon_social: CLIENTE_MOSTRADOR,
      rif: 'V000000000',
      telefono: '0000000000',
      id_empresa: empresaId,
    });
    return nuevo.id_cliente;
  };

  /** Paso 1 del cobro: crear la nota de venta (el backend calcula IVA y total). */
  const iniciarCobro = async () => {
    setErrorVenta(null);
    if (carrito.length === 0) return;
    if (!sesion) {
      setSesionDialogOpen(true);
      return;
    }
    // Si la nota ya se creó (reintento tras fallo de pagos), no recrearla.
    if (notaCreada?.id_nota_venta) {
      setPagoDialogOpen(true);
      return;
    }
    setCreandoNota(true);
    try {
      const idCliente = await obtenerClienteMostrador();
      const detalles = carrito.map((item) => ({
        id_producto: item.id_producto,
        cantidad: Number(item.cantidad),
        precio_unitario: Number(item.precio),
        subtotal: subtotalLinea(item.cantidad, item.precio).toNumber(),
      }));
      const payload = {
        fecha_emision: new Date().toISOString().slice(0, 10),
        id_empresa: empresaId,
        id_sucursal: sesion.caja_fisica_principal.sucursal.id_sucursal,
        id_cliente: { id_cliente: idCliente },
        id_caja: sesion.caja_fisica_principal.id_caja,
        observaciones: 'Venta POS mostrador',
        detalles,
      };
      if (!notaKeyRef.current) notaKeyRef.current = newIdempotencyKey();
      const creada = await post<NotaVentaCreada>('/ventas/notas-venta/', payload, {
        headers: { [IDEMPOTENCY_HEADER]: notaKeyRef.current },
      });
      setNotaCreada(creada);
      setPagoDialogOpen(true);
    } catch {
      setErrorVenta('No se pudo registrar la venta. Revisa la conexión e intenta de nuevo.');
    } finally {
      setCreandoNota(false);
    }
  };

  const totalDocumento: Decimal = notaCreada?.monto_total != null ? D(notaCreada.monto_total) : subtotal;
  const ivaDocumento: Decimal = D(notaCreada?.monto_impuesto ?? 0);

  /** Paso 2 del cobro: registrar cada pago con su Idempotency-Key estable. */
  const confirmarPagos = async (pagos: PosPago[], vueltoCalculado: string) => {
    if (!notaCreada?.id_nota_venta) return;
    // Defensa en profundidad: lo pagado (convertido a la moneda del
    // documento) debe cubrir el monto_total que calculó el BACKEND.
    const pagado = totalPagado(pagos, codigoIsoDocumento);
    if (pagado.lessThan(totalDocumento)) {
      setErrorVenta('El total pagado no cubre el total de la venta. Revisa los pagos.');
      return;
    }
    setProcesandoPagos(true);
    setErrorVenta(null);
    try {
      for (const pago of pagos) {
        await pagosService.createPagoDocumento(
          'NOTA_VENTA',
          notaCreada.id_nota_venta,
          {
            monto: Number(pago.monto),
            id_metodo_pago: pago.id_metodo_pago,
            id_moneda: pago.id_moneda,
            tasa: Number(pago.tasa),
            referencia: pago.referencia,
            id_caja_fisica: sesion?.caja_fisica_principal.id_caja,
          },
          pago.idempotencyKey,
        );
      }
      setRecibo({
        numero: notaCreada.numero_nota_venta ?? '',
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
    setRecibo(null);
    setCarrito([]);
    setBusqueda('');
    setErrorVenta(null);
    searchRef.current?.focus();
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', bgcolor: 'grey.100' }}>
      <AppBar position="static" color="primary">
        <Toolbar variant="dense">
          <IconButton color="inherit" edge="start" aria-label="Volver" onClick={() => navigate('/ventas/notas-venta')}>
            <ArrowBackIcon />
          </IconButton>
          <PointOfSaleIcon sx={{ mx: 1 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>POS de mostrador</Typography>
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
        error={errorVenta}
        onConfirm={(pagos, vueltoCalculado) => void confirmarPagos(pagos, vueltoCalculado)}
        onClose={() => setPagoDialogOpen(false)}
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
