/**
 * Detalle de Proceso de Nómina (workstream F): totales del proceso, recibos por
 * empleado (devengado / deducciones / neto con decimal.js) y el botón Procesar.
 *
 * Procesar (POST /nomina/procesos-nomina/{id}/procesar/, PR #80) es una operación
 * de dinero atómica en el backend. El diálogo captura los datos variables por
 * empleado (horas extra diurnas/nocturnas y bono nocturno) y maneja:
 *   · 422 — contabilidad activa sin mapeo NOMINA → alerta con link a
 *     /contabilidad/mapeos para configurarlo;
 *   · 400 — re-proceso de un proceso COMPLETADO/APROBADO/CANCELADO: los recibos
 *     emitidos son inmutables (hay que cancelar y crear un proceso nuevo).
 */
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useFieldArray, useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import PlayArrowOutlined from '@mui/icons-material/PlayArrowOutlined';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import { nominaService } from '../../services/nominaService';
import type { DatosVariablesEmpleado, ReciboNomina } from '../../services/nominaService';
import { rrhhService } from '../../services/rrhhService';
import type { Empleado } from '../../services/rrhhService';
import {
  procesarNominaSchema,
  type FilaProcesarEmpleadoInput,
  type ProcesarNominaInput,
} from '../../schemas/nomina.schemas';
import { nominaKeys, rrhhKeys } from '../../lib/queryKeys';
import { mensajeDeError, statusDeError } from '../../utils/api';
import { D, sumDecimals, toFixedStr } from '../../lib/decimal';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, KpiCard, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const COLOR_ESTADO_PROCESO = {
  en_proceso: 'warning',
  completado: 'success',
  aprobado: 'info',
  cancelado: 'error',
} as const;

interface ErrorProcesar {
  /** Status HTTP del backend (422 = falta mapeo NOMINA; 400 = regla de negocio). */
  status?: number;
  mensaje: string;
}

/** Convierte una fila del formulario al objeto de datos variables del backend
 * (claves de `_CAMPOS_DATOS_EMPLEADO`); solo incluye valores con efecto. */
function datosDeFila(fila: FilaProcesarEmpleadoInput): DatosVariablesEmpleado {
  const datos: DatosVariablesEmpleado = {};
  if (fila.horas_extra_diurnas !== '' && D(fila.horas_extra_diurnas).greaterThan(0)) {
    datos.horas_extra_diurnas = fila.horas_extra_diurnas;
  }
  if (fila.horas_extra_nocturnas !== '' && D(fila.horas_extra_nocturnas).greaterThan(0)) {
    datos.horas_extra_nocturnas = fila.horas_extra_nocturnas;
  }
  // "Bono nocturno: sí" = enviar las horas nocturnas que generan el recargo 30%.
  if (fila.bono_nocturno && fila.horas_nocturnas !== '' && D(fila.horas_nocturnas).greaterThan(0)) {
    datos.horas_nocturnas = fila.horas_nocturnas;
  }
  return datos;
}

export default function ProcesoNominaDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogoProcesar, setDialogoProcesar] = useState(false);
  const [errorProcesar, setErrorProcesar] = useState<ErrorProcesar | null>(null);

  const { data: proceso, isLoading: cargandoProceso } = useQuery({
    queryKey: nominaKeys.proceso(id),
    queryFn: () => nominaService.getProceso(id),
    enabled: !!id,
  });

  const { data: recibos = [], isLoading: cargandoRecibos } = useQuery({
    queryKey: nominaKeys.recibos(id),
    queryFn: () => nominaService.getRecibosProceso(id),
    enabled: !!id,
  });

  const { data: periodos = [] } = useQuery({
    queryKey: nominaKeys.periodos(),
    queryFn: () => nominaService.getPeriodos(),
  });

  // Empleados de la empresa del proceso: los activos alimentan el diálogo de
  // procesar; todos (incl. inactivos) dan nombre a los recibos históricos.
  const empresaProceso = proceso?.id_empresa ?? '';
  const { data: empleados = [], isLoading: cargandoEmpleados } = useQuery({
    queryKey: rrhhKeys.empleadosDeEmpresa(empresaProceso),
    queryFn: () => rrhhService.getEmpleadosDeEmpresa(empresaProceso),
    enabled: !!empresaProceso,
  });

  const empleadosActivos = useMemo(() => empleados.filter((e) => e.activo), [empleados]);

  const empleadoPorId = useMemo(() => {
    const mapa = new Map<number, Empleado>();
    for (const e of empleados) mapa.set(e.id, e);
    return mapa;
  }, [empleados]);

  const periodo = useMemo(
    () => periodos.find((p) => p.id_periodo_nomina === proceso?.id_periodo_nomina),
    [periodos, proceso],
  );

  const form = useForm<ProcesarNominaInput>({
    resolver: zodResolver(procesarNominaSchema),
    defaultValues: { empleados: [] },
  });
  const filas = useFieldArray({ control: form.control, name: 'empleados' });

  const procesarMutation = useMutation({
    mutationFn: (input: ProcesarNominaInput) => {
      const datos: Record<string, DatosVariablesEmpleado> = {};
      for (const fila of input.empleados) {
        const datosFila = datosDeFila(fila);
        if (Object.keys(datosFila).length > 0) datos[fila.id_empleado] = datosFila;
      }
      return nominaService.procesarProceso(id, datos);
    },
    onSuccess: (res) => {
      snackbar.success(t('nomina.detalle.procesadoOk', { neto: toFixedStr(res.total_neto) }));
      if (res.advertencia_asiento) {
        // Contabilidad inactiva sin mapeo: el proceso quedó OK pero sin asiento.
        snackbar.warning(res.advertencia_asiento);
      }
      // El prefijo ['nomina','procesos'] invalida lista, detalle y recibos a la vez.
      void queryClient.invalidateQueries({ queryKey: nominaKeys.procesosAll() });
      cerrarProcesar();
    },
    onError: (err: unknown) => {
      setErrorProcesar({
        status: statusDeError(err),
        mensaje: mensajeDeError(err, t('nomina.detalle.errorProcesar')),
      });
    },
  });

  const aprobarProcesoMutation = useMutation({
    mutationFn: () => nominaService.aprobarProceso(id),
    onSuccess: () => {
      snackbar.success(t('nomina.detalle.aprobadoOk'));
      void queryClient.invalidateQueries({ queryKey: nominaKeys.procesosAll() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, t('nomina.detalle.errorAprobar')));
    },
  });

  const aprobarReciboMutation = useMutation({
    mutationFn: (reciboId: string) => nominaService.aprobarRecibo(reciboId),
    onSuccess: () => {
      snackbar.success(t('nomina.detalle.reciboAprobadoOk'));
      void queryClient.invalidateQueries({ queryKey: nominaKeys.procesosAll() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, t('nomina.detalle.errorReciboAccion')));
    },
  });

  const marcarPagadaMutation = useMutation({
    mutationFn: (reciboId: string) => nominaService.marcarReciboPagada(reciboId),
    onSuccess: () => {
      snackbar.success(t('nomina.detalle.reciboPagadoOk'));
      void queryClient.invalidateQueries({ queryKey: nominaKeys.procesosAll() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, t('nomina.detalle.errorReciboAccion')));
    },
  });

  // Una acción de recibo a la vez evita doble submit sobre la misma fila.
  const accionReciboPendiente =
    aprobarReciboMutation.isPending || marcarPagadaMutation.isPending;

  function abrirProcesar() {
    setErrorProcesar(null);
    form.reset({
      empleados: empleadosActivos.map((e) => ({
        id_empleado: String(e.id),
        horas_extra_diurnas: '',
        horas_extra_nocturnas: '',
        bono_nocturno: false,
        horas_nocturnas: '',
      })),
    });
    setDialogoProcesar(true);
  }

  function cerrarProcesar() {
    setDialogoProcesar(false);
    setErrorProcesar(null);
  }

  const nombreEmpleado = (idEmpleado: number): string => {
    const e = empleadoPorId.get(idEmpleado);
    return e ? `${e.nombre} ${e.apellido}` : `#${idEmpleado}`;
  };

  const columnasRecibos: Column<ReciboNomina>[] = [
    {
      key: 'empleado',
      header: t('nomina.detalle.empleado'),
      render: (r) => (
        <Typography variant="body2" fontWeight={600}>
          {nombreEmpleado(r.id_empleado)}
        </Typography>
      ),
    },
    {
      key: 'sueldo',
      header: t('nomina.detalle.sueldoBase'),
      align: 'right',
      render: (r) => toFixedStr(r.sueldo_base),
    },
    {
      key: 'devengado',
      header: t('nomina.detalle.devengado'),
      align: 'right',
      render: (r) => toFixedStr(r.total_devengado),
    },
    {
      key: 'deducciones',
      header: t('nomina.detalle.deducciones'),
      align: 'right',
      render: (r) => toFixedStr(r.total_deducciones),
    },
    {
      key: 'neto',
      header: t('nomina.detalle.neto'),
      align: 'right',
      render: (r) => (
        <Typography component="span" fontWeight={600} sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {toFixedStr(r.total_neto)}
        </Typography>
      ),
    },
    {
      key: 'estado',
      header: t('nomina.procesos.estado'),
      render: (r) => <StatusChip value={r.estado} />,
    },
    {
      key: 'acciones',
      header: t('nomina.detalle.acciones'),
      align: 'right',
      render: (r) =>
        r.estado === 'CALCULADA' ? (
          <Button
            size="small"
            onClick={() => aprobarReciboMutation.mutate(r.id_nomina)}
            disabled={accionReciboPendiente}
          >
            {t('nomina.detalle.aprobarRecibo')}
          </Button>
        ) : r.estado === 'APROBADA' ? (
          <Button
            size="small"
            variant="contained"
            onClick={() => marcarPagadaMutation.mutate(r.id_nomina)}
            disabled={accionReciboPendiente}
          >
            {t('nomina.detalle.marcarPagada')}
          </Button>
        ) : null,
    },
  ];

  // Totales de control sumados con decimal.js sobre los recibos (R-CODE-4).
  const totalNetoRecibos = useMemo(
    () => sumDecimals(recibos.map((r) => r.total_neto)),
    [recibos],
  );

  if (cargandoProceso) {
    return (
      <PageContainer>
        <Stack alignItems="center" sx={{ py: 8 }}>
          <CircularProgress />
        </Stack>
      </PageContainer>
    );
  }

  const enProceso = proceso?.estado === 'EN_PROCESO';
  const completado = proceso?.estado === 'COMPLETADO';

  return (
    <PageContainer>
      <PageHeader
        title={`${t('nomina.detalle.title')} ${proceso?.numero_proceso ?? ''}`}
        subtitle={
          periodo
            ? `${t('nomina.procesos.periodo')}: ${periodo.nombre_periodo} (${periodo.fecha_inicio} – ${periodo.fecha_fin})`
            : undefined
        }
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate('/nomina/procesos')}>
              {t('common.back')}
            </Button>
            <Button
              variant="contained"
              startIcon={<PlayArrowOutlined />}
              onClick={abrirProcesar}
              disabled={!enProceso || cargandoEmpleados}
            >
              {t('nomina.detalle.procesar')}
            </Button>
            {completado && (
              <Button
                variant="contained"
                color="success"
                startIcon={<CheckCircleOutlined />}
                onClick={() => aprobarProcesoMutation.mutate()}
                disabled={aprobarProcesoMutation.isPending}
              >
                {t('nomina.detalle.aprobar')}
              </Button>
            )}
          </>
        }
      />

      {proceso && (
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('nomina.procesos.estado')}:
          </Typography>
          <StatusChip value={proceso.estado} colorMap={COLOR_ESTADO_PROCESO} />
        </Stack>
      )}

      {proceso && !enProceso && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('nomina.detalle.recibosInmutables')}
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
          gap: 2,
          mb: 3,
        }}
      >
        <KpiCard
          label={t('nomina.procesos.empleados')}
          value={proceso?.total_empleados ?? 0}
          tone="tint"
        />
        <KpiCard
          label={t('nomina.detalle.devengado')}
          value={toFixedStr(proceso?.total_devengado ?? '0')}
          tone="success"
        />
        <KpiCard
          label={t('nomina.detalle.deducciones')}
          value={toFixedStr(proceso?.total_deducciones ?? '0')}
          tone="warning"
        />
        <KpiCard
          label={t('nomina.detalle.neto')}
          value={toFixedStr(proceso?.total_neto ?? '0')}
          tone="brand"
        />
      </Box>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('nomina.detalle.recibos')}
        </Typography>
        {!cargandoRecibos && recibos.length === 0 ? (
          <Alert severity="info">
            {enProceso ? t('nomina.detalle.sinRecibosEnProceso') : t('nomina.detalle.sinRecibos')}
          </Alert>
        ) : (
          <>
            <DataTable
              columns={columnasRecibos}
              rows={recibos}
              getRowKey={(r) => r.id_nomina}
              loading={cargandoRecibos}
              emptyMessage={t('nomina.detalle.sinRecibos')}
            />
            <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2 }}>
              <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {`${t('nomina.detalle.totalNetoRecibos')}: ${toFixedStr(totalNetoRecibos)}`}
              </Typography>
            </Stack>
          </>
        )}
      </Paper>

      {/* ── Diálogo: procesar nómina (datos variables por empleado) ─────────── */}
      <Dialog open={dialogoProcesar} onClose={cerrarProcesar} fullWidth maxWidth="md">
        <DialogTitle>{t('nomina.detalle.procesarTitulo')}</DialogTitle>
        <form
          onSubmit={form.handleSubmit((input) => {
            setErrorProcesar(null);
            procesarMutation.mutate(input);
          })}
          noValidate
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorProcesar && (
                <Alert
                  severity="error"
                  action={
                    errorProcesar.status === 422 ? (
                      <Button
                        color="inherit"
                        size="small"
                        onClick={() => navigate('/contabilidad/mapeos')}
                      >
                        {t('nomina.detalle.irAMapeos')}
                      </Button>
                    ) : undefined
                  }
                >
                  {errorProcesar.status === 422
                    ? `${t('nomina.detalle.faltaMapeo')} ${errorProcesar.mensaje}`
                    : errorProcesar.mensaje}
                </Alert>
              )}
              <Typography variant="body2" color="text.secondary">
                {t('nomina.detalle.procesarAyuda')}
              </Typography>
              {filas.fields.length === 0 && (
                <Alert severity="warning">{t('nomina.detalle.sinEmpleadosActivos')}</Alert>
              )}
              {filas.fields.map((fila, idx) => {
                const empleado = empleadoPorId.get(Number(fila.id_empleado));
                const salario = empleado?.documento_json?.salario_mensual;
                const bonoActivo = form.watch(`empleados.${idx}.bono_nocturno`);
                // eslint-disable-next-line security/detect-object-injection -- FP: idx es el índice entero de fields.map de RHF, no entrada del usuario
                const erroresFila = form.formState.errors.empleados?.[idx];
                return (
                  <Paper key={fila.id} variant="outlined" sx={{ p: 2 }}>
                    <Stack
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      flexWrap="wrap"
                      useFlexGap
                      sx={{ mb: 1.5 }}
                    >
                      <Typography variant="body2" fontWeight={600}>
                        {empleado
                          ? `${empleado.nombre} ${empleado.apellido} (${empleado.cedula})`
                          : `#${fila.id_empleado}`}
                      </Typography>
                      {typeof salario === 'string' && salario !== '' ? (
                        <Typography variant="caption" color="text.secondary">
                          {t('rrhh.form.salario')}: {toFixedStr(salario)}
                        </Typography>
                      ) : (
                        <Chip size="small" color="warning" label={t('nomina.detalle.sinSalario')} />
                      )}
                    </Stack>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
                      <TextField
                        size="small"
                        inputMode="decimal"
                        label={t('nomina.detalle.horasExtraDiurnas')}
                        error={!!erroresFila?.horas_extra_diurnas}
                        helperText={
                          erroresFila?.horas_extra_diurnas?.message
                        }
                        {...form.register(`empleados.${idx}.horas_extra_diurnas`)}
                      />
                      <TextField
                        size="small"
                        inputMode="decimal"
                        label={t('nomina.detalle.horasExtraNocturnas')}
                        error={!!erroresFila?.horas_extra_nocturnas}
                        helperText={
                          erroresFila?.horas_extra_nocturnas?.message
                        }
                        {...form.register(`empleados.${idx}.horas_extra_nocturnas`)}
                      />
                      <Controller
                        name={`empleados.${idx}.bono_nocturno`}
                        control={form.control}
                        render={({ field }) => (
                          <FormControlLabel
                            control={
                              <Switch
                                checked={field.value}
                                onChange={(_, checked) => field.onChange(checked)}
                              />
                            }
                            label={t('nomina.detalle.bonoNocturno')}
                            sx={{ whiteSpace: 'nowrap' }}
                          />
                        )}
                      />
                      {bonoActivo && (
                        <TextField
                          size="small"
                          inputMode="decimal"
                          label={t('nomina.detalle.horasNocturnas')}
                          error={!!erroresFila?.horas_nocturnas}
                          helperText={
                            erroresFila?.horas_nocturnas?.message
                          }
                          {...form.register(`empleados.${idx}.horas_nocturnas`)}
                        />
                      )}
                    </Stack>
                  </Paper>
                );
              })}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarProcesar} disabled={procesarMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={procesarMutation.isPending || filas.fields.length === 0}
              startIcon={procesarMutation.isPending ? <CircularProgress size={16} /> : undefined}
            >
              {t('nomina.detalle.confirmarProcesar')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
