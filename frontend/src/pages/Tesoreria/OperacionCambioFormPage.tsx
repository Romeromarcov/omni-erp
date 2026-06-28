/**
 * Formulario de operación de cambio de divisa (workstream F).
 *
 * Usa el flujo transaccional del PR #82: el backend registra el doble registro
 * financiero + comisión + asiento CAMBIO_DIVISA en UNA transacción. Si la
 * contabilidad está activa SIN mapeo CAMBIO_DIVISA responde 422 y nada queda
 * registrado — aquí ese 422 se muestra con un link directo a la pantalla de
 * mapeos contables para destrancarlo.
 *
 * monto_destino = monto_origen × tasa con decimal.js (R-CODE-4): cero float.
 */
import { useState } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { tesoreriaService } from '../../services/tesoreriaService';
import { fetchMonedasEmpresaActivas } from '../../services/monedasEmpresaActiva';
import { fetchMetodosPagoEmpresaActivos } from '../../services/metodosPagoEmpresaActiva';
import { operacionCambioSchema, type OperacionCambioInput } from '../../schemas/tesoreria.schemas';
import { tesoreriaKeys, finanzasKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { D, toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader } from '../../components/ui';

const hoy = () => new Date().toISOString().slice(0, 10);

/** Heurística del 422 R-CODE-11: contabilidad activa sin mapeo CAMBIO_DIVISA. */
function esErrorMapeo(mensaje: string): boolean {
  return /mapeo/i.test(mensaje);
}

export default function OperacionCambioFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const empresaId = getEmpresaId() || '';
  const [errorGeneral, setErrorGeneral] = useState('');
  const [faltaMapeo, setFaltaMapeo] = useState(false);

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.empresaActivas(empresaId),
    queryFn: () => fetchMonedasEmpresaActivas(empresaId),
    enabled: !!empresaId,
  });

  const { data: metodosPago = [] } = useQuery({
    queryKey: finanzasKeys.metodosPagoEmpresaActivas(empresaId),
    queryFn: () => fetchMetodosPagoEmpresaActivos(empresaId),
    enabled: !!empresaId,
  });

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<OperacionCambioInput>({
    resolver: zodResolver(operacionCambioSchema),
    defaultValues: {
      numero_operacion: '',
      fecha_operacion: hoy(),
      tipo_operacion: 'COMPRA',
      moneda_origen: '',
      moneda_destino: '',
      monto_origen: '',
      tasa_cambio: '',
      comision: '',
      metodo_pago_origen: '',
      metodo_pago_destino: '',
      referencia_transaccion_origen: '',
      referencia_transaccion_destino: '',
      observaciones: '',
    },
  });

  const montoOrigenWatch = watch('monto_origen');
  const tasaWatch = watch('tasa_cambio');
  // monto_destino con decimal.js — nunca `Number(monto) * Number(tasa)`.
  const montoDestino = D(montoOrigenWatch).times(D(tasaWatch));

  const crearMutation = useMutation({
    mutationFn: (input: OperacionCambioInput) =>
      tesoreriaService.crearOperacionCambio({
        empresa: empresaId,
        numero_operacion: input.numero_operacion,
        // El backend espera DateTime; la fecha del día se envía a medianoche local.
        fecha_operacion: `${input.fecha_operacion}T00:00:00`,
        tipo_operacion: input.tipo_operacion,
        moneda_origen: input.moneda_origen,
        moneda_destino: input.moneda_destino,
        monto_origen: input.monto_origen,
        tasa_cambio: input.tasa_cambio,
        monto_destino: montoDestino.toFixed(4),
        comision: input.comision || '0',
        metodo_pago_origen: input.metodo_pago_origen,
        metodo_pago_destino: input.metodo_pago_destino,
        referencia_transaccion_origen: input.referencia_transaccion_origen || '',
        referencia_transaccion_destino: input.referencia_transaccion_destino || '',
        observaciones: input.observaciones || '',
      }),
    onSuccess: () => {
      snackbar.success(t('tesoreria.cambioDivisa.creada'));
      void queryClient.invalidateQueries({ queryKey: tesoreriaKeys.operacionesCambioAll() });
      navigate('/tesoreria/cambio-divisa');
    },
    onError: (err: unknown) => {
      const mensaje = mensajeDeError(err, t('tesoreria.cambioDivisa.errorCrear'));
      setFaltaMapeo(esErrorMapeo(mensaje));
      setErrorGeneral(mensaje);
    },
  });

  return (
    <PageContainer>
      <PageHeader title={t('tesoreria.cambioDivisa.formTitle')} subtitle={t('tesoreria.cambioDivisa.formSubtitle')} />
      <form
        onSubmit={handleSubmit((input) => {
          setErrorGeneral('');
          setFaltaMapeo(false);
          crearMutation.mutate(input);
        })}
        noValidate
      >
        <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
          {errorGeneral && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorGeneral}
              {faltaMapeo && (
                <>
                  {' '}
                  <Link component={RouterLink} to="/contabilidad/mapeos">
                    {t('tesoreria.cambioDivisa.irAMapeos')}
                  </Link>
                </>
              )}
            </Alert>
          )}
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('tesoreria.cambioDivisa.numero')}
                fullWidth
                required
                error={!!errors.numero_operacion}
                helperText={errors.numero_operacion?.message}
                {...register('numero_operacion')}
              />
              <TextField
                label={t('tesoreria.cambioDivisa.fecha')}
                type="date"
                fullWidth
                required
                InputLabelProps={{ shrink: true }}
                error={!!errors.fecha_operacion}
                helperText={errors.fecha_operacion?.message}
                {...register('fecha_operacion')}
              />
              <TextField
                select
                label={t('tesoreria.cambioDivisa.tipo')}
                fullWidth
                required
                defaultValue="COMPRA"
                error={!!errors.tipo_operacion}
                helperText={errors.tipo_operacion?.message}
                {...register('tipo_operacion')}
              >
                <MenuItem value="COMPRA">{t('tesoreria.cambioDivisa.compra')}</MenuItem>
                <MenuItem value="VENTA">{t('tesoreria.cambioDivisa.venta')}</MenuItem>
              </TextField>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                select
                label={t('tesoreria.cambioDivisa.monedaOrigen')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.moneda_origen}
                helperText={errors.moneda_origen?.message}
                {...register('moneda_origen')}
              >
                {monedas.map((m) => (
                  <MenuItem key={m.moneda} value={m.moneda}>
                    {m.moneda_codigo_iso} — {m.moneda_nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label={t('tesoreria.cambioDivisa.monedaDestino')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.moneda_destino}
                helperText={errors.moneda_destino?.message}
                {...register('moneda_destino')}
              >
                {monedas.map((m) => (
                  <MenuItem key={m.moneda} value={m.moneda}>
                    {m.moneda_codigo_iso} — {m.moneda_nombre}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('tesoreria.cambioDivisa.montoOrigen')}
                fullWidth
                required
                inputProps={{ inputMode: 'decimal' }}
                error={!!errors.monto_origen}
                helperText={errors.monto_origen?.message}
                {...register('monto_origen')}
              />
              <TextField
                label={t('tesoreria.cambioDivisa.tasa')}
                fullWidth
                required
                inputProps={{ inputMode: 'decimal' }}
                error={!!errors.tasa_cambio}
                helperText={errors.tasa_cambio?.message}
                {...register('tasa_cambio')}
              />
              <TextField
                label={t('tesoreria.cambioDivisa.comision')}
                fullWidth
                inputProps={{ inputMode: 'decimal' }}
                error={!!errors.comision}
                helperText={errors.comision?.message}
                {...register('comision')}
              />
            </Stack>
            <Typography variant="body1" fontWeight={600}>
              {t('tesoreria.cambioDivisa.montoDestinoCalc')}: {toFixedStr(montoDestino, 4)}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                select
                label={t('tesoreria.cambioDivisa.metodoPagoOrigen')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.metodo_pago_origen}
                helperText={errors.metodo_pago_origen?.message}
                {...register('metodo_pago_origen')}
              >
                {metodosPago.map((mp) => (
                  <MenuItem key={mp.id} value={mp.metodo_pago}>
                    {mp.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label={t('tesoreria.cambioDivisa.metodoPagoDestino')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.metodo_pago_destino}
                helperText={errors.metodo_pago_destino?.message}
                {...register('metodo_pago_destino')}
              >
                {metodosPago.map((mp) => (
                  <MenuItem key={mp.id} value={mp.metodo_pago}>
                    {mp.nombre}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('tesoreria.cambioDivisa.refOrigen')}
                fullWidth
                error={!!errors.referencia_transaccion_origen}
                helperText={errors.referencia_transaccion_origen?.message}
                {...register('referencia_transaccion_origen')}
              />
              <TextField
                label={t('tesoreria.cambioDivisa.refDestino')}
                fullWidth
                error={!!errors.referencia_transaccion_destino}
                helperText={errors.referencia_transaccion_destino?.message}
                {...register('referencia_transaccion_destino')}
              />
            </Stack>
            <TextField
              label={t('tesoreria.cambioDivisa.observaciones')}
              fullWidth
              multiline
              rows={2}
              error={!!errors.observaciones}
              helperText={errors.observaciones?.message}
              {...register('observaciones')}
            />
          </Stack>
        </Paper>
        <Stack direction="row" spacing={2}>
          <Button onClick={() => navigate('/tesoreria/cambio-divisa')}>{t('common.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={crearMutation.isPending}>
            {t('tesoreria.cambioDivisa.crear')}
          </Button>
        </Stack>
      </form>
    </PageContainer>
  );
}
