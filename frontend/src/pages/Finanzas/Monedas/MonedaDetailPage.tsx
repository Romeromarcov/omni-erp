import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { get, put } from '../../../services/api';
import { findSimilarMoneda } from '../../../utils/fuzzyDuplicate';
import type { Moneda } from './MonedaListPage';
import PageLayout from '../../../components/PageLayout';

const MonedaDetailPage: React.FC = () => {
  const { id_moneda } = useParams<{ id_moneda: string }>();
  const navigate = useNavigate();
  const [moneda, setMoneda] = useState<Moneda | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [monedasExistentes, setMonedasExistentes] = useState<Moneda[]>([]);
  // Cargar todas las monedas para validación fuzzy (excepto la actual)
  useEffect(() => {
    get('/finanzas/monedas/?limit=1000').then((res) => {
      if (Array.isArray(res)) setMonedasExistentes(res);
      else if (res && Array.isArray((res as any).results)) setMonedasExistentes((res as any).results);
      else setMonedasExistentes([]);
    }).catch(() => setMonedasExistentes([]));
  }, []);

  useEffect(() => {
    if (id_moneda) {
      get<Moneda>(`/finanzas/monedas/${id_moneda}/`)
        .then(setMoneda)
        .catch(() => setError('No se pudo cargar la moneda'));
    }
  }, [id_moneda]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (!moneda) return;
    setMoneda({ ...moneda, [e.target.name]: e.target.value });
  };

  const handleCheck = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!moneda) return;
    setMoneda({ ...moneda, [e.target.name]: e.target.checked });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!moneda) return;
    setError('');
    // Validación fuzzy de duplicados antes de enviar (excluyendo la moneda actual)
    const otras = monedasExistentes.filter(m => m.id_moneda !== moneda.id_moneda);
    const similar = findSimilarMoneda(moneda, otras, 65);
    if (similar) {
      setError(`Ya existe una moneda similar: "${similar.nombre}" (${similar.codigo_iso})`);
      return;
    }
    setSaving(true);
    // Prepara el payload para cumplir con los tipos del modelo
    type MonedaPayload = Partial<Omit<Moneda, 'referencia_externa' | 'tipo_operacion' | 'fecha_cierre_estimada'> & {
      referencia_externa: string | null;
      tipo_operacion: string | null;
      fecha_cierre_estimada: string | null;
    }>;
    const payload: MonedaPayload = {
      ...moneda,
      decimales: Number(moneda.decimales),
      fecha_cierre_estimada: moneda.fecha_cierre_estimada && typeof moneda.fecha_cierre_estimada === 'string' && moneda.fecha_cierre_estimada.match(/^\d{4}-\d{2}-\d{2}$/)
        ? moneda.fecha_cierre_estimada
        : null,
      documento_json: (() => {
        if (!moneda.documento_json || moneda.documento_json === '') return null;
        try {
          return typeof moneda.documento_json === 'string' ? JSON.parse(moneda.documento_json) : moneda.documento_json;
        } catch {
          return null;
        }
      })(),
      referencia_externa: moneda.referencia_externa !== '' ? moneda.referencia_externa : null,
      tipo_operacion: moneda.tipo_operacion !== '' ? moneda.tipo_operacion : null,
    };
    try {
      await put(`/finanzas/monedas/${id_moneda}/`, payload);
      navigate('/finanzas/monedas');
    } catch (err) {
      console.error(err);
      let backendMsg = '';
      let foundGenericError = false;
      if (
        typeof err === 'object' && err !== null &&
        'response' in err &&
        typeof (err as { response?: { data?: unknown } }).response === 'object' &&
        (err as { response?: { data?: unknown } }).response !== null &&
        'data' in (err as { response: { data?: unknown } }).response!
      ) {
        const data = (err as { response: { data: unknown } }).response.data;
        // Buscar mensaje de moneda genérica en cualquier formato
        const checkMsg = (val: unknown): boolean => {
          if (!val) return false;
          if (typeof val === 'string') return val.toLowerCase().includes('no puede modificar una moneda genérica');
          if (typeof val === 'object') {
            return Object.values(val).some(checkMsg);
          }
          return false;
        };
        foundGenericError = checkMsg(data);
        backendMsg = typeof data === 'string' ? data : JSON.stringify(data);
      }
      if (foundGenericError) {
        setError('No es posible modificar las monedas generales del sistema.');
      } else {
        setError(backendMsg || 'Error al actualizar moneda');
      }
    } finally {
      setSaving(false);
    }
  };

  if (!moneda) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Detalle de Moneda</h2>
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
        <button type="submit" disabled={saving} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 15, marginTop: 8 }}>{saving ? 'Guardando...' : 'Actualizar'}</button>
        {error && <div style={{ color: '#d32f2f', marginTop: 8, textAlign: 'center', fontWeight: 500 }}>{error}</div>}
      </form>
    </PageLayout>
  );
};

export default MonedaDetailPage;
