import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { createCuentaBancaria } from '../../../services/cuentaBancariaService';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { toList } from '../../../utils/api';
import { Button, TextField } from '@mui/material';

type MetodoPagoEmpresaActiva = {
  id: string;
  metodo_pago: string; // UUID
  nombre?: string;
  metodo_pago_nombre?: string;
  nombre_metodo?: string;
};

const CuentaBancariaCreatePage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    nombre_banco: '',
    tipo_cuenta: '',
    numero_cuenta: '',
    id_moneda: '',
    activo: true,
    metodos_pago: [] as string[],
  });
  const [error, setError] = useState('');

  const { data: monedas = [] } = useQuery<Moneda[], Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/'],
    queryFn: () => fetchMonedas(),
    enabled: !!id_empresa,
  });

  const { data: metodosPago = [] } = useQuery<unknown, Error, MetodoPagoEmpresaActiva[]>({
    queryKey: [`/finanzas/metodos-pago-empresa-activos/${id_empresa}/`],
    queryFn: () => fetchMetodosPagoEmpresaActivos(id_empresa!),
    select: toList,
    enabled: !!id_empresa,
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof form & { id_empresa: string }) => createCuentaBancaria(payload.id_empresa, payload),
    onSuccess: () => navigate(-1),
    onError: () => setError('Error al crear la cuenta bancaria'),
  });

  const loading = createMutation.isPending;

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
    if (!id_empresa) return;
    setError('');
    createMutation.mutate({ ...form, id_empresa, metodos_pago: form.metodos_pago });
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Crear Nueva Cuenta Bancaria</h2>
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
          <Button type="submit" disabled={loading}>{loading ? 'Guardando...' : 'Crear Cuenta'}</Button>
          <Button type="button" onClick={() => navigate(-1)} style={{ marginLeft: 8 }}>Cancelar</Button>
        </div>
      </form>
    </PageLayout>
  );
};

export default CuentaBancariaCreatePage;
