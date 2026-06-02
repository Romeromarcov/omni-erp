function isErrorWithDetailOrMessage(err: unknown): err is { detail?: string; message?: string } {
  return (
    typeof err === 'object' && err !== null &&
    ('detail' in err || 'message' in err)
  );
}
interface EmpresaData {
  id_moneda_pais?: string;
  id_moneda_base?: string;
  moneda_pais_nombre?: string;
}

interface TasaBCVResponse {
  valor_tasa?: number;
}
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import PageLayout from '../../../components/PageLayout';
// import { createTransaccion } from '../../../services/transaccionFinancieraService';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { toList } from '../../../utils/api';
import { registroTransaccionSchema, type RegistroTransaccionInput } from '../../../schemas/finanzas.schemas';
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';


const tipoTransaccionOptions = [
  { value: 'ingreso', label: 'Ingreso' },
  { value: 'egreso', label: 'Egreso' },
];


interface MonedaEmpresaActiva {
  id: string;
  nombre: string;
  activa: boolean;
  es_base?: boolean;
  moneda: string;
  moneda_nombre: string;
  codigo_iso: string;
  moneda_codigo_iso?: string;
}

interface MetodoPagoEmpresaActiva {
  id: string;
  nombre: string;
  activa: boolean;
  metodo_pago: string;
}

const TransaccionFinancieraFormPage: React.FC = () => {
  // Obtener automáticamente el UUID de la empresa principal del usuario autenticado
  const [idEmpresa, setIdEmpresa] = useState<string>('');
  const navigate = useNavigate();
  const [monedaBase, setMonedaBase] = useState('');
  const [tasaCambio, setTasaCambio] = useState('');
  const [tasaBCV, setTasaBCV] = useState<number | null>(null);
  const [tasaError, setTasaError] = useState('');
  const [montoBase, setMontoBase] = useState('');

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RegistroTransaccionInput>({
    resolver: zodResolver(registroTransaccionSchema),
    mode: 'onBlur',
    defaultValues: {
      fecha_hora_transaccion: '',
      tipo_transaccion: 'ingreso',
      monto_transaccion: '',
      id_moneda_transaccion: '',
      id_metodo_pago: '',
      referencia_pago: '',
      descripcion: '',
      id_caja: '',
      id_cuenta_bancaria: '',
      tipo_documento_asociado: '',
      nro_documento_asociado: '',
    },
  });

  // Valores observados que alimentan los cálculos derivados (tasa BCV / monto base).
  const idMonedaTransaccion = watch('id_moneda_transaccion');
  const fechaHoraTransaccion = watch('fecha_hora_transaccion');
  const montoTransaccion = watch('monto_transaccion');

  useEffect(() => {
    import('../../../services/empresas').then(({ fetchEmpresas }) => {
      fetchEmpresas().then((empresas: { id_empresa: string }[] | { results: { id_empresa: string }[] }) => {
        const empresasArray = Array.isArray(empresas) ? empresas : (empresas && Array.isArray(empresas.results) ? empresas.results : []);
        if (empresasArray.length > 0) {
          setIdEmpresa(empresasArray[0].id_empresa);
        }
      }).catch(err => {
        console.error('Error al obtener empresas:', err);
      });
    }).catch(err => {
      console.error('Error al importar servicio de empresas:', err);
    });
  }, []);

  const { data: monedasRaw = [] } = useQuery<unknown, Error, MonedaEmpresaActiva[]>({
    queryKey: [`/finanzas/monedas-empresa-activas/${idEmpresa}/`],
    queryFn: () => fetchMonedasEmpresaActivas(idEmpresa),
    select: toList,
    enabled: !!idEmpresa,
  });

  const monedas = monedasRaw.filter((m: MonedaEmpresaActiva) => m.activa);

  useEffect(() => {
    if (monedas.length > 0) {
      const base = monedas.find((m: MonedaEmpresaActiva) => m.es_base);
      setMonedaBase(base ? base.moneda_nombre : (monedas[0]?.moneda_nombre || ''));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monedasRaw]);

  const { data: metodosPagoRaw = [] } = useQuery<unknown, Error, MetodoPagoEmpresaActiva[]>({
    queryKey: [`/finanzas/metodos-pago-empresa-activos/${idEmpresa}/`],
    queryFn: () => fetchMetodosPagoEmpresaActivos(idEmpresa),
    select: toList,
    enabled: !!idEmpresa,
  });

  const metodosPago = metodosPagoRaw.filter((m: MetodoPagoEmpresaActiva) => m.activa);

  useEffect(() => {
    if (!idEmpresa || !idMonedaTransaccion || !fechaHoraTransaccion) return;
    // Buscar la moneda seleccionada en el array de monedas activas
    const monedaDestino = monedas.find(m => m.moneda === idMonedaTransaccion);
    const nombreMonedaDestino = monedaDestino?.moneda_nombre || '';
    const codigoDestino = monedaDestino?.moneda_codigo_iso || monedaDestino?.codigo_iso;
    // Si la moneda base es igual a la moneda de transacción, tasa = 1
    if (monedaBase && nombreMonedaDestino && monedaBase === nombreMonedaDestino) {
      setTasaCambio('1');
      setTasaBCV(1);
      setTasaError('');
      return;
    }
    // Si son diferentes, consultar la API
    const codigoOrigen = 'USD';
    // Extraer solo la fecha en formato YYYY-MM-DD
    let fecha = '';
    if (fechaHoraTransaccion.includes('T')) {
      fecha = fechaHoraTransaccion.split('T')[0];
    } else if (fechaHoraTransaccion.length >= 10) {
      fecha = fechaHoraTransaccion.substring(0, 10);
    }
    if (codigoDestino && fecha) {
      import('../../../services/api').then(({ get }) => {
        get(`/finanzas/tasa-oficial-bcv/?moneda_origen=${codigoOrigen}&moneda_destino=${codigoDestino}&fecha=${fecha}`)
          .then((data) => {
            const tasaData = data as TasaBCVResponse;
            if (tasaData && typeof tasaData.valor_tasa === 'number') {
              setTasaBCV(tasaData.valor_tasa);
              setTasaCambio(tasaData.valor_tasa.toString());
            } else {
              setTasaBCV(null);
              setTasaCambio('');
            }
          })
          .catch(() => {
            setTasaBCV(null);
            setTasaCambio('');
          });
      });
    }
  }, [idEmpresa, idMonedaTransaccion, monedas, fechaHoraTransaccion, monedaBase]);

  useEffect(() => {
    const monto = parseFloat(montoTransaccion);
    const tasa = parseFloat(tasaCambio);
    // Buscar la moneda seleccionada en el array de monedas activas
    const monedaDestino = monedas.find(m => m.moneda === idMonedaTransaccion);
    const nombreMonedaDestino = monedaDestino?.moneda_nombre || '';
    // Si la moneda base es igual a la moneda de transacción
    if (monedaBase && nombreMonedaDestino && monedaBase === nombreMonedaDestino) {
      if (!isNaN(monto)) {
        setMontoBase(monto.toFixed(2));
      } else {
        setMontoBase('');
      }
    } else {
      // Si son diferentes, monto base = monto transaccion / tasa de cambio
      if (!isNaN(monto) && !isNaN(tasa) && tasa > 0) {
        setMontoBase((monto / tasa).toFixed(2));
      } else {
        setMontoBase('');
      }
    }
  }, [montoTransaccion, tasaCambio, monedaBase, idMonedaTransaccion, monedas]);

  // Validar tasa de cambio (debe ser > 0)
  const handleTasaCambio = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    if (/^\d*\.?\d*$/.test(value)) {
      setTasaCambio(value);
      // Validar que no sea menor a la tasa BCV
      if (tasaBCV !== null && parseFloat(value) < tasaBCV) {
        setTasaError(`La tasa no puede ser menor a la oficial BCV (${tasaBCV})`);
      } else {
        setTasaError('');
      }
    }
  };

  const createMutation = useMutation({
    mutationFn: async (form: RegistroTransaccionInput) => {
      const { getSessionUsuarioId } = await import('../../../services/session');
      const usuarioId = getSessionUsuarioId();
      const { get, post } = await import('../../../services/api');
      const empresaData: EmpresaData = await get(`/core/empresas/${idEmpresa}/`);
      const idMonedaPaisEmpresa = empresaData.id_moneda_pais || '';
      const idMonedaBase = empresaData.id_moneda_base || '';
      const nombreMonedaPais = empresaData.moneda_pais_nombre || '';

      let montoMonedaPais = '';
      const montoTransaccionNum = parseFloat(form.monto_transaccion);
      const tasaNum = parseFloat(tasaCambio);
      const monedaTransaccion = monedas.find(m => m.moneda === form.id_moneda_transaccion);
      const nombreMonedaTransaccion = monedaTransaccion?.moneda_nombre || '';

      if (nombreMonedaTransaccion && nombreMonedaPais && nombreMonedaTransaccion === nombreMonedaPais) {
        if (!isNaN(montoTransaccionNum)) {
          montoMonedaPais = montoTransaccionNum.toFixed(2);
        }
      } else {
        if (!isNaN(montoTransaccionNum) && !isNaN(tasaNum) && tasaNum > 0) {
          montoMonedaPais = (montoTransaccionNum * tasaNum).toFixed(2);
        }
      }

      const payload = {
        fecha_hora_transaccion: form.fecha_hora_transaccion,
        tipo_transaccion: (form.tipo_transaccion || '').toUpperCase(),
        monto_transaccion: form.monto_transaccion,
        id_moneda_transaccion: form.id_moneda_transaccion,
        id_metodo_pago: form.id_metodo_pago,
        referencia_pago: form.referencia_pago,
        descripcion: form.descripcion,
        tasa_cambio: tasaCambio,
        monto_base: montoBase,
        id_empresa: idEmpresa,
        id_usuario_registro: usuarioId,
        id_moneda_base: idMonedaBase,
        id_moneda_pais_empresa: idMonedaPaisEmpresa,
        monto_moneda_pais: montoMonedaPais,
        id_caja: form.id_caja,
        id_cuenta_bancaria: form.id_cuenta_bancaria,
        tipo_documento_asociado: form.tipo_documento_asociado,
        nro_documento_asociado: form.nro_documento_asociado,
      };
      return post('/finanzas/transacciones-financieras/', payload);
    },
    onSuccess: () => {
      navigate(`/empresas/${idEmpresa}/transacciones-financieras`);
    },
    onError: (err: unknown) => {
      let errorMsg = 'Error al registrar transacción.';
      if (isErrorWithDetailOrMessage(err)) {
        if (typeof err.detail === 'string') {
          errorMsg = err.detail;
        } else if (typeof err.message === 'string') {
          errorMsg = err.message;
        }
      }
      setTasaError(errorMsg);
    },
  });

  const loading = createMutation.isPending;

  const onSubmit = (values: RegistroTransaccionInput) => {
    setTasaError('');
    createMutation.mutate(values);
  };

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Registrar Transacción</Typography>
      <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Stack spacing={2}>
          <TextField
            label="Fecha"
            type="datetime-local"
            {...register('fecha_hora_transaccion')}
            error={!!errors.fecha_hora_transaccion}
            helperText={errors.fecha_hora_transaccion?.message}
            required
            slotProps={{ inputLabel: { shrink: true } }}
            fullWidth
          />
          <Controller
            name="tipo_transaccion"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Tipo de Transacción"
                {...field}
                error={!!errors.tipo_transaccion}
                helperText={errors.tipo_transaccion?.message}
                fullWidth
              >
                {tipoTransaccionOptions.map(opt => (
                  <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                ))}
              </TextField>
            )}
          />
          <TextField
            label="Monto"
            type="number"
            {...register('monto_transaccion')}
            error={!!errors.monto_transaccion}
            helperText={errors.monto_transaccion?.message}
            required
            fullWidth
          />
          <Controller
            name="id_moneda_transaccion"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Moneda de Transacción"
                {...field}
                error={!!errors.id_moneda_transaccion}
                helperText={errors.id_moneda_transaccion?.message}
                required
                fullWidth
              >
                <MenuItem value="">Seleccione una moneda</MenuItem>
                {monedas.map(moneda => (
                  <MenuItem key={moneda.id} value={moneda.moneda}>{moneda.moneda_nombre}</MenuItem>
                ))}
              </TextField>
            )}
          />
          <Controller
            name="id_metodo_pago"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Método de Pago"
                {...field}
                error={!!errors.id_metodo_pago}
                helperText={errors.id_metodo_pago?.message}
                required
                fullWidth
              >
                <MenuItem value="">Seleccione método de pago</MenuItem>
                {metodosPago.map(metodo => (
                  <MenuItem key={metodo.id} value={metodo.metodo_pago}>{metodo.nombre}</MenuItem>
                ))}
              </TextField>
            )}
          />
          <TextField
            label="Moneda Base"
            value={monedaBase}
            slotProps={{ input: { readOnly: true } }}
            fullWidth
          />
          <TextField
            label="Tasa de Cambio"
            type="number"
            value={tasaCambio}
            onChange={handleTasaCambio}
            required
            slotProps={{ htmlInput: { min: '0.0001', step: '0.0001' } }}
            fullWidth
          />
          {tasaError && <Alert severity="error">{tasaError}</Alert>}
          <TextField
            label="Monto Base"
            value={montoBase}
            slotProps={{ input: { readOnly: true } }}
            fullWidth
          />
          <TextField label="Referencia" {...register('referencia_pago')} fullWidth />
          <TextField label="Descripción" {...register('descripcion')} fullWidth />
          <TextField label="Caja" {...register('id_caja')} error={!!errors.id_caja} helperText={errors.id_caja?.message} required fullWidth />
          <TextField label="Cuenta Bancaria" {...register('id_cuenta_bancaria')} fullWidth />
          <Controller
            name="tipo_documento_asociado"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Tipo de Documento Asociado"
                {...field}
                error={!!errors.tipo_documento_asociado}
                helperText={errors.tipo_documento_asociado?.message}
                required
                fullWidth
              >
                <MenuItem value="">Seleccione tipo de documento</MenuItem>
                <MenuItem value="COMPRA">Compra</MenuItem>
                <MenuItem value="VENTA">Venta</MenuItem>
                <MenuItem value="GASTO">Gasto</MenuItem>
                <MenuItem value="NOMINA">Nómina</MenuItem>
                <MenuItem value="AJUSTE">Ajuste</MenuItem>
              </TextField>
            )}
          />
          <TextField label="Nro. Documento Asociado" {...register('nro_documento_asociado')} fullWidth />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Registrando...' : 'Registrar transacción'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
}
export default TransaccionFinancieraFormPage;
