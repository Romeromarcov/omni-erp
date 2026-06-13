/**
 * Listado de Procesos de Nómina (workstream F) — estado de cada corrida LOTTT
 * y creación de procesos y períodos. El procesamiento (operación de dinero)
 * vive en el detalle del proceso.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import EventOutlined from '@mui/icons-material/EventOutlined';
import { nominaService } from '../../services/nominaService';
import type { ProcesoNomina, TipoPeriodoNomina } from '../../services/nominaService';
import {
  periodoNominaSchema,
  procesoNominaSchema,
  type PeriodoNominaInput,
  type ProcesoNominaInput,
} from '../../schemas/nomina.schemas';
import { nominaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

/** Colores del chip por estado del proceso (EN_PROCESO no está en el mapa global). */
const COLOR_ESTADO_PROCESO = {
  en_proceso: 'warning',
  completado: 'success',
  aprobado: 'info',
  cancelado: 'error',
} as const;

const TIPOS_PERIODO: TipoPeriodoNomina[] = ['SEMANAL', 'QUINCENAL', 'MENSUAL', 'ANUAL'];

export default function ProcesosNominaListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [page, setPage] = useState(1);
  const [dialogoProceso, setDialogoProceso] = useState(false);
  const [dialogoPeriodo, setDialogoPeriodo] = useState(false);
  const [errorProceso, setErrorProceso] = useState('');
  const [errorPeriodo, setErrorPeriodo] = useState('');
  const empresaId = getEmpresaId() || '';

  const { data, isLoading } = useQuery({
    queryKey: nominaKeys.procesos(page),
    queryFn: () => nominaService.getProcesosPaginated(page),
  });

  const { data: periodos = [] } = useQuery({
    queryKey: nominaKeys.periodos(),
    queryFn: () => nominaService.getPeriodos(),
  });

  const nombrePeriodo = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const p of periodos) mapa.set(p.id_periodo_nomina, p.nombre_periodo);
    return (id: string) => mapa.get(id) ?? '—';
  }, [periodos]);

  // El proceso se crea contra un período de la MISMA empresa activa (R-CODE-1).
  const periodosDeEmpresa = useMemo(
    () => periodos.filter((p) => p.id_empresa === empresaId),
    [periodos, empresaId],
  );

  const formProceso = useForm<ProcesoNominaInput>({
    resolver: zodResolver(procesoNominaSchema),
    defaultValues: { id_periodo_nomina: '', numero_proceso: '' },
  });

  const formPeriodo = useForm<PeriodoNominaInput>({
    resolver: zodResolver(periodoNominaSchema),
    defaultValues: {
      nombre_periodo: '',
      tipo_periodo: 'MENSUAL',
      fecha_inicio: '',
      fecha_fin: '',
      fecha_pago: '',
    },
  });

  const crearProcesoMutation = useMutation({
    mutationFn: (input: ProcesoNominaInput) =>
      nominaService.crearProceso({
        id_empresa: empresaId,
        id_periodo_nomina: input.id_periodo_nomina,
        numero_proceso: input.numero_proceso,
        // Provisional: al procesar, el backend fija la fecha real del cálculo.
        fecha_proceso: new Date().toISOString(),
      }),
    onSuccess: (proceso) => {
      snackbar.success(t('nomina.procesos.creado', { numero: proceso.numero_proceso }));
      void queryClient.invalidateQueries({ queryKey: nominaKeys.procesosAll() });
      setDialogoProceso(false);
      navigate(`/nomina/procesos/${proceso.id_proceso_nomina}`);
    },
    onError: (err: unknown) => {
      // 400 del backend: numero_proceso duplicado, período de otra empresa…
      setErrorProceso(mensajeDeError(err, t('nomina.procesos.errorCrear')));
    },
  });

  const crearPeriodoMutation = useMutation({
    mutationFn: (input: PeriodoNominaInput) =>
      nominaService.crearPeriodo({
        id_empresa: empresaId,
        nombre_periodo: input.nombre_periodo,
        tipo_periodo: input.tipo_periodo,
        fecha_inicio: input.fecha_inicio,
        fecha_fin: input.fecha_fin,
        fecha_pago: input.fecha_pago,
      }),
    onSuccess: (periodo) => {
      snackbar.success(t('nomina.periodos.creado', { nombre: periodo.nombre_periodo }));
      void queryClient.invalidateQueries({ queryKey: nominaKeys.periodos() });
      setDialogoPeriodo(false);
    },
    onError: (err: unknown) => {
      setErrorPeriodo(mensajeDeError(err, t('nomina.periodos.errorCrear')));
    },
  });

  function abrirDialogoProceso() {
    setErrorProceso('');
    formProceso.reset({ id_periodo_nomina: '', numero_proceso: '' });
    setDialogoProceso(true);
  }

  function abrirDialogoPeriodo() {
    setErrorPeriodo('');
    formPeriodo.reset({
      nombre_periodo: '',
      tipo_periodo: 'MENSUAL',
      fecha_inicio: '',
      fecha_fin: '',
      fecha_pago: '',
    });
    setDialogoPeriodo(true);
  }

  const procesos = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<ProcesoNomina>[] = [
    {
      key: 'numero',
      header: t('nomina.procesos.numero'),
      render: (p) => (
        <Typography variant="body2" fontWeight={600}>
          {p.numero_proceso}
        </Typography>
      ),
    },
    {
      key: 'periodo',
      header: t('nomina.procesos.periodo'),
      render: (p) => nombrePeriodo(p.id_periodo_nomina),
    },
    {
      key: 'fecha',
      header: t('nomina.procesos.fecha'),
      render: (p) => p.fecha_proceso.slice(0, 10),
    },
    {
      key: 'empleados',
      header: t('nomina.procesos.empleados'),
      align: 'right',
      render: (p) => p.total_empleados,
    },
    {
      key: 'neto',
      header: t('nomina.procesos.totalNeto'),
      align: 'right',
      render: (p) => (
        <Typography component="span" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {toFixedStr(p.total_neto)}
        </Typography>
      ),
    },
    {
      key: 'estado',
      header: t('nomina.procesos.estado'),
      render: (p) => <StatusChip value={p.estado} colorMap={COLOR_ESTADO_PROCESO} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      align: 'right',
      render: (p) => (
        <Button size="small" onClick={() => navigate(`/nomina/procesos/${p.id_proceso_nomina}`)}>
          {t('nomina.procesos.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('nomina.procesos.title')}
        subtitle={t('nomina.procesos.subtitle')}
        actions={
          <>
            <Button variant="outlined" startIcon={<EventOutlined />} onClick={abrirDialogoPeriodo}>
              {t('nomina.periodos.nuevo')}
            </Button>
            <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirDialogoProceso}>
              {t('nomina.procesos.nuevo')}
            </Button>
          </>
        }
      />
      <DataTable
        columns={columns}
        rows={procesos}
        getRowKey={(p) => p.id_proceso_nomina}
        loading={isLoading}
        emptyMessage={t('nomina.procesos.empty')}
        onRowClick={(p) => navigate(`/nomina/procesos/${p.id_proceso_nomina}`)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />

      {/* ── Diálogo: nuevo proceso ──────────────────────────────────────────── */}
      <Dialog open={dialogoProceso} onClose={() => setDialogoProceso(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('nomina.procesos.nuevo')}</DialogTitle>
        <form
          onSubmit={formProceso.handleSubmit((input) => {
            setErrorProceso('');
            crearProcesoMutation.mutate(input);
          })}
          noValidate
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorProceso && <Alert severity="error">{errorProceso}</Alert>}
              {!empresaId && <Alert severity="warning">{t('nomina.sinEmpresa')}</Alert>}
              {empresaId && periodosDeEmpresa.length === 0 && (
                <Alert severity="info">{t('nomina.procesos.sinPeriodos')}</Alert>
              )}
              <TextField
                select
                label={t('nomina.procesos.periodo')}
                defaultValue=""
                fullWidth
                required
                error={!!formProceso.formState.errors.id_periodo_nomina}
                helperText={formProceso.formState.errors.id_periodo_nomina?.message}
                {...formProceso.register('id_periodo_nomina')}
              >
                {periodosDeEmpresa.map((p) => (
                  <MenuItem key={p.id_periodo_nomina} value={p.id_periodo_nomina}>
                    {p.nombre_periodo} ({p.fecha_inicio} – {p.fecha_fin})
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label={t('nomina.procesos.numero')}
                fullWidth
                required
                placeholder="NOM-2026-06"
                error={!!formProceso.formState.errors.numero_proceso}
                helperText={formProceso.formState.errors.numero_proceso?.message}
                {...formProceso.register('numero_proceso')}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDialogoProceso(false)} disabled={crearProcesoMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={crearProcesoMutation.isPending || !empresaId}
            >
              {t('nomina.procesos.crear')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* ── Diálogo: nuevo período ──────────────────────────────────────────── */}
      <Dialog open={dialogoPeriodo} onClose={() => setDialogoPeriodo(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('nomina.periodos.nuevo')}</DialogTitle>
        <form
          onSubmit={formPeriodo.handleSubmit((input) => {
            setErrorPeriodo('');
            crearPeriodoMutation.mutate(input);
          })}
          noValidate
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorPeriodo && <Alert severity="error">{errorPeriodo}</Alert>}
              {!empresaId && <Alert severity="warning">{t('nomina.sinEmpresa')}</Alert>}
              <TextField
                label={t('nomina.periodos.nombre')}
                fullWidth
                required
                placeholder="Junio 2026"
                error={!!formPeriodo.formState.errors.nombre_periodo}
                helperText={formPeriodo.formState.errors.nombre_periodo?.message}
                {...formPeriodo.register('nombre_periodo')}
              />
              <TextField
                select
                label={t('nomina.periodos.tipo')}
                defaultValue="MENSUAL"
                fullWidth
                required
                error={!!formPeriodo.formState.errors.tipo_periodo}
                helperText={formPeriodo.formState.errors.tipo_periodo?.message}
                {...formPeriodo.register('tipo_periodo')}
              >
                {TIPOS_PERIODO.map((tipo) => (
                  <MenuItem key={tipo} value={tipo}>
                    {t(`nomina.periodos.tipos.${tipo}`)}
                  </MenuItem>
                ))}
              </TextField>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label={t('nomina.periodos.fechaInicio')}
                  type="date"
                  fullWidth
                  required
                  InputLabelProps={{ shrink: true }}
                  error={!!formPeriodo.formState.errors.fecha_inicio}
                  helperText={formPeriodo.formState.errors.fecha_inicio?.message}
                  {...formPeriodo.register('fecha_inicio')}
                />
                <TextField
                  label={t('nomina.periodos.fechaFin')}
                  type="date"
                  fullWidth
                  required
                  InputLabelProps={{ shrink: true }}
                  error={!!formPeriodo.formState.errors.fecha_fin}
                  helperText={formPeriodo.formState.errors.fecha_fin?.message}
                  {...formPeriodo.register('fecha_fin')}
                />
                <TextField
                  label={t('nomina.periodos.fechaPago')}
                  type="date"
                  fullWidth
                  required
                  InputLabelProps={{ shrink: true }}
                  error={!!formPeriodo.formState.errors.fecha_pago}
                  helperText={formPeriodo.formState.errors.fecha_pago?.message}
                  {...formPeriodo.register('fecha_pago')}
                />
              </Stack>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDialogoPeriodo(false)} disabled={crearPeriodoMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={crearPeriodoMutation.isPending || !empresaId}
            >
              {t('nomina.periodos.crear')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
