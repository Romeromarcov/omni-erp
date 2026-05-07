import React, { useEffect, useState } from 'react';
import { fetchMonedasInfoMetodoPago } from '../../../services/monedasInfoMetodoPago';
import type { MonedasInfoMetodoPago } from '../../../services/monedasInfoMetodoPago';
import { useParams, useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
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
  const [metodo, setMetodo] = useState<MetodoPagoDetail | null>(null);
  const [editMonedas, setEditMonedas] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [metodoEmpresaActivaId, setMetodoEmpresaActivaId] = useState<string | null>(null);

  // Monedas y monedasInfo para el selector avanzado
  const [monedas, setMonedas] = useState<{ id: string; nombre: string; codigo_iso: string }[]>([]);
  const [monedasInfo, setMonedasInfo] = useState<MonedasInfoMetodoPago>({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });
  useEffect(() => {
    // Siempre cargar todas las monedas disponibles para el selector
    import('../../../services/monedas').then(({ fetchMonedas }) => {
      fetchMonedas().then((todas) => {
        setMonedas(todas.map(m => ({ id: m.id_moneda, nombre: m.nombre, codigo_iso: m.codigo_iso })));
      });
    });
    // Si hay método y empresa, cargar info extra
    if (metodo && metodo.id_metodo_pago && metodo.empresa && metodo.tipo_metodo) {
      fetchMonedasInfoMetodoPago(metodo.id_metodo_pago, metodo.empresa).then(info => {
        setMonedasInfo(info);
      }).catch(() => {
        setMonedasInfo({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });
      });
    } else {
      setMonedasInfo({ asociadas: [], activas_empresa: [], sugeridas: [], obligatorias: [] });
    }
  }, [metodo]);

  // Obtener el id de la relación MetodoPagoEmpresaActiva para el método actual
  useEffect(() => {
    if (metodo && metodo.id_metodo_pago && metodo.empresa) {
      // Tipar correctamente la respuesta
      fetchMetodosPagoEmpresaActivos(metodo.empresa as string).then((data) => {
        type MetodoPagoEmpresaActiva = { id: string; metodo_pago: string };
        let rel: MetodoPagoEmpresaActiva | undefined;
        if (Array.isArray(data)) {
          rel = data.find((m: MetodoPagoEmpresaActiva) => m.metodo_pago === metodo.id_metodo_pago);
        } else if (data && Array.isArray((data as { results?: unknown }).results)) {
          rel = (data as { results: MetodoPagoEmpresaActiva[] }).results.find((m) => m.metodo_pago === metodo.id_metodo_pago);
        }
        setMetodoEmpresaActivaId(rel?.id || null);
      });
    } else {
      setMetodoEmpresaActivaId(null);
    }
  }, [metodo]);

  // (Si necesitas validación fuzzy, puedes restaurar aquí el hook de metodosExistentes)
  useEffect(() => {
    get(`/finanzas/metodos-pago/${id_metodo_pago}/`)
      .then((data) => setMetodo(data as MetodoPagoDetail))
      .catch(() => setError('Error al cargar método de pago'))
      .finally(() => setLoading(false));
  }, [id_metodo_pago]);

  // Guardar solo monedas asociadas para la empresa activa
  const handleUpdateMonedas = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!metodo || !metodoEmpresaActivaId) return;
    setError('');
    setLoading(true);
    try {
      await updateMonedasMetodoPagoEmpresaActiva(metodoEmpresaActivaId, metodo.monedas || []);
      setEditMonedas(false);
    } catch {
      setError('Error al actualizar monedas asociadas');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;
  if (error) return <PageLayout><div style={{ textAlign: 'center', color: 'red', padding: 32 }}>{error}</div></PageLayout>;
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
              value={metodo.monedas || []}
              onChange={e => {
                const options = Array.from(e.target.selectedOptions).map(opt => opt.value);
                setMetodo({ ...metodo, monedas: options });
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
