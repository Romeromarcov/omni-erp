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
  getJobsDeConector,
  type JobSincronizacion,
} from '../../services/integrationHubService';
import { PageContainer, PageHeader, StatusChip, SectionTitle } from '../../components/ui';

type ChipColor = 'success' | 'warning' | 'error' | 'info' | 'default';

const ESTADO_JOB_COLORS: Record<string, ChipColor> = {
  completado: 'success',
  completado_con_errores: 'warning',
  fallido: 'error',
  en_progreso: 'info',
  pendiente: 'default',
};

const JobRow: React.FC<{ job: JobSincronizacion }> = ({ job }) => {
  const color = ESTADO_JOB_COLORS[job.estado] ?? ESTADO_JOB_COLORS.pendiente;
  const inicio = job.iniciado_en
    ? new Date(job.iniciado_en).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })
    : '—';
  const duracion = job.duracion_segundos != null ? `${job.duracion_segundos}s` : '—';

  return (
    <TableRow>
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

  if (isLoading) return (
    <PageContainer><Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box></PageContainer>
  );
  if (!conector) return (
    <PageContainer><Alert severity="error">Conector no encontrado.</Alert></PageContainer>
  );

  const jobs = jobsData?.results ?? [];

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

      {/* Disparar sync */}
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
