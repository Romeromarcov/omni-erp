/**
 * Diarios Contables y Períodos / Cierre de Ejercicio (Ola B1).
 *
 * Tab 0: CRUD de Diarios Contables (códigos, tipos, prefijos/secuencias atómicas,
 *        cuentas por defecto Debe/Haber).
 * Tab 1: Períodos Contables mensuales (cerrar / reabrir) + Cierre de Ejercicio Anual.
 */
import { useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import LockOutlined from '@mui/icons-material/LockOutlined';
import LockOpenOutlined from '@mui/icons-material/LockOpenOutlined';
import EventAvailableOutlined from '@mui/icons-material/EventAvailableOutlined';
import {
  contabilidadService,
  type DiarioContable,
  type PeriodoContable,
  type TipoDiario,
} from '../../services/contabilidadService';
import { diarioContableSchema, type DiarioContableInput } from '../../schemas/contabilidad.schemas';
import { contabilidadKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';
import { FeedbackContext } from '../../contexts/feedbackTypes';
import { DataTable, PageContainer, PageHeader, StatusChip, type Column } from '../../components/ui';

const TIPOS_DIARIO: TipoDiario[] = ['VENTAS', 'COMPRAS', 'BANCO', 'CAJA', 'NOMINA', 'VARIOS'];
const MESES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

interface DiariosContablesPageProps {
  initialTab?: 'diarios' | 'periodos';
}

export default function DiariosContablesPage({ initialTab = 'diarios' }: DiariosContablesPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const feedback = useContext(FeedbackContext);
  const empresaId = getEmpresaId() || '';

  const [tab, setTab] = useState<'diarios' | 'periodos'>(initialTab);
  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  // ── Estado Diarios ───────────────────────────────────────────────────────
  const [filtroTipo, setFiltroTipo] = useState<string>('');
  const [diarioDialogOpen, setDiarioDialogOpen] = useState(false);
  const [editandoDiario, setEditandoDiario] = useState<DiarioContable | null>(null);
  const [diarioError, setDiarioError] = useState('');

  // ── Estado Períodos y Cierre ─────────────────────────────────────────────
  const anioActual = new Date().getFullYear();
  const [filtroAnio, setFiltroAnio] = useState<string>('');
  const [cerrarPeriodoOpen, setCerrarPeriodoOpen] = useState(false);
  const [cerrarAnio, setCerrarAnio] = useState<string>(String(anioActual));
  const [cerrarMes, setCerrarMes] = useState<string>(String(new Date().getMonth() + 1));
  const [cerrarObs, setCerrarObs] = useState('');
  const [periodoError, setPeriodoError] = useState('');

  const [reabrirTarget, setReabrirTarget] = useState<PeriodoContable | null>(null);
  const [reabrirMotivo, setReabrirMotivo] = useState('');
  const [reabrirError, setReabrirError] = useState('');

  const [cierreEjercicioOpen, setCierreEjercicioOpen] = useState(false);
  const [ejercicioAnio, setEjercicioAnio] = useState<string>(String(anioActual));
  const [cuentaPatrimonioId, setCuentaPatrimonioId] = useState('');
  const [fechaCierreEjercicio, setFechaCierreEjercicio] = useState('');
  const [ejercicioError, setEjercicioError] = useState('');
  const [bannerInfo, setBannerInfo] = useState('');

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: diarios = [], isLoading: loadingDiarios } = useQuery({
    queryKey: contabilidadKeys.diarios(filtroTipo || null),
    queryFn: () => contabilidadService.getDiarios(filtroTipo ? { tipo: filtroTipo } : {}),
  });

  const { data: cuentas = [] } = useQuery({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: () => contabilidadService.getPlanCuentas(),
  });

  const anioNumFiltro = filtroAnio.trim() ? Number.parseInt(filtroAnio.trim(), 10) : undefined;
  const { data: periodos = [], isLoading: loadingPeriodos } = useQuery({
    queryKey: contabilidadKeys.periodos(Number.isFinite(anioNumFiltro) ? anioNumFiltro : null),
    queryFn: () =>
      contabilidadService.getPeriodosContables(Number.isFinite(anioNumFiltro) ? anioNumFiltro : undefined),
  });

  const cuentasPatrimonio = useMemo(
    () => cuentas.filter((c) => c.tipo_cuenta === 'PATRIMONIO' && c.activo),
    [cuentas],
  );

  // ── Form Diarios ─────────────────────────────────────────────────────────
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DiarioContableInput>({
    resolver: zodResolver(diarioContableSchema),
    defaultValues: {
      codigo: '',
      nombre: '',
      tipo: 'VARIOS',
      prefijo_secuencia: '',
      siguiente_numero: '1',
      cuenta_defecto_debe: '',
      cuenta_defecto_haber: '',
    },
  });

  const abrirCrearDiario = () => {
    setEditandoDiario(null);
    reset({
      codigo: '',
      nombre: '',
      tipo: 'VARIOS',
      prefijo_secuencia: '',
      siguiente_numero: '1',
      cuenta_defecto_debe: '',
      cuenta_defecto_haber: '',
    });
    setDiarioError('');
    setDiarioDialogOpen(true);
  };

  const abrirEditarDiario = (d: DiarioContable) => {
    setEditandoDiario(d);
    reset({
      codigo: d.codigo,
      nombre: d.nombre,
      tipo: d.tipo,
      prefijo_secuencia: d.prefijo_secuencia || '',
      siguiente_numero: String(d.siguiente_numero ?? 1),
      cuenta_defecto_debe: d.cuenta_defecto_debe || '',
      cuenta_defecto_haber: d.cuenta_defecto_haber || '',
    });
    setDiarioError('');
    setDiarioDialogOpen(true);
  };

  const guardarDiarioMutation = useMutation({
    mutationFn: (input: DiarioContableInput) => {
      const sigNum = input.siguiente_numero?.trim() ? Number.parseInt(input.siguiente_numero.trim(), 10) : 1;
      const body = {
        codigo: input.codigo.trim(),
        nombre: input.nombre.trim(),
        tipo: input.tipo,
        prefijo_secuencia: (input.prefijo_secuencia ?? '').trim(),
        siguiente_numero: Number.isFinite(sigNum) && sigNum >= 1 ? sigNum : 1,
        cuenta_defecto_debe: input.cuenta_defecto_debe || null,
        cuenta_defecto_haber: input.cuenta_defecto_haber || null,
      };
      if (editandoDiario) {
        return contabilidadService.actualizarDiario(editandoDiario.id_diario, body);
      }
      return contabilidadService.crearDiario({ id_empresa: empresaId, ...body });
    },
    onSuccess: () => {
      feedback?.snackbar.success(t('contabilidad.diarios.guardado'));
      setBannerInfo(t('contabilidad.diarios.guardado'));
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.diariosAll() });
      setDiarioDialogOpen(false);
    },
    onError: (err: unknown) => {
      setDiarioError(mensajeDeError(err, t('contabilidad.diarios.errorGuardar')));
    },
  });

  // ── Mutations Períodos / Cierre ──────────────────────────────────────────
  const cerrarPeriodoMutation = useMutation({
    mutationFn: () =>
      contabilidadService.cerrarPeriodo({
        id_empresa: empresaId,
        anio: Number.parseInt(cerrarAnio, 10),
        mes: Number.parseInt(cerrarMes, 10),
        observaciones: cerrarObs.trim(),
      }),
    onSuccess: () => {
      feedback?.snackbar.success(t('contabilidad.periodos.periodoCerradoOk'));
      setBannerInfo(t('contabilidad.periodos.periodoCerradoOk'));
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.periodosAll() });
      setCerrarPeriodoOpen(false);
      setCerrarObs('');
    },
    onError: (err: unknown) => {
      setPeriodoError(mensajeDeError(err, t('contabilidad.periodos.errorCerrarPeriodo')));
    },
  });

  const reabrirMutation = useMutation({
    mutationFn: () =>
      contabilidadService.reabrirPeriodo(reabrirTarget?.id_periodo ?? '', reabrirMotivo.trim()),
    onSuccess: () => {
      feedback?.snackbar.success(t('contabilidad.periodos.periodoReabiertoOk'));
      setBannerInfo(t('contabilidad.periodos.periodoReabiertoOk'));
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.periodosAll() });
      setReabrirTarget(null);
      setReabrirMotivo('');
    },
    onError: (err: unknown) => {
      setReabrirError(mensajeDeError(err, t('contabilidad.periodos.errorReabrir')));
    },
  });

  const cerrarEjercicioMutation = useMutation({
    mutationFn: () =>
      contabilidadService.cerrarEjercicio({
        id_empresa: empresaId,
        anio: Number.parseInt(ejercicioAnio, 10),
        cuenta_resultado_acumulado: cuentaPatrimonioId,
        fecha_cierre: fechaCierreEjercicio || null,
      }),
    onSuccess: (res) => {
      const msg = t('contabilidad.periodos.ejercicioCerradoOk', {
        anio: res.anio,
        resultado: res.resultado_ejercicio,
      });
      feedback?.snackbar.success(msg);
      setBannerInfo(msg);
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.periodosAll() });
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.asientosAll() });
      setCierreEjercicioOpen(false);
    },
    onError: (err: unknown) => {
      setEjercicioError(mensajeDeError(err, t('contabilidad.periodos.errorCerrarEjercicio')));
    },
  });

  // ── Columnas Diarios ─────────────────────────────────────────────────────
  const diarioColumns: Column<DiarioContable>[] = [
    {
      key: 'codigo',
      header: t('contabilidad.diarios.codigo'),
      render: (d) => (
        <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
          {d.codigo}
        </Typography>
      ),
    },
    { key: 'nombre', header: t('contabilidad.diarios.nombre'), render: (d) => d.nombre },
    { key: 'tipo', header: t('contabilidad.diarios.tipo'), render: (d) => d.tipo_display || d.tipo },
    {
      key: 'secuencia',
      header: t('contabilidad.diarios.secuencia'),
      render: (d) =>
        d.prefijo_secuencia
          ? `${d.prefijo_secuencia}-${String(d.siguiente_numero ?? 1).padStart(6, '0')}`
          : '—',
    },
    {
      key: 'debe',
      header: t('contabilidad.diarios.cuentaDebe'),
      render: (d) => d.cuenta_defecto_debe_nombre || '—',
    },
    {
      key: 'haber',
      header: t('contabilidad.diarios.cuentaHaber'),
      render: (d) => d.cuenta_defecto_haber_nombre || '—',
    },
    {
      key: 'activo',
      header: t('contabilidad.diarios.activo'),
      render: (d) => <StatusChip value={d.activo} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      render: (d) => (
        <Button size="small" onClick={() => abrirEditarDiario(d)}>
          {t('common.edit')}
        </Button>
      ),
    },
  ];

  // ── Columnas Períodos ────────────────────────────────────────────────────
  const periodoColumns: Column<PeriodoContable>[] = [
    {
      key: 'periodo',
      header: t('contabilidad.periodos.periodo'),
      render: (p) => (
        <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
          {`${p.anio}-${String(p.mes).padStart(2, '0')}`}
        </Typography>
      ),
    },
    {
      key: 'estado',
      header: t('contabilidad.periodos.estado'),
      render: (p) => (
        <StatusChip
          value={p.estado}
          colorMap={{ abierto: 'success', cerrado: 'default' }}
          label={p.estado_display || p.estado}
        />
      ),
    },
    {
      key: 'fecha_cierre',
      header: t('contabilidad.periodos.fechaCierre'),
      render: (p) => (p.fecha_cierre ? p.fecha_cierre.slice(0, 10) : '—'),
    },
    {
      key: 'asiento_cierre',
      header: t('contabilidad.periodos.asientoCierre'),
      render: (p) =>
        p.asiento_cierre ? (
          <Button
            size="small"
            onClick={() => navigate(`/contabilidad/asientos/${p.asiento_cierre}`)}
          >
            {p.asiento_cierre_numero || p.asiento_cierre.slice(0, 8)}
          </Button>
        ) : (
          '—'
        ),
    },
    {
      key: 'observaciones',
      header: t('contabilidad.periodos.observaciones'),
      render: (p) => p.observaciones || '—',
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      render: (p) =>
        p.estado === 'CERRADO' ? (
          <Button
            size="small"
            startIcon={<LockOpenOutlined />}
            disabled={Boolean(p.asiento_cierre)}
            onClick={() => {
              setReabrirTarget(p);
              setReabrirMotivo('');
              setReabrirError('');
            }}
          >
            {t('contabilidad.periodos.reabrir')}
          </Button>
        ) : null,
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('contabilidad.diarios.title')}
        subtitle={t('contabilidad.diarios.subtitle')}
        actions={
          tab === 'diarios' ? (
            <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrearDiario}>
              {t('contabilidad.diarios.nuevo')}
            </Button>
          ) : (
            <Stack direction="row" spacing={1}>
              <Button
                variant="outlined"
                startIcon={<LockOutlined />}
                onClick={() => {
                  setPeriodoError('');
                  setCerrarPeriodoOpen(true);
                }}
              >
                {t('contabilidad.periodos.cerrarPeriodo')}
              </Button>
              <Button
                variant="contained"
                color="warning"
                startIcon={<EventAvailableOutlined />}
                onClick={() => {
                  setEjercicioError('');
                  if (!cuentaPatrimonioId && cuentasPatrimonio.length > 0) {
                    setCuentaPatrimonioId(cuentasPatrimonio[0].id_cuenta_contable);
                  }
                  setCierreEjercicioOpen(true);
                }}
              >
                {t('contabilidad.periodos.cerrarEjercicio')}
              </Button>
            </Stack>
          )
        }
      />

      {bannerInfo && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setBannerInfo('')}>
          {bannerInfo}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tab} onChange={(_, v: 'diarios' | 'periodos') => setTab(v)}>
          <Tab value="diarios" label={t('contabilidad.diarios.tabDiarios')} />
          <Tab value="periodos" label={t('contabilidad.diarios.tabPeriodos')} />
        </Tabs>
      </Box>

      {tab === 'diarios' ? (
        <>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <TextField
              select
              size="small"
              label={t('contabilidad.diarios.tipo')}
              value={filtroTipo}
              onChange={(e) => setFiltroTipo(e.target.value)}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="">{t('contabilidad.diarios.todos')}</MenuItem>
              {TIPOS_DIARIO.map((tp) => (
                <MenuItem key={tp} value={tp}>
                  {tp}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <DataTable
            columns={diarioColumns}
            rows={diarios}
            getRowKey={(d) => d.id_diario}
            loading={loadingDiarios}
            emptyMessage={t('contabilidad.diarios.empty')}
          />
        </>
      ) : (
        <>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <TextField
              size="small"
              type="number"
              label={t('contabilidad.periodos.anio')}
              value={filtroAnio}
              onChange={(e) => setFiltroAnio(e.target.value)}
              sx={{ width: 160 }}
            />
          </Stack>
          <DataTable
            columns={periodoColumns}
            rows={periodos}
            getRowKey={(p) => p.id_periodo}
            loading={loadingPeriodos}
            emptyMessage={t('contabilidad.periodos.empty')}
          />
        </>
      )}

      {/* Modal Crear / Editar Diario */}
      <Dialog open={diarioDialogOpen} onClose={() => setDiarioDialogOpen(false)} fullWidth maxWidth="sm">
        <form
          onSubmit={handleSubmit((input) => {
            setDiarioError('');
            guardarDiarioMutation.mutate(input);
          })}
          noValidate
        >
          <DialogTitle>
            {editandoDiario ? t('contabilidad.diarios.editar') : t('contabilidad.diarios.nuevo')}
          </DialogTitle>
          <DialogContent>
            {diarioError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {diarioError}
              </Alert>
            )}
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                label={t('contabilidad.diarios.codigo')}
                fullWidth
                required
                error={!!errors.codigo}
                helperText={errors.codigo?.message}
                {...register('codigo')}
              />
              <TextField
                label={t('contabilidad.diarios.nombre')}
                fullWidth
                required
                error={!!errors.nombre}
                helperText={errors.nombre?.message}
                {...register('nombre')}
              />
              <Controller
                name="tipo"
                control={control}
                render={({ field }) => (
                  <TextField
                    select
                    label={t('contabilidad.diarios.tipo')}
                    fullWidth
                    required
                    value={field.value ?? 'VARIOS'}
                    onChange={field.onChange}
                    error={!!errors.tipo}
                    helperText={errors.tipo?.message}
                  >
                    {TIPOS_DIARIO.map((tp) => (
                      <MenuItem key={tp} value={tp}>
                        {tp}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label={t('contabilidad.diarios.prefijo')}
                  fullWidth
                  placeholder="FAC"
                  error={!!errors.prefijo_secuencia}
                  helperText={errors.prefijo_secuencia?.message}
                  {...register('prefijo_secuencia')}
                />
                <TextField
                  label={t('contabilidad.diarios.siguienteNumero')}
                  type="number"
                  fullWidth
                  error={!!errors.siguiente_numero}
                  helperText={errors.siguiente_numero?.message}
                  {...register('siguiente_numero')}
                />
              </Stack>
              <Controller
                name="cuenta_defecto_debe"
                control={control}
                render={({ field }) => (
                  <TextField
                    select
                    label={t('contabilidad.diarios.cuentaDebe')}
                    fullWidth
                    value={field.value ?? ''}
                    onChange={field.onChange}
                  >
                    <MenuItem value="">{t('contabilidad.diarios.sinCuenta')}</MenuItem>
                    {cuentas.map((c) => (
                      <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                        {c.codigo_cuenta} — {c.nombre_cuenta}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
              <Controller
                name="cuenta_defecto_haber"
                control={control}
                render={({ field }) => (
                  <TextField
                    select
                    label={t('contabilidad.diarios.cuentaHaber')}
                    fullWidth
                    value={field.value ?? ''}
                    onChange={field.onChange}
                  >
                    <MenuItem value="">{t('contabilidad.diarios.sinCuenta')}</MenuItem>
                    {cuentas.map((c) => (
                      <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                        {c.codigo_cuenta} — {c.nombre_cuenta}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDiarioDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" variant="contained" disabled={guardarDiarioMutation.isPending}>
              {t('common.save')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Modal Cerrar Período Mensual */}
      <Dialog open={cerrarPeriodoOpen} onClose={() => setCerrarPeriodoOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('contabilidad.periodos.cerrarPeriodoTitulo')}</DialogTitle>
        <DialogContent>
          {periodoError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {periodoError}
            </Alert>
          )}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('contabilidad.periodos.anio')}
              type="number"
              fullWidth
              value={cerrarAnio}
              onChange={(e) => setCerrarAnio(e.target.value)}
            />
            <TextField
              select
              label={t('contabilidad.periodos.mes')}
              fullWidth
              value={cerrarMes}
              onChange={(e) => setCerrarMes(e.target.value)}
            >
              {MESES.map((m) => (
                <MenuItem key={m} value={String(m)}>
                  {String(m).padStart(2, '0')}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('contabilidad.periodos.observaciones')}
              fullWidth
              multiline
              rows={2}
              value={cerrarObs}
              onChange={(e) => setCerrarObs(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCerrarPeriodoOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={cerrarPeriodoMutation.isPending}
            onClick={() => {
              setPeriodoError('');
              cerrarPeriodoMutation.mutate();
            }}
          >
            {t('contabilidad.periodos.cerrarPeriodo')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Modal Reabrir Período */}
      <Dialog open={!!reabrirTarget} onClose={() => setReabrirTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('contabilidad.periodos.reabrirTitulo')}</DialogTitle>
        <DialogContent>
          {reabrirError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {reabrirError}
            </Alert>
          )}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              {reabrirTarget ? `${reabrirTarget.anio}-${String(reabrirTarget.mes).padStart(2, '0')}` : ''}
            </Typography>
            <TextField
              label={t('contabilidad.periodos.motivoReapertura')}
              fullWidth
              value={reabrirMotivo}
              onChange={(e) => setReabrirMotivo(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReabrirTarget(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={reabrirMutation.isPending}
            onClick={() => {
              setReabrirError('');
              reabrirMutation.mutate();
            }}
          >
            {t('contabilidad.periodos.reabrir')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Modal Cerrar Ejercicio Anual */}
      <Dialog open={cierreEjercicioOpen} onClose={() => setCierreEjercicioOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('contabilidad.periodos.cerrarEjercicioTitulo')}</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('contabilidad.periodos.cerrarEjercicioInfo')}
          </Alert>
          {cuentasPatrimonio.length === 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t('contabilidad.periodos.sinPatrimonio')}
            </Alert>
          )}
          {ejercicioError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {ejercicioError}
            </Alert>
          )}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('contabilidad.periodos.anio')}
              type="number"
              fullWidth
              value={ejercicioAnio}
              onChange={(e) => setEjercicioAnio(e.target.value)}
            />
            <TextField
              select
              label={t('contabilidad.periodos.cuentaResultado')}
              fullWidth
              value={cuentaPatrimonioId}
              onChange={(e) => setCuentaPatrimonioId(e.target.value)}
            >
              {cuentasPatrimonio.map((c) => (
                <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                  {c.codigo_cuenta} — {c.nombre_cuenta}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('contabilidad.periodos.fechaCierreEjercicio')}
              type="date"
              fullWidth
              InputLabelProps={{ shrink: true }}
              value={fechaCierreEjercicio}
              onChange={(e) => setFechaCierreEjercicio(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCierreEjercicioOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={cerrarEjercicioMutation.isPending || !cuentaPatrimonioId}
            onClick={() => {
              setEjercicioError('');
              cerrarEjercicioMutation.mutate();
            }}
          >
            {t('contabilidad.periodos.cerrarEjercicio')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
}
