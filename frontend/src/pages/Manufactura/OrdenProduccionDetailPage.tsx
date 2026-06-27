/**
 * Detalle de Orden de Producción (1.I): stepper con la secuencia de etapas
 * (corte → ensamble → lijado → pintura → tapizado → control final), avance de
 * etapa con horas/tarifa/destajo (transición auditada en backend) y cierre de
 * la OF (entrada de PT al costo real; el backend devuelve 400 si quedan etapas
 * pendientes — ese error se muestra en la UI sin romper el flujo).
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import { manufacturaService } from '../../services/manufacturaService';
import type { EtapaOrdenProduccion } from '../../services/manufacturaService';
import { almacenesService } from '../../services/almacenesService';
import {
  avanzarEtapaSchema,
  completarOrdenSchema,
  consumirMaterialesSchema,
  type AvanzarEtapaInput,
  type CompletarOrdenInput,
  type ConsumirMaterialesInput,
} from '../../schemas/manufactura.schemas';
import { manufacturaKeys, almacenesKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { toFixedStr } from '../../lib/decimal';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';

export default function OrdenProduccionDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const [dialogoAvanzar, setDialogoAvanzar] = useState(false);
  const [dialogoCompletar, setDialogoCompletar] = useState(false);
  const [dialogoConsumir, setDialogoConsumir] = useState(false);
  const [errorAvanzar, setErrorAvanzar] = useState('');
  const [errorCompletar, setErrorCompletar] = useState('');
  const [errorConsumir, setErrorConsumir] = useState('');

  const { data: orden, isLoading: cargandoOrden } = useQuery({
    queryKey: manufacturaKeys.orden(id),
    queryFn: () => manufacturaService.getOrden(id),
    enabled: !!id,
  });

  const { data: etapas = [], isLoading: cargandoEtapas } = useQuery({
    queryKey: manufacturaKeys.etapas(id),
    queryFn: () => manufacturaService.getEtapas(id),
    enabled: !!id,
  });

  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
    enabled: dialogoCompletar || dialogoConsumir,
  });

  const formAvanzar = useForm<AvanzarEtapaInput>({
    resolver: zodResolver(avanzarEtapaSchema),
    defaultValues: { horas_trabajadas: '', tarifa_hora: '', cantidad_destajo: '', observaciones: '' },
  });

  const formCompletar = useForm<CompletarOrdenInput>({
    resolver: zodResolver(completarOrdenSchema),
    defaultValues: { almacen_id: '', cantidad: '' },
  });

  const formConsumir = useForm<ConsumirMaterialesInput>({
    resolver: zodResolver(consumirMaterialesSchema),
    defaultValues: { almacen_id: '' },
  });

  const invalidarOrden = () => {
    // El avance/cierre cambia etapas, estado de la OF y el costeo a la vez.
    void queryClient.invalidateQueries({ queryKey: manufacturaKeys.ordenesAll() });
  };

  const avanzarMutation = useMutation({
    mutationFn: (input: AvanzarEtapaInput) =>
      manufacturaService.avanzarEtapa(id, {
        horas_trabajadas: input.horas_trabajadas || '0',
        tarifa_hora: input.tarifa_hora || '0',
        cantidad_destajo: input.cantidad_destajo || '0',
        observaciones: input.observaciones || '',
      }),
    onSuccess: () => {
      snackbar.success(t('manufactura.detalle.etapaCompletada'));
      cerrarAvanzar();
      invalidarOrden();
    },
    onError: (err: unknown) => {
      // 400 del backend: doble avance concurrente / sin etapas pendientes / OF cerrada.
      setErrorAvanzar(mensajeDeError(err, t('manufactura.detalle.errorAvanzar')));
    },
  });

  const consumirMutation = useMutation({
    mutationFn: (input: ConsumirMaterialesInput) =>
      manufacturaService.consumirMateriales(id, { almacen_id: input.almacen_id }),
    onSuccess: (res) => {
      snackbar.success(t('manufactura.detalle.consumoOk', { monto: toFixedStr(res.costo_materiales) }));
      cerrarConsumir();
      invalidarOrden();
    },
    onError: (err: unknown) => {
      // 400 del backend: sin BOM, stock insuficiente o OF cerrada.
      setErrorConsumir(mensajeDeError(err, t('manufactura.detalle.errorConsumo')));
    },
  });

  const completarMutation = useMutation({
    mutationFn: (input: CompletarOrdenInput) =>
      manufacturaService.completarOrden(id, {
        almacen_id: input.almacen_id,
        ...(input.cantidad ? { cantidad: input.cantidad } : {}),
      }),
    onSuccess: () => {
      snackbar.success(t('manufactura.detalle.ordenCompletada'));
      cerrarCompletar();
      invalidarOrden();
    },
    onError: (err: unknown) => {
      // 400 "no se puede cerrar la OF con etapas pendientes" visible en el diálogo.
      setErrorCompletar(mensajeDeError(err, t('manufactura.detalle.errorCompletar')));
    },
  });

  function abrirAvanzar() {
    setErrorAvanzar('');
    formAvanzar.reset({ horas_trabajadas: '', tarifa_hora: '', cantidad_destajo: '', observaciones: '' });
    setDialogoAvanzar(true);
  }

  function cerrarAvanzar() {
    setDialogoAvanzar(false);
    setErrorAvanzar('');
  }

  function abrirCompletar() {
    setErrorCompletar('');
    formCompletar.reset({ almacen_id: '', cantidad: '' });
    setDialogoCompletar(true);
  }

  function cerrarCompletar() {
    setDialogoCompletar(false);
    setErrorCompletar('');
  }

  function abrirConsumir() {
    setErrorConsumir('');
    formConsumir.reset({ almacen_id: '' });
    setDialogoConsumir(true);
  }

  function cerrarConsumir() {
    setDialogoConsumir(false);
    setErrorConsumir('');
  }

  if (cargandoOrden || cargandoEtapas) {
    return (
      <PageContainer>
        <Stack alignItems="center" sx={{ py: 8 }}>
          <CircularProgress />
        </Stack>
      </PageContainer>
    );
  }

  const pendientes = etapas.filter((e) => e.estado === 'pendiente');
  const siguiente = pendientes[0];
  const activeStep = etapas.findIndex((e) => e.estado === 'pendiente');
  const ordenCerrada = orden?.estado === 'finalizada' || orden?.estado === 'cancelada';
  const titulo = orden?.referencia_externa || `OF-${id.slice(0, 8)}`;

  return (
    <PageContainer>
      <PageHeader
        title={`${t('manufactura.detalle.title')} ${titulo}`}
        subtitle={orden ? `${t('manufactura.ordenes.cantidad')}: ${orden.cantidad}` : undefined}
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate(`/manufactura/ordenes/${id}/costeo`)}>
              {t('manufactura.detalle.verCosteo')}
            </Button>
            <Button variant="outlined" onClick={() => navigate(`/manufactura/ordenes/${id}/mrp`)}>
              {t('manufactura.detalle.verMrp')}
            </Button>
            <Button
              variant="outlined"
              onClick={abrirConsumir}
              disabled={!orden?.lista_materiales || ordenCerrada}
            >
              {t('manufactura.detalle.consumirMateriales')}
            </Button>
            <Button
              variant="contained"
              onClick={abrirAvanzar}
              disabled={!siguiente || ordenCerrada}
            >
              {t('manufactura.detalle.avanzarEtapa')}
            </Button>
            <Button
              variant="contained"
              color="success"
              onClick={abrirCompletar}
              disabled={ordenCerrada}
            >
              {t('manufactura.detalle.completarOrden')}
            </Button>
          </>
        }
      />

      {orden && (
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('manufactura.ordenes.estado')}:
          </Typography>
          <StatusChip value={orden.estado} />
        </Stack>
      )}

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('manufactura.detalle.etapas')}
        </Typography>
        {etapas.length === 0 ? (
          <Alert severity="info">{t('manufactura.detalle.sinEtapas')}</Alert>
        ) : (
          <Stepper orientation="vertical" activeStep={activeStep === -1 ? etapas.length : activeStep}>
            {etapas.map((etapa: EtapaOrdenProduccion) => (
              <Step key={etapa.id} completed={etapa.estado === 'completada'}>
                <StepLabel
                  optional={
                    <StatusChip
                      value={etapa.estado}
                      label={
                        etapa.estado === 'completada'
                          ? t('manufactura.detalle.completada')
                          : t('manufactura.detalle.pendiente')
                      }
                    />
                  }
                >
                  {etapa.orden}. {etapa.etapa_nombre}
                </StepLabel>
                {/* Detalle siempre visible (StepContent solo muestra el paso activo) */}
                <Box sx={{ pl: 4 }}>
                  {etapa.estado === 'completada' && (
                    <Stack spacing={0.5}>
                      <Typography variant="body2" color="text.secondary">
                        {t('manufactura.detalle.horas')}: {etapa.horas_trabajadas} ·{' '}
                        {t('manufactura.detalle.manoObra')}: {toFixedStr(etapa.costo_mano_obra)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {t('manufactura.detalle.pagoDestajo')}: {toFixedStr(etapa.pago_destajo)}
                      </Typography>
                      {etapa.fecha_completada && (
                        <Typography variant="caption" color="text.secondary">
                          {t('manufactura.detalle.completadaEl')}:{' '}
                          {new Date(etapa.fecha_completada).toLocaleString()}
                        </Typography>
                      )}
                      {etapa.observaciones && (
                        <Typography variant="caption" color="text.secondary">
                          {etapa.observaciones}
                        </Typography>
                      )}
                    </Stack>
                  )}
                </Box>
              </Step>
            ))}
          </Stepper>
        )}
      </Paper>

      {/* ── Diálogo: avanzar etapa ─────────────────────────────────────────── */}
      <Dialog open={dialogoAvanzar} onClose={cerrarAvanzar} fullWidth maxWidth="sm">
        <DialogTitle>
          {t('manufactura.detalle.avanzarEtapa')}
          {siguiente ? ` — ${siguiente.etapa_nombre}` : ''}
        </DialogTitle>
        <form
          onSubmit={formAvanzar.handleSubmit((input) => {
            setErrorAvanzar('');
            avanzarMutation.mutate(input);
          })}
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorAvanzar && <Alert severity="error">{errorAvanzar}</Alert>}
              <TextField
                label={t('manufactura.detalle.horas')}
                {...formAvanzar.register('horas_trabajadas')}
                error={!!formAvanzar.formState.errors.horas_trabajadas}
                helperText={formAvanzar.formState.errors.horas_trabajadas?.message}
                fullWidth
              />
              <TextField
                label={t('manufactura.detalle.tarifaHora')}
                {...formAvanzar.register('tarifa_hora')}
                error={!!formAvanzar.formState.errors.tarifa_hora}
                helperText={formAvanzar.formState.errors.tarifa_hora?.message}
                fullWidth
              />
              <TextField
                label={t('manufactura.detalle.cantidadDestajo')}
                {...formAvanzar.register('cantidad_destajo')}
                error={!!formAvanzar.formState.errors.cantidad_destajo}
                helperText={formAvanzar.formState.errors.cantidad_destajo?.message}
                fullWidth
              />
              <TextField
                label={t('manufactura.detalle.observaciones')}
                {...formAvanzar.register('observaciones')}
                error={!!formAvanzar.formState.errors.observaciones}
                helperText={formAvanzar.formState.errors.observaciones?.message}
                multiline
                rows={2}
                fullWidth
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarAvanzar}>{t('common.cancel')}</Button>
            <Button type="submit" variant="contained" disabled={avanzarMutation.isPending}>
              {t('manufactura.comun.confirmar')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* ── Diálogo: completar OF ──────────────────────────────────────────── */}
      <Dialog open={dialogoCompletar} onClose={cerrarCompletar} fullWidth maxWidth="sm">
        <DialogTitle>{t('manufactura.detalle.completarOrden')}</DialogTitle>
        <form
          onSubmit={formCompletar.handleSubmit((input) => {
            setErrorCompletar('');
            completarMutation.mutate(input);
          })}
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorCompletar && <Alert severity="error">{errorCompletar}</Alert>}
              <TextField
                select
                label={t('manufactura.detalle.almacen')}
                defaultValue=""
                {...formCompletar.register('almacen_id')}
                error={!!formCompletar.formState.errors.almacen_id}
                helperText={formCompletar.formState.errors.almacen_id?.message}
                fullWidth
              >
                {almacenes.map((a) => (
                  <MenuItem key={a.id_almacen} value={a.id_almacen}>
                    {a.nombre_almacen}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label={t('manufactura.detalle.cantidadProducida')}
                {...formCompletar.register('cantidad')}
                error={!!formCompletar.formState.errors.cantidad}
                helperText={formCompletar.formState.errors.cantidad?.message}
                fullWidth
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarCompletar}>{t('common.cancel')}</Button>
            <Button type="submit" variant="contained" color="success" disabled={completarMutation.isPending}>
              {t('manufactura.comun.confirmar')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* ── Diálogo: consumir materiales ───────────────────────────────────── */}
      <Dialog open={dialogoConsumir} onClose={cerrarConsumir} fullWidth maxWidth="sm">
        <DialogTitle>{t('manufactura.detalle.consumirMateriales')}</DialogTitle>
        <form
          onSubmit={formConsumir.handleSubmit((input) => {
            setErrorConsumir('');
            consumirMutation.mutate(input);
          })}
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorConsumir && <Alert severity="error">{errorConsumir}</Alert>}
              <TextField
                select
                label={t('manufactura.detalle.almacen')}
                defaultValue=""
                {...formConsumir.register('almacen_id')}
                error={!!formConsumir.formState.errors.almacen_id}
                helperText={formConsumir.formState.errors.almacen_id?.message}
                fullWidth
              >
                {almacenes.map((a) => (
                  <MenuItem key={a.id_almacen} value={a.id_almacen}>
                    {a.nombre_almacen}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarConsumir}>{t('common.cancel')}</Button>
            <Button type="submit" variant="contained" disabled={consumirMutation.isPending}>
              {t('manufactura.detalle.confirmarConsumo')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
