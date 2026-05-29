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
import PageLayout from '../../../components/PageLayout';
// import { createTransaccion } from '../../../services/transaccionFinancieraService';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { toList } from '../../../utils/api';
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
  const [form, setForm] = useState({
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
  });

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
    if (!idEmpresa || !form.id_moneda_transaccion || !form.fecha_hora_transaccion) return;
    // Buscar la moneda seleccionada en el array de monedas activas
    const monedaDestino = monedas.find(m => m.moneda === form.id_moneda_transaccion);
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
    if (form.fecha_hora_transaccion.includes('T')) {
      fecha = form.fecha_hora_transaccion.split('T')[0];
    } else if (form.fecha_hora_transaccion.length >= 10) {
      fecha = form.fecha_hora_transaccion.substring(0, 10);
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
  }, [idEmpresa, form.id_moneda_transaccion, monedas, form.fecha_hora_transaccion, monedaBase]);

  useEffect(() => {
    const monto = parseFloat(form.monto_transaccion);
    const tasa = parseFloat(tasaCambio);
    // Buscar la moneda seleccionada en el array de monedas activas
    const monedaDestino = monedas.find(m => m.moneda === form.id_moneda_transaccion);
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
  }, [form.monto_transaccion, tasaCambio, monedaBase, form.id_moneda_transaccion, monedas]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

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
    mutationFn: async () => {
      const usuarioId = localStorage.getItem('id_usuario') || '';
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setTasaError('');
    createMutation.mutate();
  };

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Registrar Transacción</Typography>
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField
            label="Fecha"
            name="fecha_hora_transaccion"
            type="datetime-local"
            value={form.fecha_hora_transaccion}
            onChange={handleChange}
            required
            slotProps={{ inputLabel: { shrink: true } }}
            fullWidth
          />
          <TextField
            select
            label="Tipo de Transacción"
            name="tipo_transaccion"
            value={form.tipo_transaccion}
            onChange={handleChange}
            fullWidth
          >
            {tipoTransaccionOptions.map(opt => (
              <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="Monto"
            name="monto_transaccion"
            type="number"
            value={form.monto_transaccion}
            onChange={handleChange}
            required
            fullWidth
          />
          <TextField
            select
            label="Moneda de Transacción"
            name="id_moneda_transaccion"
            value={form.id_moneda_transaccion}
            onChange={handleChange}
            required
            fullWidth
          >
            <MenuItem value="">Seleccione una moneda</MenuItem>
            {monedas.map(moneda => (
              <MenuItem key={moneda.id} value={moneda.moneda}>{moneda.moneda_nombre}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Método de Pago"
            name="id_metodo_pago"
            value={form.id_metodo_pago}
            onChange={handleChange}
            required
            fullWidth
          >
            <MenuItem value="">Seleccione método de pago</MenuItem>
            {metodosPago.map(metodo => (
              <MenuItem key={metodo.id} value={metodo.metodo_pago}>{metodo.nombre}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="Moneda Base"
            name="moneda_base"
            value={monedaBase}
            slotProps={{ input: { readOnly: true } }}
            fullWidth
          />
          <TextField
            label="Tasa de Cambio"
            name="tasa_cambio"
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
            name="monto_base"
            value={montoBase}
            slotProps={{ input: { readOnly: true } }}
            fullWidth
          />
          <TextField label="Referencia" name="referencia_pago" value={form.referencia_pago} onChange={handleChange} fullWidth />
          <TextField label="Descripción" name="descripcion" value={form.descripcion} onChange={handleChange} fullWidth />
          <TextField label="Caja" name="id_caja" value={form.id_caja} onChange={handleChange} required fullWidth />
          <TextField label="Cuenta Bancaria" name="id_cuenta_bancaria" value={form.id_cuenta_bancaria} onChange={handleChange} fullWidth />
          <TextField
            select
            label="Tipo de Documento Asociado"
            name="tipo_documento_asociado"
            value={form.tipo_documento_asociado}
            onChange={handleChange}
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
          <TextField label="Nro. Documento Asociado" name="nro_documento_asociado" value={form.nro_documento_asociado} onChange={handleChange} fullWidth />
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
