import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
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
  const [form, setForm] = useState<Caja>({ nombre: '', sucursal: '', moneda: '', activa: true, tipo_caja: '', metodos_pago: [] });
  const [tipoCajas, setTipoCajas] = useState<TipoCajaChoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [metodosPago, setMetodosPago] = useState<MetodoPagoEmpresaActiva[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id_caja) return;
    setLoading(true);
    (async () => {
      try {
        const data = await getCajaDetail(id_caja) as Caja;
        setForm({
          nombre: data?.nombre || '',
          sucursal: data?.sucursal || '',
          moneda: data?.moneda || '',
          activa: data?.activa !== undefined ? data.activa : true,
          tipo_caja: data?.tipo_caja || '',
          metodos_pago: Array.isArray(data?.metodos_pago) ? data.metodos_pago : [],
        });
      } finally {
        setLoading(false);
      }
    })();
  }, [id_caja]);

  useEffect(() => {
    // Obtener sucursales, monedas, tipos de caja y métodos de pago para los selects
    const empresa = localStorage.getItem('id_empresa') || '';
    if (empresa) {
      fetchSucursales(empresa).then(setSucursales);
      fetchMonedas().then(setMonedas);
      getCajaTipoChoices().then((choices) => setTipoCajas(choices as TipoCajaChoice[]));
      fetchMetodosPagoEmpresaActivos(empresa).then((res) => {
        if (Array.isArray(res)) setMetodosPago(res);
        else if (res && typeof res === 'object' && Array.isArray((res as { results?: MetodoPagoEmpresaActiva[] }).results)) setMetodosPago((res as { results: MetodoPagoEmpresaActiva[] }).results);
        else setMetodosPago([]);
      });
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const { name, value, type } = target;
    if (target instanceof HTMLSelectElement && target.multiple) {
      // Multiselect para metodos_pago
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_caja) return;
    setLoading(true);
    setError('');
    try {
      await updateCaja(id_caja, { ...form, metodos_pago: form.metodos_pago });
      navigate(-1);
    } catch {
      setError('Error al actualizar la caja');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Detalle/Edición de Caja</h2>
      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <TextField fullWidth label="Nombre de Caja" name="nombre" value={form.nombre} onChange={handleChange} required />
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
    </PageLayout>
  );
};

export default CajaDetailPage;
