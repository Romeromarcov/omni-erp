import React, { useEffect, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchMonedasInfoMetodoPago } from '../../../services/monedasInfoMetodoPago';
import type { MonedasInfoMetodoPago } from '../../../services/monedasInfoMetodoPago';
import { useParams, useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import { updateMonedasMetodoPagoEmpresaActiva, fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { Button } from '@mui/material';


interface MetodoPagoDetail {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
  activo: boolean;
  referencia_externa?: string;
  documento_json?: string;
  es_generico?: boolean;
  es_publico?: boolean;
  empresa?: string | null;
  monedas?: string[];
}


// ...existing code...

const MetodoPagoDetailPage: React.FC = () => {
  const { id_metodo_pago } = useParams();
  const navigate = useNavigate();
  // Simulación de usuario y empresas (ajusta según tu contexto real)
  type User = { es_superusuario_innova: boolean };
  type Empresa = { id: string; nombre_comercial: string };
  const user: User = (window as unknown as { user?: User }).user || { es_superusuario_innova: false };
  const empresas: Empresa[] = React.useMemo(() => (window as unknown as { empresas?: Empresa[] }).empresas || [], []);
  const [editMonedas, setEditMonedas] = useState(false);
  const [error, setError] = useState('');
  const [localMonedas, setLocalMonedas] = useState<string[]>([]);

  const { data: metodo, isLoading: loading } = useQuery<MetodoPagoDetail>({
    queryKey: [`/finanzas/metodos-pago/${id_metodo_pago}/`],
    queryFn: () => get(`/finanzas/metodos-pago/${id_metodo_pago}/`) as Promise<MetodoPagoDetail>,
    enabled: !!id_metodo_pago,
  });

  useEffect(() => {
    if (metodo?.monedas) setLocalMonedas(metodo.monedas);
  }, [metodo]);

  const { data: todasMonedas = [] } = useQuery<{ id_moneda: string; nombre: string; codigo_iso: string }[]>({
    queryKey: ['/finanzas/monedas/'],
    queryFn: async () => {
      const { fetchMonedas } = await import('../../../services/monedas');
      return fetchMonedas();
    },
  });

  const monedas = todasMonedas.map(m => ({ id: m.id_moneda, nombre: m.nombre, codigo_iso: m.codigo_iso }));

  const { data: monedasInfo = { asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] } } = useQuery<MonedasInfoMetodoPago>({
    queryKey: [`/finanzas/monedas-info/${metodo?.id_metodo_pago}/${metodo?.empresa}/`],
    queryFn: () => fetchMonedasInfoMetodoPago(metodo!.id_metodo_pago, metodo!.empresa!),
    enabled: !!(metodo?.id_metodo_pago && metodo?.empresa && metodo?.tipo_metodo),
  });

  const { data: metodoEmpresaActivaId = null } = useQuery<string | null>({
    queryKey: [`/finanzas/metodos-pago-empresa-activos/${metodo?.empresa}/`, metodo?.id_metodo_pago],
    queryFn: async () => {
      type MetodoPagoEmpresaActiva = { id: string; metodo_pago: string };
      const data = await fetchMetodosPagoEmpresaActivos(metodo!.empresa as string);
      const list = toList<MetodoPagoEmpresaActiva>(data as unknown);
      const rel = list.find(m => m.metodo_pago === metodo!.id_metodo_pago);
      return rel?.id || null;
    },
    enabled: !!(metodo?.id_metodo_pago && metodo?.empresa),
  });

  const updateMonedasMutation = useMutation({
    mutationFn: () => updateMonedasMetodoPagoEmpresaActiva(metodoEmpresaActivaId!, localMonedas),
    onSuccess: () => setEditMonedas(false),
    onError: () => setError('Error al actualizar monedas asociadas'),
  });

  // Guardar solo monedas asociadas para la empresa activa
  const handleUpdateMonedas = (e: React.FormEvent) => {
    e.preventDefault();
    if (!metodo || !metodoEmpresaActivaId) return;
    setError('');
    updateMonedasMutation.mutate();
  };

  if (loading) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;
  if (!metodo) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>No encontrado</div></PageLayout>;

  return (
    <PageLayout maxWidth={500}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Detalle de Método de Pago</h2>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button variant="contained" color="secondary" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </div>
      {!editMonedas ? (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div><b>Nombre:</b> {metodo.nombre_metodo}
            {metodo.es_generico && <span style={{ marginLeft: 6, color: '#1976d2', fontWeight: 600, fontSize: 12 }}>[Genérico]</span>}
            {metodo.es_publico && <span style={{ marginLeft: 6, color: '#43a047', fontWeight: 600, fontSize: 12 }}>[Público]</span>}
          </div>
          <div><b>Tipo:</b> {metodo.tipo_metodo}</div>
          <div><b>Visibilidad:</b> {metodo.es_generico ? 'Genérico' : metodo.es_publico ? 'Público' : 'Empresa'}
            {user.es_superusuario_innova && metodo.empresa && (
              <span style={{ marginLeft: 6, color: '#888', fontSize: 12 }}>
                ({empresas.find(e => e.id === metodo.empresa)?.nombre_comercial || metodo.empresa})
              </span>
            )}
          </div>
          <div><b>Activo:</b> {metodo.activo ? 'Sí' : 'No'}</div>
          <div><b>Monedas asociadas:</b> {
            Array.isArray(metodo.monedas) && metodo.monedas.length > 0
              ? monedas.length > 0
                ? metodo.monedas.map(id => {
                    const m = monedas.find(x => x.id === id);
                    return m ? `${m.nombre} (${m.codigo_iso})` : id;
                  }).join(', ')
                : <span style={{ color: '#888' }}>Cargando monedas...</span>
              : <span style={{ color: '#888' }}>-</span>
          }
            <Button variant="contained" onClick={() => setEditMonedas(true)} style={{ marginLeft: 12, fontSize: 13, padding: '2px 12px' }}>Editar monedas</Button>
          </div>
          <div><b>Referencia externa:</b> {metodo.referencia_externa || '-'}</div>
          <div><b>Documento JSON:</b> <pre style={{ background: '#f6fafd', borderRadius: 8, padding: 8, fontSize: 13 }}>{metodo.documento_json || '-'}</pre></div>
        </div>
      ) : (
        <form onSubmit={handleUpdateMonedas} style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontWeight: 500 }}>Monedas asociadas
            <select
              multiple
              value={localMonedas}
              onChange={e => {
                const options = Array.from(e.target.selectedOptions).map(opt => opt.value);
                setLocalMonedas(options);
              }}
              style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4, minHeight: 60 }}
            >
              {monedas.map(m => (
                <option
                  key={m.id}
                  value={m.id}
                  style={{
                    fontWeight: monedasInfo.obligatorias.includes(m.id) ? 'bold' : undefined,
                    color: monedasInfo.sugeridas.includes(m.id) ? '#1976d2' : undefined
                  }}
                >
                  {m.nombre} ({m.codigo_iso})
                  {monedasInfo.obligatorias.includes(m.id) ? ' (Sugerida)' : monedasInfo.sugeridas.includes(m.id) ? ' (Sugerida)' : ''}
                </option>
              ))}
            </select>
            <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>
              Puede seleccionar varias monedas manteniendo presionada Ctrl o Shift.<br />
              <span style={{ color: '#1976d2' }}>Las monedas sugeridas aparecen en azul.</span>
            </div>
          </label>
          {error && <div style={{ color: 'red', marginTop: 8 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 12, marginTop: 8, justifyContent: 'flex-end' }}>
            <Button type="submit" variant="contained" disabled={loading}>{loading ? 'Actualizando...' : 'Actualizar'}</Button>
            <Button type="button" variant="contained" color="secondary" onClick={() => setEditMonedas(false)}>Cancelar</Button>
          </div>
        </form>
      )}
    </PageLayout>
  );
};

export default MetodoPagoDetailPage;
