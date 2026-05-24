import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createCaja, getCajaTipoChoices } from '../../../services/cajaService';
import { fetchSucursales } from '../../../services/sucursales';
import type { Sucursal } from '../../../services/sucursales';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { Button, TextField } from '@mui/material';

type TipoCajaChoice = { value: string; display: string };

type MetodoPagoEmpresaActiva = {
  id: string;
  metodo_pago: string; // UUID
  nombre?: string;
  metodo_pago_nombre?: string;
  nombre_metodo?: string;
};

const CajaCreatePage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ nombre: '', sucursal: '', moneda: '', activa: true, tipo_caja: '', metodos_pago: [] as string[] });
  const [error, setError] = useState('');

  const { data: sucursales = [] } = useQuery<Sucursal[]>({
    queryKey: ['/core/sucursales/', id_empresa],
    queryFn: () => fetchSucursales(id_empresa!),
    enabled: !!id_empresa,
  });

  const { data: monedas = [] } = useQuery<Moneda[]>({
    queryKey: ['/finanzas/monedas/'],
    queryFn: fetchMonedas,
  });

  const { data: tipoCajas = [] } = useQuery<TipoCajaChoice[]>({
    queryKey: ['/finanzas/cajas/tipo-caja-choices/'],
    queryFn: () => getCajaTipoChoices() as Promise<TipoCajaChoice[]>,
  });

  const { data: metodosPago = [] } = useQuery<MetodoPagoEmpresaActiva[]>({
    queryKey: ['/finanzas/metodos-pago-empresa-activas/', id_empresa],
    queryFn: () => fetchMetodosPagoEmpresaActivos(id_empresa!) as unknown as Promise<MetodoPagoEmpresaActiva[]>,
    enabled: !!id_empresa,
  });

  const createMutation = useMutation({
    mutationFn: () => createCaja(id_empresa!, { ...form, saldo_actual: 0.0, metodos_pago: form.metodos_pago }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/cajas/'] });
      navigate(-1);
    },
    onError: () => {
      setError('Error al crear la caja');
    },
  });

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_empresa) return;
    setError('');
    createMutation.mutate();
  };

  const loading = createMutation.isPending;

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Crear Nueva Caja</h2>
      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <TextField fullWidth label="Nombre de Caja" name="nombre" value={form.nombre} onChange={handleChange as React.ChangeEventHandler<HTMLInputElement>} required />
        <label>Tipo de Caja</label>
        <select name="tipo_caja" value={form.tipo_caja} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione un tipo</option>
          {tipoCajas.map(tc => <option key={tc.value} value={tc.value}>{tc.display}</option>)}
        </select>
        <label>Sucursal</label>
        <select name="sucursal" value={form.sucursal} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione una sucursal</option>
          {sucursales.map(s => <option key={s.id_sucursal} value={s.id_sucursal}>{s.nombre}</option>)}
        </select>
        <label>Moneda</label>
        <select name="moneda" value={form.moneda} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione una moneda</option>
          {monedas.map(m => <option key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso} - {m.nombre}</option>)}
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
        <label style={{ display: 'block', marginBottom: 8 }}>
          <input type="checkbox" name="activa" checked={form.activa} onChange={handleChange} /> Activa
        </label>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button type="submit" disabled={loading}>Crear</Button>
          <Button type="button" variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
        </div>
        {error && <div style={{ color: 'red', marginTop: 12 }}>{error}</div>}
      </form>
    </PageLayout>
  );
};

export default CajaCreatePage;
