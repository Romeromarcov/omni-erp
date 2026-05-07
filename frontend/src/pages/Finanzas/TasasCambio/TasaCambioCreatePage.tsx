
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { get, post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface Moneda {
  id_moneda: string;
  codigo_iso: string;
  nombre: string;
}

const TIPO_TASA = [
  { value: 'OFICIAL_BCV', label: 'Oficial BCV' },
  { value: 'ESPECIAL_USUARIO', label: 'Especial Usuario' },
  { value: 'PROMEDIO_MERCADO', label: 'Promedio Mercado' },
  { value: 'FIJA', label: 'Fija' },
];

const TasaCambioCreatePage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [form, setForm] = useState({
    id_moneda_origen: '',
    id_moneda_destino: '',
    tipo_tasa: '',
    valor_tasa: '',
    fecha_tasa: '',
    hora_tasa: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    get(`/finanzas/monedas/?id_empresa=${id_empresa}`)
      .then((res) => {
        if (Array.isArray(res)) setMonedas(res);
        else if (res && typeof res === 'object' && 'results' in res) setMonedas((res as { results: Moneda[] }).results);
        else setMonedas([]);
      })
      .catch(() => setMonedas([]));
  }, [id_empresa]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await post('/finanzas/tasas-cambio/', {
        id_empresa,
        ...form,
      });
      navigate(-1);
    } catch {
      setError('Error al crear tasa de cambio');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout maxWidth={500}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Nueva Tasa de Cambio</h2>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button variant="contained" color="secondary" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </div>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <label style={{ fontWeight: 500 }}>Moneda Origen
          <select required value={form.id_moneda_origen} onChange={e => setForm(f => ({ ...f, id_moneda_origen: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
            <option value="">Seleccione</option>
            {monedas.map(m => <option key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso} - {m.nombre}</option>)}
          </select>
        </label>
        <label style={{ fontWeight: 500 }}>Moneda Destino
          <select required value={form.id_moneda_destino} onChange={e => setForm(f => ({ ...f, id_moneda_destino: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
            <option value="">Seleccione</option>
            {monedas.map(m => <option key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso} - {m.nombre}</option>)}
          </select>
        </label>
        <label style={{ fontWeight: 500 }}>Tipo de Tasa
          <select required value={form.tipo_tasa} onChange={e => setForm(f => ({ ...f, tipo_tasa: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
            <option value="">Seleccione</option>
            {TIPO_TASA.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label style={{ fontWeight: 500 }}>Valor
          <input required type="number" step="0.00000001" value={form.valor_tasa} onChange={e => setForm(f => ({ ...f, valor_tasa: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
        </label>
        <label style={{ fontWeight: 500 }}>Fecha
          <input required type="date" value={form.fecha_tasa} onChange={e => setForm(f => ({ ...f, fecha_tasa: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
        </label>
        <label style={{ fontWeight: 500 }}>Hora
          <input type="time" value={form.hora_tasa} onChange={e => setForm(f => ({ ...f, hora_tasa: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
        </label>
        {error && <div style={{ color: 'red', marginTop: 8 }}>{error}</div>}
        <Button type="submit" variant="contained" disabled={loading} style={{ marginTop: 8 }}>
          {loading ? 'Registrando...' : 'Registrar'}
        </Button>
      </form>
    </PageLayout>
  );
};

export default TasaCambioCreatePage;
