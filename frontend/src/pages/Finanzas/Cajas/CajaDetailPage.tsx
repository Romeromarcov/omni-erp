import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageContainer, PageHeader } from '../../../components/ui';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCajaDetail, updateCaja, getCajaTipoChoices } from '../../../services/cajaService';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { fetchSucursales } from '../../../services/sucursales';
import type { Sucursal } from '../../../services/sucursales';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { Button, TextField } from '@mui/material';

// Define or import the Caja type
type Caja = {
  nombre: string;
  sucursal: string;
  moneda: string;
  activa: boolean;
  tipo_caja: string;
  tipo_caja_display?: string;
  metodos_pago: string[];
};
type MetodoPagoEmpresaActiva = {
  id: string;
  metodo_pago: string; // UUID
  nombre?: string;
  metodo_pago_nombre?: string;
  nombre_metodo?: string;
};
type TipoCajaChoice = { value: string; display: string };

const CajaDetailPage: React.FC = () => {
  const { id_caja } = useParams<{ id_caja: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Caja>({ nombre: '', sucursal: '', moneda: '', activa: true, tipo_caja: '', metodos_pago: [] });
  const [error, setError] = useState('');

  const empresa = localStorage.getItem('id_empresa') || '';

  const { data: cajaData } = useQuery<Caja>({
    queryKey: ['/finanzas/cajas/', id_caja],
    queryFn: () => getCajaDetail(id_caja!) as Promise<Caja>,
    enabled: !!id_caja,
  });

  useEffect(() => {
    if (cajaData) {
      setForm({
        nombre: cajaData?.nombre || '',
        sucursal: cajaData?.sucursal || '',
        moneda: cajaData?.moneda || '',
        activa: cajaData?.activa !== undefined ? cajaData.activa : true,
        tipo_caja: cajaData?.tipo_caja || '',
        metodos_pago: Array.isArray(cajaData?.metodos_pago) ? cajaData.metodos_pago : [],
      });
    }
  }, [cajaData]);

  const { data: sucursales = [] } = useQuery<Sucursal[]>({
    queryKey: ['/core/sucursales/', empresa],
    queryFn: () => fetchSucursales(empresa),
    enabled: !!empresa,
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
    queryKey: ['/finanzas/metodos-pago-empresa-activas/', empresa],
    queryFn: () => fetchMetodosPagoEmpresaActivos(empresa) as unknown as Promise<MetodoPagoEmpresaActiva[]>,
    enabled: !!empresa,
  });

  const updateMutation = useMutation({
    mutationFn: () => updateCaja(id_caja!, { ...form, metodos_pago: form.metodos_pago }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/cajas/', id_caja] });
      queryClient.invalidateQueries({ queryKey: ['/finanzas/cajas/'] });
      navigate(-1);
    },
    onError: () => {
      setError('Error al actualizar la caja');
    },
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const { name, value, type } = target;
    if (target instanceof HTMLSelectElement && target.multiple) {
      const selected: string[] = Array.from(target.selectedOptions).map(opt => opt.value);
      setForm(f => ({ ...f, [name]: selected }));
    } else {
      let fieldValue: string | boolean = value;
      if (type === 'checkbox') {
        fieldValue = (target as HTMLInputElement).checked;
      }
      setForm(f => ({ ...f, [name]: fieldValue }));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_caja) return;
    setError('');
    updateMutation.mutate();
  };

  const loading = updateMutation.isPending;

  return (
    <PageContainer>
      <PageHeader title="Detalle/Edición de Caja" />
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
          <Button type="submit" disabled={loading}>Actualizar</Button>
          <Button type="button" variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
          <Button type="button" variant="outlined" onClick={() => navigate(`/cajas/${id_caja}/movimientos-caja-banco`)}>Ver Movimientos</Button>
        </div>
        {error && <div style={{ color: 'red', marginTop: 12 }}>{error}</div>}
      </form>
    </PageContainer>
  );
};

export default CajaDetailPage;
