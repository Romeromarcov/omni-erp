import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { get, post, patch } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface MetodoPago {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
  activo: boolean;
  es_generico?: boolean;
  es_publico?: boolean;
  empresa?: string | null;
}

type MetodoPagoEmpresaActiva = {
  id?: number;
  empresa: string;
  metodo_pago: string;
  activa: boolean;
};

const TIPO_METODO = [
  { value: '', label: 'Todos' },
  { value: 'TRANSFERENCIA', label: 'Transferencia' },
  { value: 'TARJETA', label: 'Tarjeta' },
  { value: 'EFECTIVO', label: 'Efectivo' },
  { value: 'CHEQUE', label: 'Cheque' },
  { value: 'OTRO', label: 'Otro' },
];

const MetodoPagoListPage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  // Simulación de usuario y empresas (ajusta según tu contexto real)
  type User = { es_superusuario_innova: boolean };
  type Empresa = { id: string; nombre_comercial: string };
  const user: User = (window as unknown as { user?: User }).user || { es_superusuario_innova: false };
  const empresas: Empresa[] = (window as unknown as { empresas?: Empresa[] }).empresas || [];
  const [metodos, setMetodos] = useState<MetodoPago[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filtro, setFiltro] = useState({ nombre: '', tipo: '', visibilidad: '' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [count, setCount] = useState(0);
  const [activas, setActivas] = useState<Record<string, MetodoPagoEmpresaActiva>>({});

  useEffect(() => {
    setLoading(true);
    type MetodoPagoEmpresaActivaApiResponse = MetodoPagoEmpresaActiva[] | { results: MetodoPagoEmpresaActiva[] };
    function isPaginatedActivas(data: MetodoPagoEmpresaActivaApiResponse): data is { results: MetodoPagoEmpresaActiva[] } {
      return !!data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results);
    }
    let url = `/finanzas/metodos-pago/?id_empresa=${id_empresa}&limit=${pageSize}&offset=${(page-1)*pageSize}`;
    if (filtro.nombre) url += `&nombre_metodo=${encodeURIComponent(filtro.nombre)}`;
    if (filtro.tipo) url += `&tipo_metodo=${filtro.tipo}`;
    if (filtro.visibilidad === 'generico') url += `&es_generico=true`;
    if (filtro.visibilidad === 'publico') url += `&es_publico=true`;
    if (filtro.visibilidad === 'empresa') url += `&empresa=${id_empresa}`;
    Promise.all([
      get(url),
      get<MetodoPagoEmpresaActivaApiResponse>(`/finanzas/metodos-pago-empresa-activas/?empresa=${id_empresa}`)
    ])
      .then(([res, activasDataRaw]) => {
        type Paginated = { results: MetodoPago[]; count: number };
        function isPaginated(data: unknown): data is Paginated {
          return !!data && typeof data === 'object' && Array.isArray((data as Paginated).results);
        }
        if (Array.isArray(res)) {
          setMetodos(res);
          setCount(res.length);
        } else if (isPaginated(res)) {
          setMetodos(res.results);
          setCount(res.count);
        } else {
          setMetodos([]);
          setCount(0);
        }
        // Activaciones empresa
        let activasArr: MetodoPagoEmpresaActiva[] = [];
        if (Array.isArray(activasDataRaw)) {
          activasArr = activasDataRaw;
        } else if (isPaginatedActivas(activasDataRaw)) {
          activasArr = activasDataRaw.results;
        }
        const activasMap: Record<string, MetodoPagoEmpresaActiva> = {};
        activasArr.forEach(a => {
          activasMap[a.metodo_pago] = a;
        });
        setActivas(activasMap);
      })
      .catch(() => setError('Error al cargar métodos de pago'))
      .finally(() => setLoading(false));
  }, [id_empresa, filtro, page, pageSize]);

  // Activar/desactivar método de pago para la empresa actual
  const handleToggleEmpresa = async (metodo: MetodoPago) => {
    const actual = activas[metodo.id_metodo_pago];
    const nuevaActivo = !(actual?.activa ?? true);
    setActivas(prev => ({
      ...prev,
      [metodo.id_metodo_pago]: { ...actual, metodo_pago: metodo.id_metodo_pago, empresa: id_empresa as string, activa: nuevaActivo }
    }));
    try {
      if (actual && actual.id) {
        await patch(`/finanzas/metodos-pago-empresa-activas/${actual.id}/`, { activa: nuevaActivo });
      } else {
        await post('/finanzas/metodos-pago-empresa-activas/', { metodo_pago: metodo.id_metodo_pago, empresa: id_empresa, activa: nuevaActivo });
      }
    } catch {
      setError('No se pudo actualizar el estado de uso en empresa');
    }
  };

  return (
    <PageLayout maxWidth={900}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Métodos de Pago</h2>
      <div style={{ display: 'flex', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
        <input
          placeholder="Buscar por nombre"
          value={filtro.nombre}
          onChange={e => setFiltro(f => ({ ...f, nombre: e.target.value }))}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', minWidth: 180, background: '#f6fafd' }}
        />
        <select
          value={filtro.tipo}
          onChange={e => setFiltro(f => ({ ...f, tipo: e.target.value }))}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', minWidth: 140, background: '#f6fafd' }}
        >
          {TIPO_METODO.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <select
          value={filtro.visibilidad}
          onChange={e => setFiltro(f => ({ ...f, visibilidad: e.target.value }))}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', minWidth: 140, background: '#f6fafd' }}
        >
          <option value="">Todas las visibilidades</option>
          <option value="generico">Genéricos</option>
          <option value="publico">Públicos</option>
          <option value="empresa">Solo de mi empresa</option>
        </select>
        <Button variant="contained" color="secondary" onClick={() => setFiltro({ nombre: '', tipo: '', visibilidad: '' })}>Limpiar</Button>
        <div style={{ flex: 1 }} />
        <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/metodos-pago/new`)}>
          + Nuevo método de pago
        </Button>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : error ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32 }}>{error}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Tipo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Visibilidad</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Uso Empresa</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {metodos.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No hay métodos registrados.</td>
                </tr>
              ) : (
                metodos.map(m => (
                  <tr key={m.id_metodo_pago} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{m.nombre_metodo}
                      {m.es_generico && <span style={{ marginLeft: 6, color: '#1976d2', fontWeight: 600, fontSize: 12 }}>[Genérico]</span>}
                      {m.es_publico && <span style={{ marginLeft: 6, color: '#43a047', fontWeight: 600, fontSize: 12 }}>[Público]</span>}
                    </td>
                    <td style={{ padding: '10px 8px' }}>{m.tipo_metodo}</td>
                    <td style={{ padding: '10px 8px' }}>{m.es_generico ? 'Genérico' : m.es_publico ? 'Público' : 'Empresa'}
                      {user.es_superusuario_innova && m.empresa && (
                        <span style={{ marginLeft: 6, color: '#888', fontSize: 12 }}>
                          ({empresas.find(e => e.id === m.empresa)?.nombre_comercial || m.empresa})
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>{m.activo ? 'Sí' : 'No'}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={activas[m.id_metodo_pago]?.activa ?? true}
                        onChange={() => handleToggleEmpresa(m)}
                        style={{ transform: 'scale(1.2)' }}
                      />
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                      <Button variant="contained" onClick={() => navigate(`/metodos-pago/${m.id_metodo_pago}`)}>Ver/Editar</Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
      {/* Paginación */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', marginTop: 24, gap: 8 }}>
        <Button variant="contained" color="secondary" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Anterior</Button>
        <span style={{ fontWeight: 500 }}>Página {page} de {Math.max(1, Math.ceil(count / pageSize))}</span>
        <Button variant="contained" color="secondary" onClick={() => setPage(p => (p < Math.ceil(count / pageSize) ? p + 1 : p))} disabled={page >= Math.ceil(count / pageSize)}>Siguiente</Button>
        <span style={{ marginLeft: 16 }}>
          <label style={{ fontWeight: 500 }}>Tamaño:
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ marginLeft: 4, padding: 6, borderRadius: 6, border: '1px solid #cfd8dc' }}>
              {[10, 20, 50, 100].map(sz => <option key={sz} value={sz}>{sz}</option>)}
            </select>
          </label>
        </span>
      </div>
    </PageLayout>
  );
};

export default MetodoPagoListPage;
