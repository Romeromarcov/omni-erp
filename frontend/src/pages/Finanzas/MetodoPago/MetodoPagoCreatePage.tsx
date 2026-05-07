interface MonedaEmpresaActivaApi {
  id: string;
  empresa: string;
  empresa_nombre: string;
  moneda: string;
  moneda_codigo_iso: string;
  moneda_nombre: string;
  activa: boolean;
  es_base: boolean;
}
import React, { useState, useEffect } from 'react';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import type { MonedasInfoMetodoPago } from '../../../services/monedasInfoMetodoPago';
import { useParams, useNavigate } from 'react-router-dom';
import { post, get } from '../../../services/api';
import { findSimilarMetodoPago } from '../../../utils/fuzzyDuplicate';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

const TIPO_METODO = [
  { value: 'EFECTIVO', label: 'Efectivo' },
  { value: 'ELECTRONICO', label: 'Electrónico' },
  { value: 'TARJETA', label: 'Tarjeta' },
  { value: 'CHEQUE', label: 'Cheque' },
  { value: 'CREDITO', label: 'Crédito' },
  { value: 'OTRO', label: 'Otro' },
];

const MetodoPagoCreatePage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  // Simulación de usuario y empresas (reemplaza por tu contexto real)
  // Ajusta estos tipos según tu contexto real de usuario y empresa
  const user = (window as unknown as { user?: { es_superusuario_innova: boolean } }).user || { es_superusuario_innova: false };
  const empresas = (window as unknown as { empresas?: { id: string; nombre_comercial: string }[] }).empresas || [];

  const [form, setForm] = useState({
    nombre_metodo: '',
    tipo_metodo: '',
    activo: true,
    referencia_externa: '',
    documento_json: '',
    es_generico: false,
    es_publico: false,
    empresa: id_empresa || '',
    monedas: [] as string[],
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [metodosExistentes, setMetodosExistentes] = useState<Array<{
    id_metodo_pago: string;
    nombre_metodo: string;
    tipo_metodo: string;
    activo: boolean;
    es_generico?: boolean;
    es_publico?: boolean;
    empresa?: string | null;
    monedas?: string[];
  }>>([]);
  const [monedas, setMonedas] = useState<Array<{ id: string; nombre: string; codigo_iso: string }>>([]);
  const [monedasInfo, setMonedasInfo] = useState<MonedasInfoMetodoPago>({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });
  // Cargar monedas activas de la empresa
  // Cargar monedas sugeridas/obligatorias según tipo_metodo y empresa
  useEffect(() => {
    if (form.tipo_metodo && form.empresa) {
      // Solo cargar las monedas activas de la empresa
      fetchMonedasEmpresaActivas(form.empresa).then((data) => {
        let monedasActivas: MonedaEmpresaActivaApi[] = [];
        if (Array.isArray(data)) {
          monedasActivas = (data as MonedaEmpresaActivaApi[]).filter(m => m.activa);
        } else if (data && Array.isArray((data as { results?: unknown }).results)) {
          monedasActivas = (data as { results: MonedaEmpresaActivaApi[] }).results.filter(m => m.activa);
        }
        setMonedas(monedasActivas.map(m => ({
          id: m.moneda,
          nombre: m.moneda_nombre,
          codigo_iso: m.moneda_codigo_iso
        })));
      }).catch(() => {
        setMonedas([]);
      });
      setMonedasInfo({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });
    } else {
      setMonedas([]);
      setMonedasInfo({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });
    }
  }, [form.tipo_metodo, form.empresa]);
  useEffect(() => {
    get('/finanzas/metodos-pago/?limit=1000').then((res: unknown) => {
      if (Array.isArray(res)) setMetodosExistentes(res);
      else if (res && typeof res === 'object' && 'results' in res && Array.isArray((res as { results: unknown }).results)) {
        setMetodosExistentes((res as { results: Array<{
          id_metodo_pago: string;
          nombre_metodo: string;
          tipo_metodo: string;
          activo: boolean;
          es_generico?: boolean;
          es_publico?: boolean;
          empresa?: string | null;
          monedas?: string[];
        }> }).results);
      } else setMetodosExistentes([]);
    }).catch(() => setMetodosExistentes([]));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    // Validación fuzzy de duplicados antes de enviar
    const similar = findSimilarMetodoPago(form, metodosExistentes, 65);
    if (similar) {
      setError(`Ya existe un método de pago similar: "${similar.nombre_metodo}" (${similar.tipo_metodo})`);
      return;
    }
    setLoading(true);
    try {
      const payload = {
        nombre_metodo: form.nombre_metodo,
        tipo_metodo: form.tipo_metodo,
        activo: form.activo,
        referencia_externa: form.referencia_externa || '',
        documento_json: form.documento_json ? JSON.parse(form.documento_json) : null,
        monedas: form.monedas,
        ...(user.es_superusuario_innova && {
          es_generico: form.es_generico,
          es_publico: form.es_publico,
          empresa: form.empresa || null,
        })
      };
      await post('/finanzas/metodos-pago/', payload);
      navigate(-1);
    } catch {
      setError('Error al crear método de pago');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout maxWidth={500}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Nuevo Método de Pago</h2>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button variant="contained" color="secondary" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </div>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {user?.es_superusuario_innova && (
          <>
            <label>
              <input
                type="checkbox"
                checked={form.es_generico}
                onChange={e => setForm(f => ({ ...f, es_generico: e.target.checked }))}
              /> Método genérico (global)
            </label>
            <label>
              <input
                type="checkbox"
                checked={form.es_publico}
                onChange={e => setForm(f => ({ ...f, es_publico: e.target.checked }))}
              /> Método público (visible para todas las empresas)
            </label>
            <label>
              Empresa:
              <select
                value={form.empresa}
                onChange={e => setForm(f => ({ ...f, empresa: e.target.value }))}
              >
                <option value="">Seleccione empresa</option>
                {empresas.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.nombre_comercial}</option>
                ))}
              </select>
            </label>
          </>
        )}
        <label style={{ fontWeight: 500 }}>Nombre
          <input required value={form.nombre_metodo} onChange={e => setForm(f => ({ ...f, nombre_metodo: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
        </label>
        <label style={{ fontWeight: 500 }}>Tipo
          <select required value={form.tipo_metodo} onChange={e => setForm(f => ({ ...f, tipo_metodo: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
            <option value="">Seleccione tipo</option>
            {TIPO_METODO.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label style={{ fontWeight: 500 }}>Activo
          <select value={form.activo ? '1' : '0'} onChange={e => setForm(f => ({ ...f, activo: e.target.value === '1' }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
            <option value="1">Sí</option>
            <option value="0">No</option>
          </select>
        </label>
        <label style={{ fontWeight: 500 }}>Referencia externa
          <input value={form.referencia_externa} onChange={e => setForm(f => ({ ...f, referencia_externa: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
        </label>
        <label style={{ fontWeight: 500 }}>Documento JSON
          <textarea value={form.documento_json} onChange={e => setForm(f => ({ ...f, documento_json: e.target.value }))} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4, minHeight: 60, fontFamily: 'monospace' }} placeholder="{ }" />
        </label>
        <label style={{ fontWeight: 500 }}>Monedas asociadas
          <select
            multiple
            value={form.monedas}
            onChange={e => {
              const options = Array.from(e.target.selectedOptions).map(opt => opt.value);
              // No permitir desasociar obligatorias
              const nuevas = Array.from(new Set([...monedasInfo.obligatorias, ...options]));
              setForm(f => ({ ...f, monedas: nuevas }));
            }}
            style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4, minHeight: 60 }}
          >
            {monedas.map((m, idx) => (
              <option
                key={m.id + '-' + idx}
                value={m.id}
                disabled={monedasInfo.obligatorias.includes(m.id)}
                style={{
                  fontWeight: monedasInfo.obligatorias.includes(m.id) ? 'bold' : undefined,
                  color: monedasInfo.sugeridas.includes(m.id) ? '#1976d2' : undefined
                }}
              >
                {m.nombre} ({m.codigo_iso})
                {monedasInfo.obligatorias.includes(m.id) ? ' (Obligatoria)' : monedasInfo.sugeridas.includes(m.id) ? ' (Sugerida)' : ''}
              </option>
            ))}
          </select>
          <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>
            Puede seleccionar varias monedas manteniendo presionada Ctrl o Shift.<br />
            <span style={{ color: '#1976d2' }}>Las monedas sugeridas aparecen en azul.</span> <span style={{ fontWeight: 'bold' }}>(Obligatoria)</span> no puede ser desasociada.
          </div>
        </label>
        {/* Sugerencia de duplicado eliminada, ya no se reutiliza */}
        {error && <div style={{ color: 'red', marginTop: 8 }}>{error}</div>}
        <Button type="submit" variant="contained" disabled={loading} style={{ marginTop: 8 }}>
          {loading ? 'Registrando...' : 'Registrar'}
        </Button>
      </form>
      {/* Modal de reutilización eliminado */}
    </PageLayout>
  );
};

export default MetodoPagoCreatePage;

