import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { get, post, patch } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

export type Moneda = {
  id_moneda: string;
  tipo_moneda: 'fiat' | 'crypto' | 'otro';
  codigo_iso: string;
  nombre: string;
  simbolo: string;
  decimales: number;
  activo: boolean;
  referencia_externa?: string;
  documento_json?: string;
  tipo_operacion?: string;
  fecha_cierre_estimada?: string;
};

type MonedaApiResponse = Moneda[] | { results: Moneda[] };
function isPaginated(data: MonedaApiResponse): data is { results: Moneda[] } {
  return !!data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results);
}

export type MonedaEmpresaActiva = {
  id?: number;
  empresa: string;
  moneda: string;
  activa: boolean;
};

const MonedaListPage: React.FC = () => {
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activas, setActivas] = useState<Record<string, MonedaEmpresaActiva>>({});

  useEffect(() => {
    setLoading(true);
    type MonedaEmpresaActivaApiResponse = MonedaEmpresaActiva[] | { results: MonedaEmpresaActiva[] };
    function isPaginatedActivas(data: MonedaEmpresaActivaApiResponse): data is { results: MonedaEmpresaActiva[] } {
      return !!data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results);
    }
    Promise.all([
      get<MonedaApiResponse>('/finanzas/monedas/'),
      get<MonedaEmpresaActivaApiResponse>('/finanzas/monedas-empresa-activas/')
    ])
      .then(([data, activasDataRaw]) => {
        if (Array.isArray(data)) {
          setMonedas(data);
        } else if (isPaginated(data)) {
          setMonedas(data.results);
        } else {
          setMonedas([]);
        }
        // Permitir que activasData sea array o paginado
        let activasArr: MonedaEmpresaActiva[] = [];
        if (Array.isArray(activasDataRaw)) {
          activasArr = activasDataRaw;
        } else if (isPaginatedActivas(activasDataRaw)) {
          activasArr = activasDataRaw.results;
        }
        const activasMap: Record<string, MonedaEmpresaActiva> = {};
        activasArr.forEach(a => {
          activasMap[a.moneda] = a;
        });
        setActivas(activasMap);
      })
      .catch((err) => {
        let msg = 'Error al cargar monedas';
        if (err instanceof Error) {
          msg = err.message;
        }
        setError(msg);
        // Mostrar en consola para depuración
        console.error('Error al cargar monedas:', err);
      })
      .finally(() => setLoading(false));
  }, []);

  // Definir el tipo global para id_empresa
  interface WindowWithEmpresa extends Window {
    id_empresa?: string;
  }
  const id_empresa = (window as WindowWithEmpresa).id_empresa || '';

  const handleToggle = async (moneda: Moneda) => {
    const actual = activas[moneda.id_moneda];
    const nuevaActivo = !(actual?.activa ?? true);
    setActivas(prev => ({
      ...prev,
      [moneda.id_moneda]: { ...actual, moneda: moneda.id_moneda, empresa: id_empresa, activa: nuevaActivo }
    }));
    try {
      if (actual && actual.id) {
        await patch(`/finanzas/monedas-empresa-activas/${actual.id}/`, { activa: nuevaActivo });
      } else {
        await post('/finanzas/monedas-empresa-activas/', { moneda: moneda.id_moneda, empresa: id_empresa, activa: nuevaActivo });
      }
    } catch {
      setError('No se pudo actualizar el estado de la moneda');
    }
  };

  const filtered = monedas.filter(m =>
    m.codigo_iso.toLowerCase().includes(search.toLowerCase()) ||
    m.nombre.toLowerCase().includes(search.toLowerCase()) ||
    m.simbolo.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Monedas</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 18 }}>
        <input
          placeholder="Buscar..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 180 }}
        />
        <Link to="/finanzas/monedas/new" style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', fontWeight: 600, fontSize: 15, textDecoration: 'none', display: 'inline-block' }}>Nueva Moneda</Link>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : error ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32, fontWeight: 500 }}>{error}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Código ISO</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Símbolo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Uso Empresa</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No hay monedas</td>
                </tr>
              ) : (
                filtered.map(moneda => (
                  <tr key={moneda.id_moneda} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{moneda.codigo_iso}</td>
                    <td style={{ padding: '10px 8px' }}>{moneda.nombre}</td>
                    <td style={{ padding: '10px 8px' }}>{moneda.simbolo}</td>
                    <td style={{ padding: '10px 8px' }}>{moneda.activo ? 'Sí' : 'No'}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={activas[moneda.id_moneda]?.activa ?? true}
                        onChange={() => handleToggle(moneda)}
                        style={{ transform: 'scale(1.2)' }}
                      />
                    </td>
                    <td style={{ padding: '10px 8px' }}>
                      <Link to={`/finanzas/monedas/${moneda.id_moneda}`}>Ver/Editar</Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
};

export default MonedaListPage;
