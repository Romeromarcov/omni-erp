import { useState, type SyntheticEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import AddShoppingCartOutlined from '@mui/icons-material/AddShoppingCartOutlined';
import GpsFixedOutlined from '@mui/icons-material/GpsFixedOutlined';
import PaymentsOutlined from '@mui/icons-material/PaymentsOutlined';
import StorefrontOutlined from '@mui/icons-material/StorefrontOutlined';
import TrendingUpOutlined from '@mui/icons-material/TrendingUpOutlined';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';
import {
  portalVendedorService,
  type CarteraClienteItem,
  type CatalogoProductoPortalItem,
  type ResultadoVisitaGPS,
} from '../../services/portalesService';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

interface LineaCarrito {
  producto: CatalogoProductoPortalItem;
  cantidad: string;
}

const RESULTADOS_VISITA: { value: ResultadoVisitaGPS; label: string }[] = [
  { value: 'EFECTIVA', label: 'Visita efectiva' },
  { value: 'COBRANZA', label: 'Gestión de cobranza' },
  { value: 'SIN_STOCK', label: 'Sin pedido / sin stock' },
  { value: 'CERRADO', label: 'Local cerrado' },
  { value: 'REPROGRAMADA', label: 'Reprogramada' },
];

export default function PortalVendedorPage() {
  const empresaId = getEmpresaId();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState(0);
  const [busqueda, setBusqueda] = useState('');
  const [clienteSel, setClienteSel] = useState<CarteraClienteItem | null>(null);
  const [feedback, setFeedback] = useState<{ tipo: 'success' | 'error'; msg: string } | null>(null);

  // Check-in GPS
  const [lat, setLat] = useState('10.481000');
  const [lng, setLng] = useState('-66.858000');
  const [resultadoVisita, setResultadoVisita] = useState<ResultadoVisitaGPS>('EFECTIVA');
  const [notasVisita, setNotasVisita] = useState('');

  // Carrito de pedido móvil
  const [carrito, setCarrito] = useState<LineaCarrito[]>([]);
  const [obsPedido, setObsPedido] = useState('');
  const [refExtPedido, setRefExtPedido] = useState('');

  // Reporte de cobro en campo
  const [cobroMonto, setCobroMonto] = useState('');
  const [cobroMonedaId, setCobroMonedaId] = useState('');
  const [cobroMetodoId, setCobroMetodoId] = useState('');
  const [cobroTasa, setCobroTasa] = useState('1.0000');
  const [cobroRef, setCobroRef] = useState('');
  const [cobroUrl, setCobroUrl] = useState('');
  const [cobroObs, setCobroObs] = useState('');

  const { data: carteraData, isLoading: loadingCartera } = useQuery({
    queryKey: ['portal-vendedor', 'cartera', empresaId],
    queryFn: () => portalVendedorService.getCartera(empresaId ?? undefined),
  });

  const { data: catalogoData, isLoading: loadingCatalogo } = useQuery({
    queryKey: ['portal-vendedor', 'catalogo', empresaId, busqueda],
    queryFn: () => portalVendedorService.getCatalogo(busqueda || undefined, empresaId ?? undefined),
  });

  const { data: metasData } = useQuery({
    queryKey: ['portal-vendedor', 'metas', empresaId],
    queryFn: () => portalVendedorService.getMetasComisiones(empresaId ?? undefined),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: ['portal-vendedor', 'monedas', empresaId],
    queryFn: portalVendedorService.getMonedasCatalogo,
  });

  const { data: metodos = [] } = useQuery({
    queryKey: ['portal-vendedor', 'metodos-pago', empresaId],
    queryFn: portalVendedorService.getMetodosPagoCatalogo,
  });

  const checkinMut = useMutation({
    mutationFn: () => {
      if (!clienteSel) throw new Error('Selecciona un cliente de tu cartera.');
      return portalVendedorService.registrarCheckin({
        id_cliente: clienteSel.id_cliente,
        latitud: lat,
        longitud: lng,
        resultado: resultadoVisita,
        notas: notasVisita,
      });
    },
    onSuccess: (res) => {
      const dist = res.distancia_cliente_m ? ` · distancia ${res.distancia_cliente_m} m` : '';
      setFeedback({ tipo: 'success', msg: `Check-in registrado (${res.resultado}${dist}).` });
      setNotasVisita('');
    },
    onError: (err) => setFeedback({ tipo: 'error', msg: mensajeDeError(err) }),
  });

  const pedidoMut = useMutation({
    mutationFn: () => {
      if (!clienteSel) throw new Error('Selecciona un cliente para el pedido.');
      if (carrito.length === 0) throw new Error('Agrega al menos un producto al carrito.');
      return portalVendedorService.crearPedido({
        id_cliente: clienteSel.id_cliente,
        observaciones: obsPedido,
        referencia_externa: refExtPedido,
        lineas: carrito.map((l) => ({ id_producto: l.producto.id_producto, cantidad: l.cantidad })),
      });
    },
    onSuccess: (res) => {
      setFeedback({
        tipo: 'success',
        msg: `Pedido ${res.numero_pedido} creado (${res.estado}) · Total est. ${res.total_estimado}.`,
      });
      setCarrito([]);
      setObsPedido('');
      setRefExtPedido('');
      void queryClient.invalidateQueries({ queryKey: ['portal-vendedor', 'catalogo'] });
    },
    onError: (err) => setFeedback({ tipo: 'error', msg: mensajeDeError(err) }),
  });

  const cobroMut = useMutation({
    mutationFn: () => {
      if (!clienteSel) throw new Error('Selecciona un cliente de tu cartera.');
      return portalVendedorService.reportarCobro({
        id_cliente: clienteSel.id_cliente,
        monto: cobroMonto,
        id_moneda: cobroMonedaId,
        id_metodo_pago: cobroMetodoId,
        tasa: cobroTasa || '1.0000',
        referencia: cobroRef,
        comprobante_url: cobroUrl,
        observaciones: cobroObs,
      });
    },
    onSuccess: (res) => {
      setFeedback({
        tipo: 'success',
        msg: `Cobro ${res.id_pago_portal} reportado por ${res.monto} ${res.moneda} (${res.estado}).`,
      });
      setCobroMonto('');
      setCobroRef('');
      setCobroUrl('');
      setCobroObs('');
      void queryClient.invalidateQueries({ queryKey: ['portal-vendedor', 'cartera'] });
    },
    onError: (err) => setFeedback({ tipo: 'error', msg: mensajeDeError(err) }),
  });

  const agregarAlCarrito = (producto: CatalogoProductoPortalItem) => {
    setCarrito((prev) => {
      const idx = prev.findIndex((i) => i.producto.id_producto === producto.id_producto);
      if (idx >= 0) {
        return prev.map((item, i) =>
          i === idx ? { ...item, cantidad: String(Number(item.cantidad || '0') + 1) } : item,
        );
      }
      return [...prev, { producto, cantidad: '1' }];
    });
    setFeedback({ tipo: 'success', msg: `${producto.nombre_producto} agregado al pedido.` });
  };

  const capturarGPS = () => {
    if (!navigator?.geolocation) {
      setFeedback({ tipo: 'error', msg: 'Tu navegador no soporta geolocalización; ingresa lat/lng manual.' });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLng(pos.coords.longitude.toFixed(6));
        setFeedback({ tipo: 'success', msg: 'Coordenadas GPS capturadas.' });
      },
      () => setFeedback({ tipo: 'error', msg: 'No se pudo obtener GPS; usa coordenadas manuales.' }),
    );
  };

  const clientes = carteraData?.clientes ?? [];
  const productos = catalogoData?.productos ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Portal de Vendedores (SFA)"
        subtitle="Cartera asignada, catálogo trimonetario, check-in GPS, pedidos en campo y metas"
      />

      {feedback && (
        <Alert severity={feedback.tipo} onClose={() => setFeedback(null)} sx={{ mb: 2 }}>
          {feedback.msg}
        </Alert>
      )}

      {clienteSel && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Cliente activo: <strong>{clienteSel.razon_social}</strong> ({clienteSel.rif}) · Saldo CxC{' '}
          <strong>${clienteSel.saldo_pendiente}</strong> · Límite ${clienteSel.limite_credito}
        </Alert>
      )}

      <Tabs
        value={tab}
        onChange={(_e: SyntheticEvent, v: number) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label={`Cartera (${clientes.length})`} />
        <Tab label={`Catálogo (${productos.length})`} />
        <Tab label="Check-in GPS" />
        <Tab label={`Pedido y Cobro (${carrito.length})`} />
        <Tab label="Metas y Comisiones" />
      </Tabs>

      {tab === 0 && (
        <Grid container spacing={2}>
          {loadingCartera && (
            <Grid size={{ xs: 12 }}>
              <Typography color="text.secondary">Cargando cartera asignada…</Typography>
            </Grid>
          )}
          {clientes.map((c) => (
            <Grid size={{ xs: 12, md: 6, lg: 4 }} key={c.id_cliente}>
              <Card variant={clienteSel?.id_cliente === c.id_cliente ? 'outlined' : 'elevation'}>
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="subtitle1" fontWeight={600}>
                      {c.razon_social}
                    </Typography>
                    <StatusChip
                      value={c.bloquear_por_mora ? 'en_mora' : c.cuentas_vencidas > 0 ? 'vencida' : 'vigente'}
                      label={c.bloquear_por_mora ? 'En mora' : c.cuentas_vencidas > 0 ? 'Vencida' : 'Al día'}
                      colorMap={{ en_mora: 'error', vencida: 'warning', vigente: 'success' }}
                    />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    RIF: {c.rif} · Tipo: {c.tipo_cliente}
                  </Typography>
                  <Typography variant="body2" mt={1}>
                    Saldo pendiente: <strong>${c.saldo_pendiente}</strong> · CxC vencidas: {c.cuentas_vencidas}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Límite de crédito: ${c.limite_credito}
                  </Typography>
                  <Stack direction="row" spacing={1} mt={2}>
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => {
                        setClienteSel(c);
                        setTab(2);
                      }}
                    >
                      Operar cliente
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => {
                        setClienteSel(c);
                        setTab(3);
                      }}
                    >
                      Nuevo pedido
                    </Button>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {tab === 1 && (
        <Box>
          <TextField
            label="Buscar por nombre, SKU o código de barras"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            fullWidth
            size="small"
            sx={{ mb: 2 }}
          />
          {loadingCatalogo && <Typography color="text.secondary">Cargando catálogo…</Typography>}
          <Grid container spacing={2}>
            {productos.map((p) => (
              <Grid size={{ xs: 12, md: 6, lg: 4 }} key={p.id_producto}>
                <Card>
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                      <Box>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {p.nombre_producto}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          SKU: {p.sku || 'N/A'} · Stock disp.: {p.stock_disponible}
                        </Typography>
                      </Box>
                      <Chip icon={<StorefrontOutlined />} label={`${p.precio} ${p.moneda_precio}`} color="primary" size="small" />
                    </Stack>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="caption" display="block" color="text.secondary">
                      Fiscal ({p.equivalencias_trimonetarias.pais_fiscal_iso ?? 'VES'}):{' '}
                      <strong>{p.equivalencias_trimonetarias.pais_fiscal ?? 'N/D'}</strong> · Ref (
                      {p.equivalencias_trimonetarias.referencia_iso ?? 'USDT'}):{' '}
                      <strong>{p.equivalencias_trimonetarias.referencia ?? 'N/D'}</strong>
                    </Typography>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<AddShoppingCartOutlined />}
                      sx={{ mt: 1.5 }}
                      onClick={() => agregarAlCarrito(p)}
                    >
                      Agregar al pedido
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {tab === 2 && (
        <Card sx={{ maxWidth: 640 }}>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h6">Check-in GPS en Cliente</Typography>
              <TextField
                select
                label="Cliente de cartera"
                value={clienteSel?.id_cliente ?? ''}
                onChange={(e) => {
                  const found = clientes.find((c) => c.id_cliente === e.target.value) ?? null;
                  setClienteSel(found);
                }}
                size="small"
              >
                {clientes.map((c) => (
                  <MenuItem key={c.id_cliente} value={c.id_cliente}>
                    {c.razon_social} ({c.rif})
                  </MenuItem>
                ))}
              </TextField>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField label="Latitud" value={lat} onChange={(e) => setLat(e.target.value)} size="small" fullWidth />
                <TextField label="Longitud" value={lng} onChange={(e) => setLng(e.target.value)} size="small" fullWidth />
                <Button variant="outlined" startIcon={<GpsFixedOutlined />} onClick={capturarGPS}>
                  Usar GPS
                </Button>
              </Stack>
              <TextField
                select
                label="Resultado de la visita"
                value={resultadoVisita}
                onChange={(e) => setResultadoVisita(e.target.value as ResultadoVisitaGPS)}
                size="small"
              >
                {RESULTADOS_VISITA.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Notas de campo"
                value={notasVisita}
                onChange={(e) => setNotasVisita(e.target.value)}
                multiline
                rows={2}
                size="small"
              />
              <Button variant="contained" onClick={() => checkinMut.mutate()} disabled={checkinMut.isPending}>
                Registrar Check-in GPS
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}

      {tab === 3 && (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Levantar Pedido Rápido</Typography>
                  <TextField
                    select
                    label="Cliente"
                    value={clienteSel?.id_cliente ?? ''}
                    onChange={(e) => setClienteSel(clientes.find((c) => c.id_cliente === e.target.value) ?? null)}
                    size="small"
                  >
                    {clientes.map((c) => (
                      <MenuItem key={c.id_cliente} value={c.id_cliente}>
                        {c.razon_social} ({c.rif})
                      </MenuItem>
                    ))}
                  </TextField>
                  {carrito.map((item) => (
                    <Stack key={item.producto.id_producto} direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2" sx={{ flex: 1 }}>
                        {item.producto.nombre_producto} ({item.producto.precio})
                      </Typography>
                      <TextField
                        label="Cant."
                        value={item.cantidad}
                        onChange={(e) =>
                          setCarrito((prev) =>
                            prev.map((l) =>
                              l.producto.id_producto === item.producto.id_producto
                                ? { ...l, cantidad: e.target.value }
                                : l,
                            ),
                          )
                        }
                        size="small"
                        sx={{ width: 96 }}
                      />
                    </Stack>
                  ))}
                  <TextField
                    label="Observaciones pedido"
                    value={obsPedido}
                    onChange={(e) => setObsPedido(e.target.value)}
                    size="small"
                  />
                  <TextField
                    label="Referencia externa (offline)"
                    value={refExtPedido}
                    onChange={(e) => setRefExtPedido(e.target.value)}
                    size="small"
                  />
                  <Button variant="contained" onClick={() => pedidoMut.mutate()} disabled={pedidoMut.isPending}>
                    Enviar Pedido
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          <Grid size={{ xs: 12, md: 6 }}>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h6">Reportar Cobro en Campo</Typography>
                  <TextField label="Monto cobrado" value={cobroMonto} onChange={(e) => setCobroMonto(e.target.value)} size="small" />
                  <TextField
                    select
                    label="Moneda"
                    value={cobroMonedaId}
                    onChange={(e) => setCobroMonedaId(e.target.value)}
                    size="small"
                  >
                    {monedas.map((m) => (
                      <MenuItem key={m.id_moneda} value={m.id_moneda}>
                        {m.codigo_iso} - {m.nombre}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    select
                    label="Método de pago"
                    value={cobroMetodoId}
                    onChange={(e) => setCobroMetodoId(e.target.value)}
                    size="small"
                  >
                    {metodos.map((mp) => (
                      <MenuItem key={mp.id_metodo_pago} value={mp.id_metodo_pago}>
                        {mp.nombre_metodo} ({mp.tipo_metodo})
                      </MenuItem>
                    ))}
                  </TextField>
                  <Stack direction="row" spacing={1}>
                    <TextField label="Tasa" value={cobroTasa} onChange={(e) => setCobroTasa(e.target.value)} size="small" fullWidth />
                    <TextField label="Referencia" value={cobroRef} onChange={(e) => setCobroRef(e.target.value)} size="small" fullWidth />
                  </Stack>
                  <TextField
                    label="URL foto comprobante (https://...)"
                    value={cobroUrl}
                    onChange={(e) => setCobroUrl(e.target.value)}
                    size="small"
                  />
                  <TextField
                    label="Observaciones cobro"
                    value={cobroObs}
                    onChange={(e) => setCobroObs(e.target.value)}
                    size="small"
                  />
                  <Button
                    variant="contained"
                    color="secondary"
                    startIcon={<PaymentsOutlined />}
                    onClick={() => cobroMut.mutate()}
                    disabled={cobroMut.isPending}
                  >
                    Registrar Cobro
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tab === 4 && (
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <Card sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="caption" color="text.secondary">
                  Comisiones devengadas
                </Typography>
                <Typography variant="h5" fontWeight={700}>
                  ${metasData?.total_devengado ?? '0.0000'}
                </Typography>
              </CardContent>
            </Card>
            <Card sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="caption" color="text.secondary">
                  Comisiones liquidadas
                </Typography>
                <Typography variant="h5" fontWeight={700} color="success.main">
                  ${metasData?.total_liquidado ?? '0.0000'}
                </Typography>
              </CardContent>
            </Card>
          </Stack>

          {(metasData?.esquemas ?? []).map((esq) => (
            <Card key={esq.id_esquema_comision}>
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <TrendingUpOutlined color="primary" />
                  <Typography variant="subtitle1" fontWeight={600}>
                    Esquema {esq.modalidad_devengo} · Base {esq.porcentaje_base}% · Meta ${esq.meta_mensual_monto} (+{esq.bono_meta_porcentaje}%)
                  </Typography>
                </Stack>
              </CardContent>
            </Card>
          ))}

          {(metasData?.comisiones ?? []).map((com) => (
            <Card key={com.id_comision_venta} variant="outlined">
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2">
                    {com.nota_venta} · {com.fecha_devengo} ({com.origen_devengo})
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography fontWeight={600}>${com.monto}</Typography>
                    <StatusChip value={com.estado} colorMap={{ liquidada: 'success', devengada: 'info' }} />
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}
    </PageContainer>
  );
}
