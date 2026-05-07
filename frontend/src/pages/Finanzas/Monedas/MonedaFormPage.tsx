import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { post, get } from '../../../services/api';
import { findSimilarMoneda } from '../../../utils/fuzzyDuplicate';
import type { Moneda } from './MonedaListPage';
import PageLayout from '../../../components/PageLayout';

const defaultMoneda: Partial<Moneda> = {
  tipo_moneda: 'fiat',
  codigo_iso: '',
  nombre: '',
  simbolo: '',
  decimales: 2,
  activo: true,
  referencia_externa: '',
  documento_json: '',
  tipo_operacion: '',
  fecha_cierre_estimada: '',
};

const MonedaFormPage: React.FC = () => {
  const [moneda, setMoneda] = useState<Partial<Moneda>>(defaultMoneda);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [monedasExistentes, setMonedasExistentes] = useState<Moneda[]>([]);

  useEffect(() => {
    get('/finanzas/monedas/?limit=1000').then((res) => {
      if (Array.isArray(res)) setMonedasExistentes(res);
      else if (res && Array.isArray((res as any).results)) setMonedasExistentes((res as any).results);
      else setMonedasExistentes([]);
    }).catch(() => setMonedasExistentes([]));
  }, []);
  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setMoneda({ ...moneda, [e.target.name]: e.target.value });
  };

  const handleCheck = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMoneda({ ...moneda, [e.target.name]: e.target.checked });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    // Validación fuzzy de duplicados antes de enviar
    const similar = findSimilarMoneda(moneda, monedasExistentes, 65);
    if (similar) {
      setError(`Ya existe una moneda similar: "${similar.nombre}" (${similar.codigo_iso})`);
      return;
    }
    setSaving(true);
    // Formatea la fecha correctamente
    const payload = {
      ...moneda,
      fecha_cierre_estimada: moneda.fecha_cierre_estimada
        ? (typeof moneda.fecha_cierre_estimada === 'string' && moneda.fecha_cierre_estimada.match(/^\d{4}-\d{2}-\d{2}$/)
            ? moneda.fecha_cierre_estimada
            : null)
        : null,
    };
    try {
      await post('/finanzas/monedas/', payload);
      navigate('/finanzas/monedas');
    } catch {
      setError('Error al crear moneda');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Nueva Moneda</h2>
      <form onSubmit={handleSubmit} style={{ background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', padding: 32, display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 400, margin: '0 auto' }}>
        <label>Tipo de Moneda
          <select name="tipo_moneda" value={moneda.tipo_moneda || 'fiat'} onChange={handleChange} required>
            <option value="fiat">Fiat</option>
            <option value="crypto">Cripto</option>
            <option value="otro">Otro</option>
          </select>
        </label>
        <label>Código ISO
          <input
            name="codigo_iso"
            value={moneda.codigo_iso}
            onChange={handleChange}
            required
            maxLength={moneda.tipo_moneda === 'crypto' ? 5 : 3}
          />
        </label>
        <label>Nombre
          <input name="nombre" value={moneda.nombre} onChange={handleChange} required />
        </label>
        <label>Símbolo
          <input name="simbolo" value={moneda.simbolo} onChange={handleChange} required />
        </label>
        <label>Decimales
          <input name="decimales" type="number" value={moneda.decimales} onChange={handleChange} min={0} max={8} required />
        </label>
        <label>Referencia Externa
          <input name="referencia_externa" value={moneda.referencia_externa || ''} onChange={handleChange} />
        </label>
        <label>Documento JSON
          <input name="documento_json" value={moneda.documento_json || ''} onChange={handleChange} />
        </label>
        <label>Tipo Operación
          <input name="tipo_operacion" value={moneda.tipo_operacion || ''} onChange={handleChange} />
        </label>
        <label>Fecha Cierre Estimada
          <input name="fecha_cierre_estimada" type="date" value={moneda.fecha_cierre_estimada || ''} onChange={handleChange} />
        </label>
        <label>
          <input name="activo" type="checkbox" checked={!!moneda.activo} onChange={handleCheck} /> Activo
        </label>
        <button type="submit" disabled={saving} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 15, marginTop: 8 }}>{saving ? 'Guardando...' : 'Crear'}</button>
        {error && <div style={{ color: '#d32f2f', marginTop: 8, textAlign: 'center', fontWeight: 500 }}>{error}</div>}
      </form>
    </PageLayout>
  );
};

export default MonedaFormPage;
