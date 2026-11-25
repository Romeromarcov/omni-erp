import { useState, type SyntheticEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Divider,
  Grid,
  Link,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import DownloadOutlined from '@mui/icons-material/DownloadOutlined';
import LocalShippingOutlined from '@mui/icons-material/LocalShippingOutlined';
import LockOutlined from '@mui/icons-material/LockOutlined';
import LogoutOutlined from '@mui/icons-material/LogoutOutlined';
import ReceiptLongOutlined from '@mui/icons-material/ReceiptLongOutlined';
import ShoppingBagOutlined from '@mui/icons-material/ShoppingBagOutlined';
import {
  clearPortalClienteSession,
  getPortalClienteSession,
  portalClienteService,
  safeExternalUrl,
  setPortalClienteSession,
  type CanalOTPPortal,
  type PortalClienteSession,
} from '../../services/portalesService';
import { StatusChip } from '../../components/ui';

export default function PortalClientePage() {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<PortalClienteSession | null>(() => getPortalClienteSession());
  const [feedback, setFeedback] = useState<{ tipo: 'success' | 'error'; msg: string } | null>(null);
  const [tab, setTab] = useState(0);

  // Flujo OTP
  const [rif, setRif] = useState('');
  const [idEmpresa, setIdEmpresa] = useState('');
  const [canal, setCanal] = useState<CanalOTPPortal>('WHATSAPP');
  const [destino, setDestino] = useState('');
  const [idToken, setIdToken] = useState<string | null>(null);
  const [codigoOtp, setCodigoOtp] = useState('');

  // Reporte de pago con OCR/IA
  const [montoPago, setMontoPago] = useState('');
  const [monedaId, setMonedaId] = useState('');
  const [metodoId, setMetodoId] = useState('');
  const [tasaPago, setTasaPago] = useState('1.0000');
  const [referenciaPago, setReferenciaPago] = useState('');
  const [comprobanteUrl, setComprobanteUrl] = useState('');
  const [textoOcr, setTextoOcr] = useState('');
  const [ocrResult, setOcrResult] = useState<Record<string, unknown> | null>(null);

  // Pedido self-service B2B/B2C
  const [productoId, setProductoId] = useState('');
  const [cantidadPedido, setCantidadPedido] = useState('1');
  const [obsPedido, setObsPedido] = useState('');

  const token = session?.session_token ?? '';

  const { data: resumen, isLoading: loadingResumen } = useQuery({
    queryKey: ['portal-cliente', 'resumen', token],
    queryFn: () => portalClienteService.getResumen(token),
    enabled: Boolean(token),
  });

  const { data: tracking } = useQuery({
    queryKey: ['portal-cliente', 'tracking', token],
    queryFn: () => portalClienteService.getTracking(token),
    enabled: Boolean(token),
  });

  const solicitarOtpMut = useMutation({
    mutationFn: () =>
      portalClienteService.solicitarOtp({
        rif,
        id_empresa: idEmpresa.trim() || undefined,
        canal,
        destino: destino.trim() || undefined,
      }),
    onSuccess: (res) => {
      if (res.id_token) setIdToken(res.id_token);
      setFeedback({
        tipo: 'success',
        msg: res.destino_enmascarado
          ? `Código enviado por ${res.canal} a ${res.destino_enmascarado}.`
          : res.detail ?? 'Si el RIF existe, el código fue enviado.',
      });
    },
    onError: (err: Error) => setFeedback({ tipo: 'error', msg: err.message }),
  });

  const verificarOtpMut = useMutation({
    mutationFn: () =>
      portalClienteService.verificarOtp({
        id_token: idToken ?? undefined,
        rif,
        codigo: codigoOtp,
        id_empresa: idEmpresa.trim() || undefined,
      }),
    onSuccess: (sess) => {
      setPortalClienteSession(sess);
      setSession(sess);
      setCodigoOtp('');
      setFeedback({ tipo: 'success', msg: `Bienvenido, ${sess.cliente.razon_social}.` });
    },
    onError: (err: Error) => setFeedback({ tipo: 'error', msg: err.message }),
  });

  const pagoMut = useMutation({
    mutationFn: () =>
      portalClienteService.reportarPago(token, {
        monto: montoPago,
        id_moneda: monedaId,
        id_metodo_pago: metodoId,
        tasa: tasaPago || '1.0000',
        referencia: referenciaPago,
        comprobante_url: comprobanteUrl,
        texto_comprobante_ocr: textoOcr,
      }),
    onSuccess: (res) => {
      setOcrResult(res.ocr_extraido);
      setFeedback({
        tipo: 'success',
        msg: `Pago ${res.id_pago_portal} reportado (${res.estado}) ref. ${res.referencia || 'N/A'}.`,
      });
      setMontoPago('');
      setReferenciaPago('');
      setTextoOcr('');
      void queryClient.invalidateQueries({ queryKey: ['portal-cliente', 'resumen'] });
    },
    onError: (err: Error) => setFeedback({ tipo: 'error', msg: err.message }),
  });

  const pedidoMut = useMutation({
    mutationFn: () =>
      portalClienteService.crearPedido(token, {
        observaciones: obsPedido,
        lineas: [{ id_producto: productoId, cantidad: cantidadPedido }],
      }),
    onSuccess: (res) => {
      setFeedback({
        tipo: 'success',
        msg: `Pedido ${res.numero_pedido} registrado (${res.estado}) · Total est. ${res.total_estimado}.`,
      });
      setProductoId('');
      setCantidadPedido('1');
      setObsPedido('');
    },
    onError: (err: Error) => setFeedback({ tipo: 'error', msg: err.message }),
  });

  const cerrarSesion = () => {
    clearPortalClienteSession();
    queryClient.removeQueries({ queryKey: ['portal-cliente'] });
    setSession(null);
    setOcrResult(null);
    setFeedback(null);
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 4 }}>
      <Container maxWidth="md">
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
          <Box>
            <Typography variant="h5" fontWeight={700}>
              Portal de Clientes OmniERP
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {session
                ? `${session.cliente.razon_social} (${session.cliente.rif}) · ${session.cliente.empresa_nombre}`
                : 'Acceso B2B/B2C por código OTP de un solo uso'}
            </Typography>
          </Box>
          {session && (
            <Button size="small" variant="outlined" startIcon={<LogoutOutlined />} onClick={cerrarSesion}>
              Salir
            </Button>
          )}
        </Stack>

        {feedback && (
          <Alert severity={feedback.tipo} onClose={() => setFeedback(null)} sx={{ mb: 2 }}>
            {feedback.msg}
          </Alert>
        )}

        {!session ? (
          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <LockOutlined color="primary" />
                  <Typography variant="h6">Ingresar con RIF y OTP</Typography>
                </Stack>
                <TextField label="RIF (ej. J-123456789)" value={rif} onChange={(e) => setRif(e.target.value)} size="small" />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <TextField
                    select
                    label="Canal OTP"
                    value={canal}
                    onChange={(e) => setCanal(e.target.value as CanalOTPPortal)}
                    size="small"
                    sx={{ minWidth: 160 }}
                  >
                    <MenuItem value="WHATSAPP">WhatsApp</MenuItem>
                    <MenuItem value="EMAIL">Email</MenuItem>
                  </TextField>
                  <TextField
                    label="Destino alternativo (opcional)"
                    value={destino}
                    onChange={(e) => setDestino(e.target.value)}
                    size="small"
                    fullWidth
                  />
                  <TextField
                    label="ID Empresa (opcional)"
                    value={idEmpresa}
                    onChange={(e) => setIdEmpresa(e.target.value)}
                    size="small"
                    fullWidth
                  />
                </Stack>
                <Button variant="outlined" onClick={() => solicitarOtpMut.mutate()} disabled={solicitarOtpMut.isPending || !rif.trim()}>
                  Solicitar código OTP
                </Button>
                <Divider />
                <TextField
                  label="Código OTP (6 dígitos)"
                  value={codigoOtp}
                  onChange={(e) => setCodigoOtp(e.target.value)}
                  size="small"
                />
                <Button
                  variant="contained"
                  onClick={() => verificarOtpMut.mutate()}
                  disabled={verificarOtpMut.isPending || !rif.trim() || codigoOtp.trim().length < 6}
                >
                  Verificar e ingresar
                </Button>
              </Stack>
            </CardContent>
          </Card>
        ) : (
          <Box>
            {loadingResumen && <Typography color="text.secondary">Cargando estado de cuenta…</Typography>}

            {resumen && (
              <Grid container spacing={2} mb={2}>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <Card>
                    <CardContent>
                      <Typography variant="caption" color="text.secondary">
                        Saldo pendiente ({resumen.estado_cuenta_trimonetario.equivalencias.base_iso ?? 'USD'})
                      </Typography>
                      <Typography variant="h5" fontWeight={700}>
                        {resumen.estado_cuenta_trimonetario.saldo_pendiente}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Docs: {resumen.estado_cuenta_trimonetario.documentos_pendientes} · Vencidas:{' '}
                        {resumen.estado_cuenta_trimonetario.cuentas_vencidas}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <Card>
                    <CardContent>
                      <Typography variant="caption" color="text.secondary">
                        Equivalencia ({resumen.estado_cuenta_trimonetario.equivalencias.pais_fiscal_iso ?? 'VES'})
                      </Typography>
                      <Typography variant="h6" fontWeight={600}>
                        {resumen.estado_cuenta_trimonetario.equivalencias.pais_fiscal ?? 'N/D'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <Card>
                    <CardContent>
                      <Typography variant="caption" color="text.secondary">
                        Referencia ({resumen.estado_cuenta_trimonetario.equivalencias.referencia_iso ?? 'USDT'})
                      </Typography>
                      <Typography variant="h6" fontWeight={600}>
                        {resumen.estado_cuenta_trimonetario.equivalencias.referencia ?? 'N/D'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            )}

            <Tabs
              value={tab}
              onChange={(_e: SyntheticEvent, v: number) => setTab(v)}
              variant="scrollable"
              scrollButtons="auto"
              sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
            >
              <Tab icon={<ReceiptLongOutlined />} iconPosition="start" label="Documentos y Pagos" />
              <Tab label="Reportar Pago (OCR/IA)" />
              <Tab icon={<ShoppingBagOutlined />} iconPosition="start" label="Hacer Pedido" />
              <Tab icon={<LocalShippingOutlined />} iconPosition="start" label="Tracking Despachos" />
            </Tabs>

            {tab === 0 && resumen && (
              <Stack spacing={2}>
                <Typography variant="subtitle1" fontWeight={600}>
                  Facturas Fiscales ({resumen.facturas_fiscales.length})
                </Typography>
                {resumen.facturas_fiscales.map((f) => {
                  const href = safeExternalUrl(f.pdf_url);
                  return (
                    <Card key={f.id_factura} variant="outlined">
                      <CardContent>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Box>
                            <Typography fontWeight={600}>
                              {f.numero_factura} (Ctrl {f.numero_control})
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {f.fecha_emision} · {f.monto_total} {f.moneda} · {f.estado}
                            </Typography>
                          </Box>
                          {href && (
                            <Button
                              component={Link}
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              size="small"
                              startIcon={<DownloadOutlined />}
                            >
                              PDF
                            </Button>
                          )}
                        </Stack>
                      </CardContent>
                    </Card>
                  );
                })}

                <Typography variant="subtitle1" fontWeight={600}>
                  Notas de Venta ({resumen.notas_venta.length})
                </Typography>
                {resumen.notas_venta.map((n) => (
                  <Card key={n.id_nota_venta} variant="outlined">
                    <CardContent>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2">
                          {n.numero_nota} · {n.fecha_nota} ({n.ambito})
                        </Typography>
                        <StatusChip value={n.estado} colorMap={{ entregada: 'success', pendiente: 'warning' }} />
                      </Stack>
                    </CardContent>
                  </Card>
                ))}

                <Typography variant="subtitle1" fontWeight={600}>
                  Pagos Reportados ({resumen.pagos_reportados.length})
                </Typography>
                {resumen.pagos_reportados.map((p) => (
                  <Card key={p.id_pago_portal} variant="outlined">
                    <CardContent>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2">
                          {p.monto} {p.moneda} · Ref: {p.referencia || 'N/A'}
                        </Typography>
                        <StatusChip value={p.estado} />
                      </Stack>
                    </CardContent>
                  </Card>
                ))}
              </Stack>
            )}

            {tab === 1 && (
              <Card>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">Reportar Pago con Extracción OCR/IA</Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                      <TextField label="Monto" value={montoPago} onChange={(e) => setMontoPago(e.target.value)} size="small" fullWidth />
                      <TextField label="Tasa" value={tasaPago} onChange={(e) => setTasaPago(e.target.value)} size="small" fullWidth />
                    </Stack>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                      <TextField label="UUID Moneda" value={monedaId} onChange={(e) => setMonedaId(e.target.value)} size="small" fullWidth />
                      <TextField label="UUID Método de Pago" value={metodoId} onChange={(e) => setMetodoId(e.target.value)} size="small" fullWidth />
                    </Stack>
                    <TextField label="Referencia (opcional si OCR la detecta)" value={referenciaPago} onChange={(e) => setReferenciaPago(e.target.value)} size="small" />
                    <TextField label="URL Comprobante (https://...)" value={comprobanteUrl} onChange={(e) => setComprobanteUrl(e.target.value)} size="small" />
                    <TextField
                      label="Texto copiado del comprobante (OCR/IA)"
                      value={textoOcr}
                      onChange={(e) => setTextoOcr(e.target.value)}
                      multiline
                      rows={3}
                      size="small"
                    />
                    <Button variant="contained" onClick={() => pagoMut.mutate()} disabled={pagoMut.isPending}>
                      Enviar Reporte de Pago
                    </Button>
                    {ocrResult && (
                      <Alert severity="info">
                        OCR ({String(ocrResult.fuente ?? 'DET')}): monto={String(ocrResult.monto ?? '-')}, moneda=
                        {String(ocrResult.moneda ?? '-')}, ref={String(ocrResult.referencia ?? '-')}
                      </Alert>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            )}

            {tab === 2 && (
              <Card>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">Nuevo Pedido B2B/B2C</Typography>
                    <TextField label="UUID del Producto" value={productoId} onChange={(e) => setProductoId(e.target.value)} size="small" />
                    <TextField label="Cantidad" value={cantidadPedido} onChange={(e) => setCantidadPedido(e.target.value)} size="small" />
                    <TextField label="Observaciones" value={obsPedido} onChange={(e) => setObsPedido(e.target.value)} size="small" />
                    <Button variant="contained" onClick={() => pedidoMut.mutate()} disabled={pedidoMut.isPending || !productoId.trim()}>
                      Enviar Pedido
                    </Button>
                  </Stack>
                </CardContent>
              </Card>
            )}

            {tab === 3 && (
              <Stack spacing={2}>
                {(tracking?.despachos ?? []).map((d) => {
                  const trackHref = safeExternalUrl(d.tracking_url_publico);
                  return (
                    <Card key={d.id_despacho} variant="outlined">
                      <CardContent>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Box>
                            <Typography fontWeight={600}>
                              {d.numero_despacho} · Estado: {d.estado_despacho}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Parada: {d.parada_estado ?? 'Sin ruta'} · ETA: {d.eta_estimada ?? 'Por definir'}
                            </Typography>
                          </Box>
                          <Stack direction="row" spacing={1} alignItems="center">
                            {d.token_tracking && <Chip label={`Token ${d.token_tracking.slice(0, 8)}`} size="small" />}
                            {trackHref && (
                              <Button component={Link} href={trackHref} target="_blank" rel="noopener noreferrer" size="small">
                                Ver mapa
                              </Button>
                            )}
                          </Stack>
                        </Stack>
                      </CardContent>
                    </Card>
                  );
                })}
                {(tracking?.despachos ?? []).length === 0 && (
                  <Typography color="text.secondary">Sin despachos activos en seguimiento.</Typography>
                )}
              </Stack>
            )}
          </Box>
        )}
      </Container>
    </Box>
  );
}
