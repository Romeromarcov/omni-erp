import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import {
  getConector,
  testConector,
  triggerSync,
  exportarConector,
  getJobsDeConector,
  type JobSincronizacion,
} from '../../services/integrationHubService';
import { PageContainer, PageHeader, StatusChip, SectionTitle } from '../../components/ui';
import EditarConectorModal from './EditarConectorModal';

const PROVEEDOR_SHEETS = 'google_sheets';

type ChipColor = 'success' | 'warning' | 'error' | 'info' | 'default';

const ESTADO_JOB_COLORS: Record<string, ChipColor> = {
  completado: 'success',
  completado_con_errores: 'warning',
  fallido: 'error',
  en_progreso: 'info',
  pendiente: 'default',
};

/** Etiqueta legible de la dirección de un job (los jobs Sheets son outbound). */
function etiquetaDireccion(direccion: string): { label: string; outbound: boolean } {
  const outbound = direccion === 'outbound';
  return { label: outbound ? 'Exportación' : 'Importación', outbound };
}

const JobRow: React.FC<{ job: JobSincronizacion }> = ({ job }) => {
  const color = ESTADO_JOB_COLORS[job.estado] ?? ESTADO_JOB_COLORS.pendiente;
  const dir = etiquetaDireccion(job.direccion);
  const inicio = job.iniciado_en
    ? new Date(job.iniciado_en).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })
    : '—';
  const duracion = job.duracion_segundos != null ? `${job.duracion_segundos}s` : '—';

  return (
    <TableRow>
      <TableCell>
        <Chip
          size="small"
          label={dir.label}
          color={dir.outbound ? 'secondary' : 'default'}
          variant="outlined"
        />
      </TableCell>
      <TableCell>{job.tipo_entidad}</TableCell>
      <TableCell>
        <Chip size="small" label={job.estado.replace(/_/g, ' ')} color={color} variant={color === 'default' ? 'outlined' : 'filled'} />
      </TableCell>
      <TableCell>{inicio}</TableCell>
      <TableCell align="right">
        {job.creados > 0 && <Box component="span" sx={{ color: 'success.main', mr: 1 }}>+{job.creados}</Box>}
        {job.actualizados > 0 && <Box component="span" sx={{ color: 'primary.main', mr: 1 }}>↺{job.actualizados}</Box>}
        {job.omitidos > 0 && <Box component="span" sx={{ color: 'text.disabled', mr: 1 }}>={job.omitidos}</Box>}
        {job.fallidos > 0 && <Box component="span" sx={{ color: 'error.main' }}>✕{job.fallidos}</Box>}
      </TableCell>
      <TableCell align="right">{duracion}</TableCell>
    </TableRow>
  );
};

const ConectorDetallePage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [syncEntidad, setSyncEntidad] = useState('');
  const [editarAbierto, setEditarAbierto] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; version?: string } | null>(null);

  const { data: conector, isLoading } = useQuery({
    queryKey: [`/integration-hub/instancias/${id}/`],
    queryFn: () => getConector(id!),
    enabled: !!id,
  });

  const { data: jobsData } = useQuery({
    queryKey: [`/integration-hub/instancias/${id}/jobs/`],
    queryFn: () => getJobsDeConector(id!),
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const testMutation = useMutation({
    mutationFn: () => testConector(id!),
    onSuccess: res => setTestResult(res),
    onError: (e: Error) => setTestResult({ success: false, message: e.message }),
  });

  const syncMutation = useMutation({
    mutationFn: () => triggerSync(id!, syncEntidad),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [`/integration-hub/instancias/${id}/jobs/`] });
      qc.invalidateQueries({ queryKey: ['/integration-hub/status/'] });
    },
  });

  // Exportación outbound (Google Sheets). `full` reexporta todo el histórico.
  const exportMutation = useMutation({
    mutationFn: (full: boolean) => exportarConector(id!, { full }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [`/integration-hub/instancias/${id}/jobs/`] });
      qc.invalidateQueries({ queryKey: ['/integration-hub/status/'] });
    },
  });

  if (isLoading) return (
    <PageContainer><Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box></PageContainer>
  );
  if (!conector) return (
    <PageContainer><Alert severity="error">Conector no encontrado.</Alert></PageContainer>
  );

  const jobs = jobsData?.results ?? [];
  const esSheets = conector.proveedor_codigo === PROVEEDOR_SHEETS;

  return (
    <PageContainer>
      {/* Back */}
      <Button onClick={() => navigate('/integraciones')} sx={{ mb: 2 }}>
        ← Volver al Integration Hub
      </Button>

      <PageHeader
        title={conector.nombre}
        subtitle={`${conector.proveedor_nombre}${conector.version_detectada ? ` · v${conector.version_detectada}` : ''}`}
        actions={
          <>
            <StatusChip value={conector.estado} colorMap={{ activo: 'success', configurando: 'warning', error: 'error', inactivo: 'default' }} />
            <Button variant="outlined" onClick={() => setEditarAbierto(true)}>
              Editar
            </Button>
            <Button
              variant="outlined"
              onClick={() => { testMutation.reset(); setTestResult(null); testMutation.mutate(); }}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? 'Probando…' : 'Probar conexión'}
            </Button>
          </>
        }
      />

      {editarAbierto && (
        <EditarConectorModal conector={conector} onClose={() => setEditarAbierto(false)} />
      )}

      {/* Test result */}
      {testResult && (
        <Alert severity={testResult.success ? 'success' : 'error'} sx={{ mb: 3 }}>
          {testResult.message}
          {testResult.version && <Box component="span" sx={{ ml: 1, opacity: 0.7 }}>({testResult.version})</Box>}
        </Alert>
      )}

      {/* Config info */}
      <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
        <SectionTitle>Configuración</SectionTitle>
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', rowGap: 0.75, columnGap: 3 }}>
          {conector.configuracion_publica?.host && (
            <>
              <Typography variant="body2" color="text.secondary">Host</Typography>
              <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{conector.configuracion_publica.host}</Typography>
            </>
          )}
          {conector.configuracion_publica?.user && (
            <>
              <Typography variant="body2" color="text.secondary">Usuario</Typography>
              <Typography variant="body2">{conector.configuracion_publica.user}</Typography>
            </>
          )}
          <Typography variant="body2" color="text.secondary">Intervalo sync</Typography>
          <Typography variant="body2">Cada {conector.intervalo_sync_minutos} min</Typography>
          <Typography variant="body2" color="text.secondary">Último sync</Typography>
          <Typography variant="body2">{conector.ultimo_sync ? new Date(conector.ultimo_sync).toLocaleString('es-VE') : 'Nunca'}</Typography>
        </Box>

        {conector.entidades_activas.length > 0 && (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap mt={1.5} alignItems="center">
            <Typography variant="body2" color="text.secondary">Entidades:</Typography>
            {conector.entidades_activas.map(e => (
              <Chip key={e} size="small" label={e} color="info" variant="outlined" />
            ))}
          </Stack>
        )}
      </Paper>

      {/* Exportar ahora — solo conectores Google Sheets (outbound) */}
      {esSheets && (
        <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
          <SectionTitle>Exportar a Google Sheets</SectionTitle>
          <Typography variant="body2" color="text.secondary" mb={1.5}>
            Exporta las entidades activas del conector de origen a la planilla. Se encola
            una tarea en segundo plano; sigue el avance en el historial de jobs.
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate(false)}
            >
              {exportMutation.isPending ? 'Encolando…' : 'Exportar ahora'}
            </Button>
            <Button
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate(true)}
            >
              Exportar todo (full)
            </Button>
          </Stack>
          {exportMutation.isSuccess && (
            <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 1 }}>
              Exportación encolada — {exportMutation.data.mensaje}
            </Typography>
          )}
          {exportMutation.isError && (
            <Typography variant="caption" color="error.main" sx={{ display: 'block', mt: 1 }}>
              Error: {(exportMutation.error as Error).message}
            </Typography>
          )}
        </Paper>
      )}

      {/* Disparar sync — solo conectores de entrada (no aplica a Google Sheets) */}
      {!esSheets && (
      <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
        <SectionTitle>Sincronización manual</SectionTitle>
        <Stack direction="row" spacing={1}>
          <TextField
            select
            size="small"
            value={syncEntidad}
            onChange={e => setSyncEntidad(e.target.value)}
            sx={{ flex: 1 }}
          >
            <MenuItem value="">Seleccionar entidad…</MenuItem>
            {conector.entidades_activas.map(e => (
              <MenuItem key={e} value={e}>{e}</MenuItem>
            ))}
          </TextField>
          <Button
            variant="contained"
            disabled={!syncEntidad || syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            {syncMutation.isPending ? 'Iniciando…' : 'Sincronizar'}
          </Button>
        </Stack>
        {syncMutation.isSuccess && syncMutation.data?.job_id && (
          <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 1 }}>
            Job iniciado — {syncMutation.data.mensaje}
          </Typography>
        )}
        {syncMutation.isError && (
          <Typography variant="caption" color="error.main" sx={{ display: 'block', mt: 1 }}>
            Error: {(syncMutation.error as Error).message}
          </Typography>
        )}
      </Paper>
      )}

      {/* Jobs recientes */}
      <Paper variant="outlined">
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <SectionTitle>Jobs recientes</SectionTitle>
        </Box>
        {jobs.length === 0 ? (
          <Typography align="center" color="text.secondary" py={4}>Sin jobs registrados aún.</Typography>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Tipo</TableCell>
                  <TableCell>Entidad</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Inicio</TableCell>
                  <TableCell align="right">Registros</TableCell>
                  <TableCell align="right">Duración</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {jobs.map(j => <JobRow key={j.id_job} job={j} />)}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </PageContainer>
  );
};

export default ConectorDetallePage;
