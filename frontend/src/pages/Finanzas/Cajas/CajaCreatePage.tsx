import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { createCaja } from '../../../services/cajaService';
import { fetchSucursales } from '../../../services/sucursales';
import type { Sucursal } from '../../../services/sucursales';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';


import { getCajaTipoChoices } from '../../../services/cajaService';
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
  const [form, setForm] = useState({ nombre: '', sucursal: '', moneda: '', activa: true, tipo_caja: '', metodos_pago: [] as string[] });
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [tipoCajas, setTipoCajas] = useState<TipoCajaChoice[]>([]);
  const [metodosPago, setMetodosPago] = useState<MetodoPagoEmpresaActiva[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (id_empresa) {
      fetchSucursales(id_empresa).then(setSucursales);
      fetchMonedas().then(setMonedas);
      getCajaTipoChoices().then((choices) => setTipoCajas(choices as TipoCajaChoice[]));
      fetchMetodosPagoEmpresaActivos(id_empresa).then((res) => {
        // Puede venir paginado o como array directa
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
  }, [id_empresa]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const { name, value, type } = target;
    if (target instanceof HTMLSelectElement && target.multiple) {
      // Multiselect para metodos_pago
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
    setLoading(true);
    setError('');
    try {
      // Enviar metodos_pago como array de UUIDs
      await createCaja(id_empresa, { ...form, saldo_actual: 0.0, metodos_pago: form.metodos_pago });
      navigate(-1);
    } catch {
      setError('Error al crear la caja');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Crear Nueva Caja</h2>
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
