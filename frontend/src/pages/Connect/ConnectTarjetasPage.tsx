import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import AddOutlined from '@mui/icons-material/AddOutlined';
import BlockOutlined from '@mui/icons-material/BlockOutlined';
import CheckCircleOutlineOutlined from '@mui/icons-material/CheckCircleOutlineOutlined';
import DownloadOutlined from '@mui/icons-material/DownloadOutlined';
import LinkOutlined from '@mui/icons-material/LinkOutlined';
import QrCode2Outlined from '@mui/icons-material/QrCode2Outlined';
import ReportProblemOutlined from '@mui/icons-material/ReportProblemOutlined';
import {
  DataTable,
  PageContainer,
  PageHeader,
  StatusChip,
  type Column,
} from '../../components/ui';
import { connectKeys } from '../../lib/queryKeys';
import {
  activarTarjetaConnect,
  asignarTarjetaConnect,
  crearTarjetaConnect,
  desactivarTarjetaConnect,
  getMiPerfilQrBlob,
  getPerfilesConnect,
  getTarjetaQrBlob,
  getTarjetasConnect,
  marcarPerdidaTarjetaConnect,
  type ConnectPerfil,
  type ConnectQrFormato,
  type ConnectTarjeta,
  type TarjetaTipo,
} from '../../services/connectService';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';

type QrTarget =
  | { kind: 'mi-perfil' }
  | { kind: 'tarjeta'; tarjeta: ConnectTarjeta };

const TIPO_OPCIONES: Array<{ value: TarjetaTipo; label: string }> = [
  { value: 'PVC', label: 'Tarjeta PVC' },
  { value: 'METAL', label: 'Tarjeta metálica' },
  { value: 'PULSERA', label: 'Pulsera NFC' },
];

const TIPO_LABELS = new Map<string, string>(TIPO_OPCIONES.map((opt) => [opt.value, opt.label]));

const ESTADO_OPCIONES = [
  { value: '', label: 'Todos los estados' },
  { value: 'INVENTARIO', label: 'En inventario' },
  { value: 'ACTIVA', label: 'Activa' },
  { value: 'DESACTIVADA', label: 'Desactivada' },
  { value: 'PERDIDA', label: 'Perdida' },
];

const ESTADO_COLOR_MAP: Record<
  string,
  'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info'
> = {
  inventario: 'info',
  activa: 'success',
  desactivada: 'default',
  perdida: 'error',
};

function dispararDescargaUrl(objectUrl: string, filename: string): void {
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function nombreArchivoQr(target: QrTarget, formato: ConnectQrFormato): string {
  if (target.kind === 'mi-perfil') {
    return `qr-mi-perfil.${formato}`;
  }
  const slug = target.tarjeta.perfil_slug || 'tarjeta';
  return `qr-${slug}-${target.tarjeta.uid_chip}.${formato}`;
}

export default function ConnectTarjetasPage() {
  const empresaId = getEmpresaId();
  const queryClient = useQueryClient();

  // Filtros
  const [estadoFiltro, setEstadoFiltro] = useState<string>('');
  const [incluirInactivos, setIncluirInactivos] = useState<boolean>(false);

  // Feedback global de acciones de fila
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  // Diálogo crear tarjeta
  const [createOpen, setCreateOpen] = useState(false);
  const [uidChip, setUidChip] = useState('');
  const [tipo, setTipo] = useState<TarjetaTipo>('PVC');
  const [notas, setNotas] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  // Diálogo asignar a perfil
  const [asignarTarget, setAsignarTarget] = useState<ConnectTarjeta | null>(null);
  const [asignarPerfilId, setAsignarPerfilId] = useState('');
  const [asignarActivar, setAsignarActivar] = useState(true);
  const [asignarError, setAsignarError] = useState<string | null>(null);

  // Diálogo confirmar marcar perdida
  const [perdidaTarget, setPerdidaTarget] = useState<ConnectTarjeta | null>(null);
  const [perdidaError, setPerdidaError] = useState<string | null>(null);

  // Diálogo vista previa y descarga QR
  const [qrTarget, setQrTarget] = useState<QrTarget | null>(null);
  const [qrFormato, setQrFormato] = useState<ConnectQrFormato>('svg');
  const [qrPreviewUrl, setQrPreviewUrl] = useState<string | null>(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [qrDownloading, setQrDownloading] = useState(false);
  const [qrError, setQrError] = useState<string | null>(null);
  const qrObjectUrlRef = useRef<string | null>(null);

  const revocarQrPreviewUrl = useCallback(() => {
    if (qrObjectUrlRef.current) {
      URL.revokeObjectURL(qrObjectUrlRef.current);
      qrObjectUrlRef.current = null;
    }
    setQrPreviewUrl(null);
  }, []);

  useEffect(() => {
    return () => {
      if (qrObjectUrlRef.current) {
        URL.revokeObjectURL(qrObjectUrlRef.current);
        qrObjectUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!qrTarget) {
      revocarQrPreviewUrl();
      setQrError(null);
      setQrLoading(false);
      return;
    }

    let cancelled = false;
    setQrLoading(true);
    setQrError(null);
    revocarQrPreviewUrl();

    const request =
      qrTarget.kind === 'mi-perfil'
        ? getMiPerfilQrBlob(qrFormato, empresaId)
        : getTarjetaQrBlob(qrTarget.tarjeta.id_tarjeta, qrFormato);

    request
      .then((blob) => {
        if (cancelled) return;
        const nextUrl = URL.createObjectURL(blob);
        qrObjectUrlRef.current = nextUrl;
        setQrPreviewUrl(nextUrl);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setQrError(mensajeDeError(err, 'No se pudo generar el código QR.'));
      })
      .finally(() => {
        if (!cancelled) setQrLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [qrTarget, qrFormato, empresaId, revocarQrPreviewUrl]);

  const tarjetasQuery = useQuery<ConnectTarjeta[]>({
    queryKey: connectKeys.tarjetas(empresaId, estadoFiltro || null, incluirInactivos),
    queryFn: () =>
      getTarjetasConnect({
        empresaId,
        estado: estadoFiltro || null,
        incluirInactivos,
      }),
  });

  const perfilesQuery = useQuery<ConnectPerfil[]>({
    queryKey: connectKeys.perfiles(empresaId),
    queryFn: () => getPerfilesConnect(empresaId),
  });

  const invalidarTarjetas = useCallback(() => {
    return queryClient.invalidateQueries({ queryKey: connectKeys.tarjetasAll(empresaId) });
  }, [empresaId, queryClient]);

  function resetCreateDialog() {
    setCreateOpen(false);
    setUidChip('');
    setTipo('PVC');
    setNotas('');
    setCreateError(null);
  }

  function resetAsignarDialog() {
    setAsignarTarget(null);
    setAsignarPerfilId('');
    setAsignarActivar(true);
    setAsignarError(null);
  }

  function resetPerdidaDialog() {
    setPerdidaTarget(null);
    setPerdidaError(null);
  }

  function closeQrDialog() {
    revocarQrPreviewUrl();
    setQrTarget(null);
    setQrFormato('svg');
    setQrError(null);
    setQrLoading(false);
    setQrDownloading(false);
  }

  const crearMutation = useMutation({
    mutationFn: () =>
      crearTarjetaConnect(
        {
          uid_chip: uidChip.trim(),
          tipo,
          notas: notas.trim(),
        },
        empresaId,
      ),
    onSuccess: async (creada) => {
      await invalidarTarjetas();
      setFeedbackError(null);
      setFeedbackSuccess(`Tarjeta ${creada.uid_chip} registrada en inventario.`);
      resetCreateDialog();
    },
    onError: (err) => {
      setCreateError(mensajeDeError(err, 'No se pudo registrar la tarjeta NFC.'));
    },
  });

  const asignarMutation = useMutation({
    mutationFn: ({ tarjetaId, perfilId, activar }: { tarjetaId: string; perfilId: string; activar: boolean }) =>
      asignarTarjetaConnect(tarjetaId, { perfil_id: perfilId, activar }),
    onSuccess: async (actualizada) => {
      await invalidarTarjetas();
      setFeedbackError(null);
      setFeedbackSuccess(`Tarjeta ${actualizada.uid_chip} asignada correctamente.`);
      resetAsignarDialog();
    },
    onError: (err) => {
      setAsignarError(mensajeDeError(err, 'No se pudo asignar la tarjeta al perfil.'));
    },
  });

  const activarMutation = useMutation({
    mutationFn: (tarjetaId: string) => activarTarjetaConnect(tarjetaId),
    onSuccess: async (actualizada) => {
      await invalidarTarjetas();
      setFeedbackError(null);
      setFeedbackSuccess(`Tarjeta ${actualizada.uid_chip} activada.`);
    },
    onError: (err) => {
      setFeedbackSuccess(null);
      setFeedbackError(mensajeDeError(err, 'No se pudo activar la tarjeta.'));
    },
  });

  const desactivarMutation = useMutation({
    mutationFn: (tarjetaId: string) => desactivarTarjetaConnect(tarjetaId),
    onSuccess: async (actualizada) => {
      await invalidarTarjetas();
      setFeedbackError(null);
      setFeedbackSuccess(`Tarjeta ${actualizada.uid_chip} desactivada.`);
    },
    onError: (err) => {
      setFeedbackSuccess(null);
      setFeedbackError(mensajeDeError(err, 'No se pudo desactivar la tarjeta.'));
    },
  });

  const perdidaMutation = useMutation({
    mutationFn: (tarjetaId: string) => marcarPerdidaTarjetaConnect(tarjetaId),
    onSuccess: async (actualizada) => {
      await invalidarTarjetas();
      setFeedbackError(null);
      setFeedbackSuccess(`Tarjeta ${actualizada.uid_chip} marcada como perdida y revocada.`);
      resetPerdidaDialog();
    },
    onError: (err) => {
      setPerdidaError(mensajeDeError(err, 'No se pudo marcar la tarjeta como perdida.'));
    },
  });

  function handleCrearSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError(null);
    if (!uidChip.trim()) {
      setCreateError('El UID del chip es obligatorio.');
      return;
    }
    crearMutation.mutate();
  }

  function handleAsignarSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAsignarError(null);
    if (!asignarTarget || !asignarPerfilId) {
      setAsignarError('Selecciona un perfil activo para asignar la tarjeta.');
      return;
    }
    asignarMutation.mutate({
      tarjetaId: asignarTarget.id_tarjeta,
      perfilId: asignarPerfilId,
      activar: asignarActivar,
    });
  }

  async function handleDescargarQr(formato: ConnectQrFormato) {
    if (!qrTarget) return;
    setQrError(null);
    const filename = nombreArchivoQr(qrTarget, formato);

    if (formato === qrFormato && qrPreviewUrl) {
      dispararDescargaUrl(qrPreviewUrl, filename);
      return;
    }

    setQrDownloading(true);
    let tempUrl: string | null = null;
    let deferredRevoke = false;
    try {
      const blob =
        qrTarget.kind === 'mi-perfil'
          ? await getMiPerfilQrBlob(formato, empresaId)
          : await getTarjetaQrBlob(qrTarget.tarjeta.id_tarjeta, formato);
      tempUrl = URL.createObjectURL(blob);
      dispararDescargaUrl(tempUrl, filename);
      const urlToRevoke = tempUrl;
      deferredRevoke = true;
      window.setTimeout(() => URL.revokeObjectURL(urlToRevoke), 1000);
    } catch (err) {
      setQrError(mensajeDeError(err, 'No se pudo descargar el código QR.'));
    } finally {
      if (tempUrl && !deferredRevoke) {
        URL.revokeObjectURL(tempUrl);
      }
      setQrDownloading(false);
    }
  }

  const tarjetas = tarjetasQuery.data ?? [];
  const perfilesActivos = (perfilesQuery.data ?? []).filter((p) => p.activo);
  const accionFilaEnCurso = activarMutation.isPending || desactivarMutation.isPending;

  const columns: Column<ConnectTarjeta>[] = [
    {
      key: 'uid_chip',
      header: 'UID del chip',
      render: (row) => (
        <Box>
          <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
            {row.uid_chip}
          </Typography>
          {row.notas && (
            <Typography variant="caption" color="text.secondary">
              {row.notas}
            </Typography>
          )}
        </Box>
      ),
    },
    {
      key: 'tipo',
      header: 'Tipo',
      render: (row) => TIPO_LABELS.get(row.tipo) ?? row.tipo,
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (row) => <StatusChip value={row.estado} colorMap={ESTADO_COLOR_MAP} />,
    },
    {
      key: 'perfil',
      header: 'Perfil asignado',
      render: (row) =>
        row.perfil ? (
          <Box>
            <Typography variant="body2" fontWeight={500}>
              {row.perfil_nombre || 'Perfil asignado'}
            </Typography>
            {row.perfil_slug && (
              <Typography variant="caption" color="text.secondary" fontFamily="monospace">
                /c/{row.perfil_slug}
              </Typography>
            )}
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Sin asignar
          </Typography>
        ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (row) => (
        <Stack direction="row" spacing={0.75} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
          {row.estado !== 'PERDIDA' && (
            <Button
              size="small"
              variant="outlined"
              startIcon={<LinkOutlined />}
              onClick={() => {
                setAsignarError(null);
                const perfilValido =
                  row.perfil && perfilesActivos.some((p) => p.id_perfil === row.perfil)
                    ? row.perfil
                    : '';
                setAsignarPerfilId(perfilValido);
                setAsignarActivar(true);
                setAsignarTarget(row);
              }}
            >
              Asignar
            </Button>
          )}

          {row.perfil && (row.estado === 'INVENTARIO' || row.estado === 'DESACTIVADA') && (
            <Button
              size="small"
              variant="outlined"
              color="success"
              startIcon={<CheckCircleOutlineOutlined />}
              disabled={accionFilaEnCurso}
              onClick={() => activarMutation.mutate(row.id_tarjeta)}
            >
              Activar
            </Button>
          )}

          {row.estado === 'ACTIVA' && (
            <Button
              size="small"
              variant="outlined"
              color="warning"
              startIcon={<BlockOutlined />}
              disabled={accionFilaEnCurso}
              onClick={() => desactivarMutation.mutate(row.id_tarjeta)}
            >
              Desactivar
            </Button>
          )}

          {row.perfil && (
            <Button
              size="small"
              variant="outlined"
              startIcon={<QrCode2Outlined />}
              onClick={() => {
                setQrFormato('svg');
                setQrTarget({ kind: 'tarjeta', tarjeta: row });
              }}
            >
              QR
            </Button>
          )}

          {row.estado !== 'PERDIDA' && (
            <Button
              size="small"
              variant="outlined"
              color="error"
              startIcon={<ReportProblemOutlined />}
              onClick={() => {
                setPerdidaError(null);
                setPerdidaTarget(row);
              }}
            >
              Marcar perdida
            </Button>
          )}
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Tarjetas NFC y códigos QR"
        subtitle="Administra el inventario de chips físicos, su asignación a perfiles y descarga códigos QR."
        actions={
          <>
            <Button
              variant="outlined"
              startIcon={<QrCode2Outlined />}
              onClick={() => {
                setQrFormato('svg');
                setQrTarget({ kind: 'mi-perfil' });
              }}
            >
              QR de mi perfil
            </Button>
            <Button
              variant="contained"
              startIcon={<AddOutlined />}
              onClick={() => {
                setCreateError(null);
                setCreateOpen(true);
              }}
            >
              Nueva tarjeta
            </Button>
          </>
        }
      />

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        mb={2.5}
      >
        <TextField
          select
          size="small"
          label="Filtrar por estado"
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value)}
          sx={{ minWidth: 210 }}
        >
          {ESTADO_OPCIONES.map((opt) => (
            <MenuItem key={opt.value} value={opt.value}>
              {opt.label}
            </MenuItem>
          ))}
        </TextField>

        <FormControlLabel
          control={
            <Checkbox
              checked={incluirInactivos}
              onChange={(e) => setIncluirInactivos(e.target.checked)}
            />
          }
          label="Incluir inactivas"
        />
      </Stack>

      {feedbackSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setFeedbackSuccess(null)}>
          {feedbackSuccess}
        </Alert>
      )}

      {feedbackError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setFeedbackError(null)}>
          {feedbackError}
        </Alert>
      )}

      {tarjetasQuery.isError ? (
        <Alert severity="error">
          {mensajeDeError(tarjetasQuery.error, 'No se pudieron cargar las tarjetas NFC.')}
        </Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={tarjetas}
          getRowKey={(row) => row.id_tarjeta}
          loading={tarjetasQuery.isLoading}
          emptyMessage="No hay tarjetas registradas con los filtros actuales."
        />
      )}

      {/* Diálogo crear tarjeta en inventario */}
      <Dialog open={createOpen} onClose={resetCreateDialog} maxWidth="sm" fullWidth>
        <Box component="form" onSubmit={handleCrearSubmit} noValidate>
          <DialogTitle>Registrar tarjeta NFC en inventario</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {createError && <Alert severity="error">{createError}</Alert>}
              <TextField
                label="UID del chip"
                required
                fullWidth
                value={uidChip}
                onChange={(e) => setUidChip(e.target.value)}
                helperText="8 a 20 caracteres hexadecimales (ej. 04A1B2C3D4)."
              />
              <TextField
                select
                label="Tipo de tarjeta"
                fullWidth
                value={tipo}
                onChange={(e) => setTipo(e.target.value as TarjetaTipo)}
              >
                {TIPO_OPCIONES.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Notas"
                multiline
                minRows={2}
                fullWidth
                value={notas}
                onChange={(e) => setNotas(e.target.value)}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={resetCreateDialog} disabled={crearMutation.isPending}>
              Cancelar
            </Button>
            <Button type="submit" variant="contained" disabled={crearMutation.isPending}>
              {crearMutation.isPending ? 'Guardando…' : 'Registrar tarjeta'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      {/* Diálogo asignar tarjeta a perfil */}
      <Dialog open={Boolean(asignarTarget)} onClose={resetAsignarDialog} maxWidth="sm" fullWidth>
        <Box component="form" onSubmit={handleAsignarSubmit} noValidate>
          <DialogTitle>Asignar tarjeta a perfil</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {asignarTarget && (
                <Typography variant="body2" color="text.secondary">
                  Chip seleccionado: <strong>{asignarTarget.uid_chip}</strong>
                </Typography>
              )}
              {asignarError && <Alert severity="error">{asignarError}</Alert>}
              <TextField
                select
                label="Perfil Connect"
                required
                fullWidth
                value={
                  perfilesActivos.some((p) => p.id_perfil === asignarPerfilId)
                    ? asignarPerfilId
                    : ''
                }
                onChange={(e) => setAsignarPerfilId(e.target.value)}
              >
                {perfilesActivos.map((perfil) => (
                  <MenuItem key={perfil.id_perfil} value={perfil.id_perfil}>
                    {perfil.nombre_publico} (/c/{perfil.slug})
                  </MenuItem>
                ))}
              </TextField>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={asignarActivar}
                    onChange={(e) => setAsignarActivar(e.target.checked)}
                  />
                }
                label="Activar tarjeta inmediatamente al asignar"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={resetAsignarDialog} disabled={asignarMutation.isPending}>
              Cancelar
            </Button>
            <Button type="submit" variant="contained" disabled={asignarMutation.isPending}>
              {asignarMutation.isPending ? 'Asignando…' : 'Guardar asignación'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      {/* Diálogo confirmación marcar perdida */}
      <Dialog open={Boolean(perdidaTarget)} onClose={resetPerdidaDialog} maxWidth="xs" fullWidth>
        <DialogTitle>Confirmar tarjeta perdida</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {perdidaError && <Alert severity="error">{perdidaError}</Alert>}
            <Typography variant="body2">
              ¿Seguro que deseas marcar la tarjeta <strong>{perdidaTarget?.uid_chip}</strong> como{' '}
              <strong>PERDIDA</strong>? Se revocará inmediatamente su acceso público NFC y no podrá
              reactivarse.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={resetPerdidaDialog} disabled={perdidaMutation.isPending}>
            Cancelar
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={perdidaMutation.isPending || !perdidaTarget}
            onClick={() => {
              if (perdidaTarget) perdidaMutation.mutate(perdidaTarget.id_tarjeta);
            }}
          >
            {perdidaMutation.isPending ? 'Revocando…' : 'Confirmar perdida'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Diálogo vista previa y descarga QR */}
      <Dialog open={Boolean(qrTarget)} onClose={closeQrDialog} maxWidth="xs" fullWidth>
        <DialogTitle>
          {qrTarget?.kind === 'mi-perfil'
            ? 'Código QR de mi perfil'
            : `Código QR — ${qrTarget?.tarjeta.uid_chip ?? ''}`}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} alignItems="center" sx={{ mt: 1 }}>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={qrFormato}
              aria-label="Formato de vista previa QR"
              onChange={(_, next: ConnectQrFormato | null) => {
                if (next) setQrFormato(next);
              }}
            >
              <ToggleButton value="svg">SVG</ToggleButton>
              <ToggleButton value="png">PNG</ToggleButton>
            </ToggleButtonGroup>

            {qrError && (
              <Alert severity="error" sx={{ width: '100%' }}>
                {qrError}
              </Alert>
            )}

            {qrLoading ? (
              <Box sx={{ py: 5 }}>
                <CircularProgress aria-label="Generando código QR" />
              </Box>
            ) : qrPreviewUrl ? (
              <Box
                component="img"
                src={qrPreviewUrl}
                alt={
                  qrTarget?.kind === 'mi-perfil'
                    ? 'Vista previa QR de mi perfil'
                    : `Vista previa QR tarjeta ${qrTarget?.tarjeta.uid_chip ?? ''}`
                }
                sx={{
                  width: 220,
                  height: 220,
                  objectFit: 'contain',
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 2,
                  p: 1,
                  bgcolor: '#fff',
                }}
              />
            ) : null}

            <Stack direction="row" spacing={1.25} width="100%" justifyContent="center">
              <Button
                variant="outlined"
                startIcon={<DownloadOutlined />}
                disabled={qrLoading || qrDownloading}
                onClick={() => void handleDescargarQr('svg')}
              >
                Descargar SVG
              </Button>
              <Button
                variant="contained"
                startIcon={<DownloadOutlined />}
                disabled={qrLoading || qrDownloading}
                onClick={() => void handleDescargarQr('png')}
              >
                Descargar PNG
              </Button>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeQrDialog}>Cerrar</Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
}
