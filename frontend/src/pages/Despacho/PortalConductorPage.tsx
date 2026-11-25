import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Link,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import LocalShippingOutlined from '@mui/icons-material/LocalShippingOutlined';
import MapOutlined from '@mui/icons-material/MapOutlined';
import NavigationOutlined from '@mui/icons-material/NavigationOutlined';
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';
import {
  portalConductorService,
  safeExternalUrl,
  type ParadaPortalConductor,
} from '../../services/portalesService';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

type ResultadoEPOD = 'ENTREGADA' | 'ENTREGA_PARCIAL' | 'RECHAZADA';

export default function PortalConductorPage() {
  const empresaId = getEmpresaId();
  const queryClient = useQueryClient();

  const [filtroConductor, setFiltroConductor] = useState('');
  const [feedback, setFeedback] = useState<{ tipo: 'success' | 'error'; msg: string } | null>(null);

  // Dialogo escaneo de bulto
  const [paradaScan, setParadaScan] = useState<ParadaPortalConductor | null>(null);
  const [codigoBulto, setCodigoBulto] = useState('');

  // Dialogo ePOD
  const [paradaEpod, setParadaEpod] = useState<ParadaPortalConductor | null>(null);
  const [resultadoEpod, setResultadoEpod] = useState<ResultadoEPOD>('ENTREGADA');
  const [receptorNombre, setReceptorNombre] = useState('');
  const [receptorCedula, setReceptorCedula] = useState('');
  const [firmaBase64, setFirmaBase64] = useState('');
  const [fotoUrl, setFotoUrl] = useState('');
  const [latitud, setLatitud] = useState('10.481000');
  const [longitud, setLongitud] = useState('-66.858000');
  const [observaciones, setObservaciones] = useState('');
  const [motivoRechazo, setMotivoRechazo] = useState('');
  const [incluirCobro, setIncluirCobro] = useState(false);
  const [cobroMonto, setCobroMonto] = useState('');
  const [cobroMoneda, setCobroMoneda] = useState('');
  const [cobroMetodo, setCobroMetodo] = useState('');
  const [cobroRef, setCobroRef] = useState('');

  const { data: rutasData, isLoading } = useQuery({
    queryKey: ['portal-conductor', 'mis-rutas', empresaId, filtroConductor],
    queryFn: () =>
      portalConductorService.getMisRutas({
        empresa: empresaId ?? undefined,
        conductor: filtroConductor.trim() || undefined,
      }),
  });

  const scanMut = useMutation({
    mutationFn: () => {
      if (!paradaScan) throw new Error('Selecciona una parada.');
      return portalConductorService.escanearBulto(paradaScan.id_parada, { codigo_bulto: codigoBulto });
    },
    onSuccess: (res) => {
      setFeedback({ tipo: 'success', msg: `Bulto ${res.codigo_bulto} verificado en parada.` });
      setParadaScan(null);
      setCodigoBulto('');
    },
    onError: (err) => setFeedback({ tipo: 'error', msg: mensajeDeError(err) }),
  });

  const epodMut = useMutation({
    mutationFn: () => {
      if (!paradaEpod) throw new Error('Selecciona una parada.');
      return portalConductorService.registrarEpod(paradaEpod.id_parada, {
        resultado: resultadoEpod,
        receptor_nombre: receptorNombre,
        receptor_cedula: receptorCedula,
        firma_base64: firmaBase64,
        foto_url: fotoUrl,
        latitud: latitud || null,
        longitud: longitud || null,
        observaciones,
        motivo_rechazo: resultadoEpod === 'RECHAZADA' ? motivoRechazo : '',
        cobro: incluirCobro
          ? {
              monto: cobroMonto,
              id_moneda: cobroMoneda,
              id_metodo_pago: cobroMetodo,
              referencia: cobroRef,
            }
          : null,
      });
    },
    onSuccess: (res) => {
      setFeedback({
        tipo: 'success',
        msg: `ePOD registrado · Despacho ${res.despacho_estado}${res.pago_id ? ' · Cobro aplicado' : ''}.`,
      });
      setParadaEpod(null);
      setReceptorNombre('');
      setReceptorCedula('');
      setFirmaBase64('');
      setFotoUrl('');
      setObservaciones('');
      setMotivoRechazo('');
      setIncluirCobro(false);
      void queryClient.invalidateQueries({ queryKey: ['portal-conductor', 'mis-rutas'] });
    },
    onError: (err) => setFeedback({ tipo: 'error', msg: mensajeDeError(err) }),
  });

  const rutas = rutasData?.rutas ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Portal de Conductores"
        subtitle="Rutas optimizadas VRP, navegación 1-tap Waze/Maps, escaneo de bultos y captura ePOD"
      />

      {feedback && (
        <Alert severity={feedback.tipo} onClose={() => setFeedback(null)} sx={{ mb: 2 }}>
          {feedback.msg}
        </Alert>
      )}

      <TextField
        label="Filtrar por UUID Conductor (solo supervisor)"
        value={filtroConductor}
        onChange={(e) => setFiltroConductor(e.target.value)}
        size="small"
        sx={{ mb: 2, minWidth: 300 }}
      />

      {isLoading && <Typography color="text.secondary">Cargando rutas asignadas…</Typography>}

      <Stack spacing={2}>
        {rutas.map((ruta) => (
          <Card key={ruta.id_ruta}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <LocalShippingOutlined color="primary" />
                  <Typography variant="h6">
                    {ruta.codigo} · Vehículo {ruta.vehiculo_placa ?? 'Sin asignar'}
                  </Typography>
                </Stack>
                <StatusChip value={ruta.estado} colorMap={{ en_curso: 'info', planificada: 'warning' }} />
              </Stack>

              <Stack spacing={1.5}>
                {ruta.paradas.map((p) => {
                  const wazeHref = safeExternalUrl(p.waze_url);
                  const mapsHref = safeExternalUrl(p.google_maps_url);
                  return (
                    <Card key={p.id_parada} variant="outlined">
                      <CardContent>
                        <Stack
                          direction={{ xs: 'column', md: 'row' }}
                          justifyContent="space-between"
                          alignItems={{ xs: 'flex-start', md: 'center' }}
                          spacing={1}
                        >
                          <Box>
                            <Typography fontWeight={600}>
                              Parada #{p.secuencia} · {p.despacho_numero}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {p.direccion_texto} · Estado: {p.estado}
                            </Typography>
                          </Box>

                          <Stack direction="row" spacing={1} flexWrap="wrap">
                            {wazeHref && (
                              <Button
                                component={Link}
                                href={wazeHref}
                                target="_blank"
                                rel="noopener noreferrer"
                                size="small"
                                variant="outlined"
                                startIcon={<NavigationOutlined />}
                              >
                                Waze
                              </Button>
                            )}
                            {mapsHref && (
                              <Button
                                component={Link}
                                href={mapsHref}
                                target="_blank"
                                rel="noopener noreferrer"
                                size="small"
                                variant="outlined"
                                startIcon={<MapOutlined />}
                              >
                                Google Maps
                              </Button>
                            )}
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={<QrCodeScannerOutlined />}
                              onClick={() => setParadaScan(p)}
                            >
                              Escanear bulto
                            </Button>
                            <Button
                              size="small"
                              variant="contained"
                              startIcon={<CheckCircleOutlined />}
                              onClick={() => setParadaEpod(p)}
                            >
                              Registrar ePOD
                            </Button>
                          </Stack>
                        </Stack>
                      </CardContent>
                    </Card>
                  );
                })}
              </Stack>
            </CardContent>
          </Card>
        ))}

        {!isLoading && rutas.length === 0 && (
          <Typography color="text.secondary">No tienes rutas activas asignadas en este momento.</Typography>
        )}
      </Stack>

      <Dialog open={Boolean(paradaScan)} onClose={() => setParadaScan(null)} fullWidth maxWidth="xs">
        <DialogTitle>Escanear Bulto · Parada #{paradaScan?.secuencia}</DialogTitle>
        <DialogContent>
          <TextField
            label="SKU o Código de Barras"
            value={codigoBulto}
            onChange={(e) => setCodigoBulto(e.target.value)}
            fullWidth
            size="small"
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setParadaScan(null)}>Cancelar</Button>
          <Button variant="contained" onClick={() => scanMut.mutate()} disabled={scanMut.isPending || !codigoBulto.trim()}>
            Verificar bulto
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(paradaEpod)} onClose={() => setParadaEpod(null)} fullWidth maxWidth="sm">
        <DialogTitle>Registrar ePOD · {paradaEpod?.despacho_numero}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Resultado entrega"
              value={resultadoEpod}
              onChange={(e) => setResultadoEpod(e.target.value as ResultadoEPOD)}
              size="small"
            >
              <MenuItem value="ENTREGADA">Entregada conforme</MenuItem>
              <MenuItem value="ENTREGA_PARCIAL">Entrega parcial</MenuItem>
              <MenuItem value="RECHAZADA">Rechazada</MenuItem>
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField label="Receptor nombre" value={receptorNombre} onChange={(e) => setReceptorNombre(e.target.value)} size="small" fullWidth />
              <TextField label="Receptor cédula" value={receptorCedula} onChange={(e) => setReceptorCedula(e.target.value)} size="small" fullWidth />
            </Stack>
            <TextField label="Firma (base64 / trazo)" value={firmaBase64} onChange={(e) => setFirmaBase64(e.target.value)} size="small" />
            <TextField label="URL Foto ePOD" value={fotoUrl} onChange={(e) => setFotoUrl(e.target.value)} size="small" />
            <Stack direction="row" spacing={1}>
              <TextField label="Latitud entrega" value={latitud} onChange={(e) => setLatitud(e.target.value)} size="small" fullWidth />
              <TextField label="Longitud entrega" value={longitud} onChange={(e) => setLongitud(e.target.value)} size="small" fullWidth />
            </Stack>
            <TextField label="Observaciones / motivo rechazo" value={observaciones} onChange={(e) => { setObservaciones(e.target.value); setMotivoRechazo(e.target.value); }} size="small" />
            <FormControlLabel
              control={<Checkbox checked={incluirCobro} onChange={(e) => setIncluirCobro(e.target.checked)} />}
              label="Registrar cobro contra entrega"
            />
            {incluirCobro && (
              <Stack spacing={1}>
                <Stack direction="row" spacing={1}>
                  <TextField label="Monto cobro" value={cobroMonto} onChange={(e) => setCobroMonto(e.target.value)} size="small" fullWidth />
                  <TextField label="Referencia cobro" value={cobroRef} onChange={(e) => setCobroRef(e.target.value)} size="small" fullWidth />
                </Stack>
                <Stack direction="row" spacing={1}>
                  <TextField label="UUID Moneda" value={cobroMoneda} onChange={(e) => setCobroMoneda(e.target.value)} size="small" fullWidth />
                  <TextField label="UUID Método Pago" value={cobroMetodo} onChange={(e) => setCobroMetodo(e.target.value)} size="small" fullWidth />
                </Stack>
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setParadaEpod(null)}>Cancelar</Button>
          <Button variant="contained" onClick={() => epodMut.mutate()} disabled={epodMut.isPending}>
            Confirmar ePOD
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
}
