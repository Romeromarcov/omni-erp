import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, patch } from '../../../services/api';
import { getEmpresaId } from '../../../utils/empresa';
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

export type MonedaEmpresaActiva = {
  id?: number;
  empresa: string;
  moneda: string;
  activa: boolean;
};

type MonedaEmpresaActivaApiResponse = MonedaEmpresaActiva[] | { results: MonedaEmpresaActiva[] };

function toList<T>(raw: T[] | { results: T[] }): T[] {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === 'object' && 'results' in raw && Array.isArray(raw.results)) return raw.results;
  return [];
}

const MonedaListPage: React.FC = () => {
  const [search, setSearch] = useState('');
  const [toggleError, setToggleError] = useState('');
  const queryClientHook = useQueryClient();

  const id_empresa = getEmpresaId() || '';

  // ── Queries paralelas ──────────────────────────────────────────
  const { data: monedas = [], isLoading: loadingMonedas, isError: errorMonedas } =
    useQuery<MonedaApiResponse, Error, Moneda[]>({
      queryKey: ['/finanzas/monedas/'],
      queryFn: () => get<MonedaApiResponse>('/finanzas/monedas/'),
      select: toList,
    });

  const { data: activasArr = [], isLoading: loadingActivas } =
    useQuery<MonedaEmpresaActivaApiResponse, Error, MonedaEmpresaActiva[]>({
      queryKey: ['/finanzas/monedas-empresa-activas/'],
      queryFn: () => get<MonedaEmpresaActivaApiResponse>('/finanzas/monedas-empresa-activas/'),
      select: toList,
    });

  // Mapa moneda.id_moneda → MonedaEmpresaActiva para O(1) lookup
  const activas: Record<string, MonedaEmpresaActiva> = {};
  activasArr.forEach(a => { activas[a.moneda] = a; });

  // ── Mutation: toggle activa/inactiva ───────────────────────────
  const toggleMutation = useMutation<
    MonedaEmpresaActiva,
    Error,
    { moneda: Moneda; nuevaActivo: boolean }
  >({
    mutationFn: ({ moneda, nuevaActivo }) => {
      const actual = activas[moneda.id_moneda];
      if (actual?.id) {
        return patch<MonedaEmpresaActiva>(
          `/finanzas/monedas-empresa-activas/${actual.id}/`,
          { activa: nuevaActivo }
        );
      }
      return post<MonedaEmpresaActiva>(
        '/finanzas/monedas-empresa-activas/',
        { moneda: moneda.id_moneda, empresa: id_empresa, activa: nuevaActivo }
      );
    },
    onSuccess: () => {
      setToggleError('');
      queryClientHook.invalidateQueries({ queryKey: ['/finanzas/monedas-empresa-activas/'] });
    },
    onError: () => setToggleError('No se pudo actualizar el estado de la moneda'),
  });

  const handleToggle = (moneda: Moneda) => {
    const actual = activas[moneda.id_moneda];
    const nuevaActivo = !(actual?.activa ?? true);
    toggleMutation.mutate({ moneda, nuevaActivo });
  };

  const isLoading = loadingMonedas || loadingActivas;

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
        <Link
          to="/finanzas/monedas/new"
          style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', fontWeight: 600, fontSize: 15, textDecoration: 'none', display: 'inline-block' }}
        >
          Nueva Moneda
        </Link>
      </div>

      {toggleError && (
        <div style={{ color: '#d32f2f', marginBottom: 12, fontWeight: 500 }}>{toggleError}</div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : errorMonedas ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32, fontWeight: 500 }}>Error al cargar monedas</div>
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
                        disabled={toggleMutation.isPending}
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
