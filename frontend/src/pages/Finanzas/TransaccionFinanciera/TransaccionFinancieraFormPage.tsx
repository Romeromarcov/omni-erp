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
import PageLayout from '../../../components/PageLayout';
// import { createTransaccion } from '../../../services/transaccionFinancieraService';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { Button, TextField } from '@mui/material';


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
  const [loading, setLoading] = useState(false);

  const [monedas, setMonedas] = useState<MonedaEmpresaActiva[]>([]);
  const [metodosPago, setMetodosPago] = useState<MetodoPagoEmpresaActiva[]>([]);
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

  useEffect(() => {
    if (!idEmpresa) return;
    fetchMonedasEmpresaActivas(idEmpresa)
      .then((data) => {
        const monedasData: MonedaEmpresaActiva[] = Array.isArray(data) ? data
          : Array.isArray((data as { results?: unknown }).results) ? (data as { results: MonedaEmpresaActiva[] }).results : [];
        const activas = monedasData.filter((m: MonedaEmpresaActiva) => m.activa);
        setMonedas(activas);
        const base = activas.find((m: MonedaEmpresaActiva) => m.es_base);
        setMonedaBase(base ? base.moneda_nombre : (activas[0]?.moneda_nombre || ''));
      })
      .catch((err) => {
        console.error('Error al consultar monedas activas:', err);
        setMonedas([]);
      });
    fetchMetodosPagoEmpresaActivos(idEmpresa)
      .then((data) => {
        const metodosData: MetodoPagoEmpresaActiva[] = Array.isArray(data) ? data
          : Array.isArray((data as { results?: unknown }).results) ? (data as { results: MetodoPagoEmpresaActiva[] }).results : [];
        setMetodosPago(metodosData.filter((m: MetodoPagoEmpresaActiva) => m.activa));
      })
      .catch((err) => {
        console.error('Error al consultar métodos de pago activos:', err);
        setMetodosPago([]);
      });
  }, [idEmpresa]);

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    // Aquí iría la lógica para registrar la transacción
    // Por ahora solo navega atrás para evitar error de compilación
    setTasaError('');
    try {
      // Obtener el id del usuario autenticado desde localStorage
      const usuarioId = localStorage.getItem('id_usuario') || '';
      // Obtener id_moneda_pais_empresa e id_moneda_base desde la empresa (requiere get)
      let idMonedaPaisEmpresa = '';
      let idMonedaBase = '';
      let nombreMonedaPais = '';
      try {
        const { get, post } = await import('../../../services/api');
  const empresaData: EmpresaData = await get(`/core/empresas/${idEmpresa}/`);
  idMonedaPaisEmpresa = empresaData.id_moneda_pais || '';
  idMonedaBase = empresaData.id_moneda_base || '';
  nombreMonedaPais = empresaData.moneda_pais_nombre || '';

        // Calcular monto_moneda_pais según las reglas:
        // SI moneda_transacción = moneda_pais ENTONCES monto_pais = monto_transacción
        // SI NO monto_pais = monto_transaccion * tasa_cambio
        let montoMonedaPais = '';
        const montoTransaccionNum = parseFloat(form.monto_transaccion);
        const tasaNum = parseFloat(tasaCambio);
        
        // Buscar la moneda de transacción para comparar con moneda país
        const monedaTransaccion = monedas.find(m => m.moneda === form.id_moneda_transaccion);
        const nombreMonedaTransaccion = monedaTransaccion?.moneda_nombre || '';
        
        if (nombreMonedaTransaccion && nombreMonedaPais && nombreMonedaTransaccion === nombreMonedaPais) {
          // Moneda de transacción es igual a moneda país
          if (!isNaN(montoTransaccionNum)) {
            montoMonedaPais = montoTransaccionNum.toFixed(2);
          }
        } else {
          // Monedas diferentes: monto_pais = monto_transaccion * tasa_cambio
          if (!isNaN(montoTransaccionNum) && !isNaN(tasaNum) && tasaNum > 0) {
            montoMonedaPais = (montoTransaccionNum * tasaNum).toFixed(2);
          }
        }

        // Construir el payload para la API con los nombres y valores correctos
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
        // Usar el método post del servicio API
        await post('/finanzas/transacciones-financieras/', payload);
        // Si todo sale bien, navegar a la lista de transacciones
        navigate(`/empresas/${idEmpresa}/transacciones-financieras`);
  } catch (err) {
        let errorMsg = 'Error al registrar transacción.';
        if (isErrorWithDetailOrMessage(err)) {
          if (typeof err.detail === 'string') {
            errorMsg = err.detail;
          } else if (typeof err.message === 'string') {
            errorMsg = err.message;
          }
        }
        setTasaError(errorMsg);
        setLoading(false);
        return;
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setTasaError('Error inesperado: ' + err.message);
      } else {
        setTasaError('Error inesperado.');
      }
    }
    setLoading(false);
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Registrar Transacción</h2>
      <form onSubmit={handleSubmit} style={{ maxWidth: 400, margin: '0 auto' }}>
        <TextField fullWidth label="Fecha" name="fecha_hora_transaccion" type="datetime-local" value={form.fecha_hora_transaccion} onChange={handleChange} required />
        <label style={{ display: 'block', marginBottom: 4 }}>Tipo de Transacción</label>
        <select name="tipo_transaccion" value={form.tipo_transaccion} onChange={handleChange} style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc', width: '100%', marginBottom: 16 }}>
          {tipoTransaccionOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <TextField fullWidth label="Monto" name="monto_transaccion" type="number" value={form.monto_transaccion} onChange={handleChange} required />

        {/* Dropdown de monedas activas */}
        <label style={{ display: 'block', marginBottom: 4 }}>Moneda de Transacción</label>
        <select name="id_moneda_transaccion" value={form.id_moneda_transaccion} onChange={handleChange} required style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc', width: '100%', marginBottom: 16 }}>
          <option value="">Seleccione una moneda</option>
          {monedas.map(moneda => (
            <option key={moneda.id} value={moneda.moneda}>{moneda.moneda_nombre}</option>
          ))}
        </select>

        {/* Dropdown de métodos de pago activos */}
        <label style={{ display: 'block', marginBottom: 4 }}>Método de Pago</label>
        <select name="id_metodo_pago" value={form.id_metodo_pago} onChange={handleChange} required style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc', width: '100%', marginBottom: 16 }}>
          <option value="">Seleccione método de pago</option>
          {metodosPago.map(metodo => (
            <option key={metodo.id} value={metodo.metodo_pago}>{metodo.nombre}</option>
          ))}
        </select>

        {/* Moneda base (readonly) */}
        <TextField fullWidth label="Moneda Base" name="moneda_base" value={monedaBase} readOnly style={{ marginBottom: 16 }} />

        {/* Tasa de cambio (editable, validada) */}
        <TextField fullWidth label="Tasa de Cambio" name="tasa_cambio" type="number" value={tasaCambio} onChange={handleTasaCambio} required min="0.0001" step="0.0001" style={{ marginBottom: 16 }} />
        {tasaError && <div style={{ color: 'red', marginBottom: 8 }}>{tasaError}</div>}

        {/* Monto base (readonly, auto-calculado) */}
        <TextField fullWidth label="Monto Base" name="monto_base" value={montoBase} readOnly style={{ marginBottom: 16 }} />

        <TextField fullWidth label="Referencia" name="referencia_pago" value={form.referencia_pago} onChange={handleChange} />
        <TextField fullWidth label="Descripción" name="descripcion" value={form.descripcion} onChange={handleChange} />
        <TextField fullWidth label="Caja" name="id_caja" value={form.id_caja} onChange={handleChange} required />
        <TextField fullWidth label="Cuenta Bancaria" name="id_cuenta_bancaria" value={form.id_cuenta_bancaria} onChange={handleChange} />
        <label style={{ display: 'block', marginBottom: 4 }}>Tipo de Documento Asociado</label>
        <select name="tipo_documento_asociado" value={form.tipo_documento_asociado} onChange={handleChange} required style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc', width: '100%', marginBottom: 16 }}>
          <option value="">Seleccione tipo de documento</option>
          <option value="COMPRA">Compra</option>
          <option value="VENTA">Venta</option>
          <option value="GASTO">Gasto</option>
          <option value="NOMINA">Nómina</option>
          <option value="AJUSTE">Ajuste</option>
        </select>
        <TextField fullWidth label="Nro. Documento Asociado" name="nro_documento_asociado" value={form.nro_documento_asociado} onChange={handleChange} />
        <Button type="submit" disabled={loading}>
          {loading ? 'Registrando...' : 'Registrar transacción'}
        </Button>
      </form>
    </PageLayout>
  );
}
export default TransaccionFinancieraFormPage;
