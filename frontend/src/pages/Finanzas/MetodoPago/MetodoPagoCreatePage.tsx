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
import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import type { MonedasInfoMetodoPago } from '../../../services/monedasInfoMetodoPago';
import { useParams, useNavigate } from 'react-router-dom';
import { post, get } from '../../../services/api';
import { toList } from '../../../utils/api';
import { findSimilarMetodoPago } from '../../../utils/fuzzyDuplicate';
import { PageContainer, PageHeader } from '../../../components/ui';
import { Button } from '@mui/material';
import { useAuth } from '../../../contexts/AuthContext';
import { useEmpresas } from '../../../hooks/useEmpresas';

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
  const { user } = useAuth();
  const esSuperusuario = user?.es_superusuario_innova ?? false;
  const { data: empresasData = [] } = useEmpresas();
  const empresas = empresasData.map(e => ({ id: e.id_empresa, nombre_comercial: e.nombre_comercial }));

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
  const [monedasInfo] = useState<MonedasInfoMetodoPago>({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });

  type MetodoPagoExistente = {
    id_metodo_pago: string;
    nombre_metodo: string;
    tipo_metodo: string;
    activo: boolean;
    es_generico?: boolean;
    es_publico?: boolean;
    empresa?: string | null;
    monedas?: string[];
  };

  const { data: metodosExistentes = [] } = useQuery<unknown, Error, MetodoPagoExistente[]>({
    queryKey: ['/finanzas/metodos-pago/?limit=1000'],
    queryFn: () => get('/finanzas/metodos-pago/?limit=1000'),
    select: toList,
  });

  const { data: monedasRaw = [] } = useQuery<unknown, Error, MonedaEmpresaActivaApi[]>({
    queryKey: [`/finanzas/monedas-empresa-activas/${form.empresa}/`],
    queryFn: () => fetchMonedasEmpresaActivas(form.empresa),
    select: toList,
    enabled: !!(form.tipo_metodo && form.empresa),
  });

  const monedas = monedasRaw.filter(m => m.activa).map(m => ({ id: m.moneda, nombre: m.moneda_nombre, codigo_iso: m.moneda_codigo_iso }));

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => post('/finanzas/metodos-pago/', payload),
    onSuccess: () => navigate(-1),
    onError: () => setError('Error al crear método de pago'),
  });

  const loading = createMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    // Validación fuzzy de duplicados antes de enviar
    const similar = findSimilarMetodoPago(form, metodosExistentes, 65);
    if (similar) {
      setError(`Ya existe un método de pago similar: "${similar.nombre_metodo}" (${similar.tipo_metodo})`);
      return;
    }
    const payload: Record<string, unknown> = {
      nombre_metodo: form.nombre_metodo,
      tipo_metodo: form.tipo_metodo,
      activo: form.activo,
      referencia_externa: form.referencia_externa || '',
      documento_json: form.documento_json ? JSON.parse(form.documento_json) : null,
      monedas: form.monedas,
      ...(esSuperusuario && {
        es_generico: form.es_generico,
        es_publico: form.es_publico,
        empresa: form.empresa || null,
      })
    };
    createMutation.mutate(payload);
  };

  return (
    <PageContainer>
      <PageHeader
        title="Nuevo Método de Pago"
        actions={<Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>}
      />
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {esSuperusuario && (
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
    </PageContainer>
  );
};

export default MetodoPagoCreatePage;

