import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { getCuentaBancariaDetail, updateCuentaBancaria } from '../../../services/cuentaBancariaService';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { Button, TextField } from '@mui/material';

interface CuentaBancaria {
  nombre_banco: string;
  tipo_cuenta: string;
  numero_cuenta: string;
  id_moneda: string;
  activo: boolean;
  metodos_pago: string[];
}
type MetodoPagoEmpresaActiva = {
  id: string;
  metodo_pago: string; // UUID
  nombre?: string;
  metodo_pago_nombre?: string;
  nombre_metodo?: string;
};

const CuentaBancariaDetailPage: React.FC = () => {
  const { id_cuenta } = useParams<{ id_cuenta: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState<CuentaBancaria>({
    nombre_banco: '',
    tipo_cuenta: '',
    numero_cuenta: '',
    id_moneda: '',
    activo: true,
    metodos_pago: [],
  });
  const [metodosPago, setMetodosPago] = useState<MetodoPagoEmpresaActiva[]>([]);
  const [loading, setLoading] = useState(false);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id_cuenta) return;
    setLoading(true);
    (async () => {
      try {
        const data = await getCuentaBancariaDetail(id_cuenta) as CuentaBancaria;
        setForm({
          nombre_banco: data?.nombre_banco || '',
          tipo_cuenta: data?.tipo_cuenta || '',
          numero_cuenta: data?.numero_cuenta || '',
          id_moneda: data?.id_moneda || '',
          activo: data?.activo !== undefined ? data.activo : true,
          metodos_pago: Array.isArray(data?.metodos_pago) ? data.metodos_pago : [],
        });
      } finally {
        setLoading(false);
      }
    })();
  }, [id_cuenta]);

  useEffect(() => {
    fetchMonedas().then(setMonedas);
    // Obtener métodos de pago activos
    const empresa = localStorage.getItem('id_empresa') || '';
    if (empresa) {
      fetchMetodosPagoEmpresaActivos(empresa).then((res) => {
        if (Array.isArray(res)) setMetodosPago(res);
        else if (
          res &&
          typeof res === 'object' &&
          !Array.isArray(res) &&
          'results' in res &&
          Array.isArray((res as { results?: MetodoPagoEmpresaActiva[] }).results)
        ) {
          setMetodosPago((res as { results: MetodoPagoEmpresaActiva[] }).results);
        } else setMetodosPago([]);
      });
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const { name, value, type } = target;
    if (target instanceof HTMLSelectElement && target.multiple) {
      const selected: string[] = Array.from(target.selectedOptions).map(opt => opt.value);
      setForm(f => ({ ...f, [name]: selected }));
    } else {
      setForm(f => ({
        ...f,
        [name]: type === 'checkbox' ? (target as HTMLInputElement).checked : value
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_cuenta) return;
    setLoading(true);
    setError('');
    try {
      const id_empresa = localStorage.getItem('id_empresa') || '';
      await updateCuentaBancaria(id_cuenta, { ...form, metodos_pago: form.metodos_pago, id_empresa });
      navigate(-1);
    } catch {
      setError('Error al actualizar la cuenta bancaria');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Detalle de Cuenta Bancaria</h2>
      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <TextField fullWidth label="Banco" name="nombre_banco" value={form.nombre_banco} onChange={handleChange} required />
        <label>Tipo de Cuenta</label>
        <select name="tipo_cuenta" value={form.tipo_cuenta} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione un tipo</option>
          <option value="AHORRO">Ahorro</option>
          <option value="CORRIENTE">Corriente</option>
          <option value="CREDITO">Crédito</option>
        </select>
        <TextField fullWidth label="Número de Cuenta" name="numero_cuenta" value={form.numero_cuenta} onChange={handleChange} required />
        <label>Moneda</label>
        <select name="id_moneda" value={form.id_moneda} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione una moneda</option>
          {monedas.map(m => <option key={m.id_moneda} value={m.id_moneda}>{m.nombre}</option>)}
        </select>
        <label>Métodos de Pago</label>
        <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>
          Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varios métodos.
        </div>
        <select
          name="metodos_pago"
          multiple
          value={form.metodos_pago}
          onChange={handleChange}
          required={metodosPago.length > 0}
          style={{ width: '100%', marginBottom: 16, padding: 8, minHeight: 60 }}
        >
          {metodosPago.map(mp => (
            <option key={mp.metodo_pago} value={mp.metodo_pago}>
              {mp.nombre || mp.nombre_metodo || mp.metodo_pago_nombre || mp.metodo_pago}
            </option>
          ))}
        </select>
        <label>
          <input type="checkbox" name="activo" checked={form.activo} onChange={handleChange} /> Activa
        </label>
        {error && <div style={{ color: 'red', marginTop: 8 }}>{error}</div>}
        <div style={{ marginTop: 16 }}>
          <Button type="submit" disabled={loading}>{loading ? 'Guardando...' : 'Guardar Cambios'}</Button>
          <Button type="button" onClick={() => navigate(-1)} style={{ marginLeft: 8 }}>Cancelar</Button>
        </div>
      </form>
    </PageLayout>
  );
};

export default CuentaBancariaDetailPage;
