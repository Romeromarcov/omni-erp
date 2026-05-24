
import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { get, post } from '../../../services/api';
import { toList } from '../../../utils/api';
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
  const [form, setForm] = useState({
    id_moneda_origen: '',
    id_moneda_destino: '',
    tipo_tasa: '',
    valor_tasa: '',
    fecha_tasa: '',
    hora_tasa: '',
  });
  const [error, setError] = useState('');

  const { data: monedas = [] } = useQuery<unknown, Error, Moneda[]>({
    queryKey: [`/finanzas/monedas/?id_empresa=${id_empresa}`],
    queryFn: () => get(`/finanzas/monedas/?id_empresa=${id_empresa}`),
    select: toList,
    enabled: !!id_empresa,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => post('/finanzas/tasas-cambio/', payload),
    onSuccess: () => navigate(-1),
    onError: () => setError('Error al crear tasa de cambio'),
  });

  const loading = createMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    createMutation.mutate({ id_empresa, ...form });
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
