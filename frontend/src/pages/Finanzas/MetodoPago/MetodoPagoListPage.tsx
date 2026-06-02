import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, patch } from '../../../services/api';
import { toList, toCount, type PaginatedResponse } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';
import { useAuth } from '../../../contexts/AuthContext';
import { useEmpresas } from '../../../hooks/useEmpresas';

// ── Tipos ────────────────────────────────────────────────────────────────────

interface MetodoPago {
  id_metodo_pago: string;
  nombre_metodo: string;
  tipo_metodo: string;
  activo: boolean;
  es_generico?: boolean;
  es_publico?: boolean;
  empresa?: string | null;
}

interface MetodoPagoEmpresaActiva {
  id?: number;
  empresa: string;
  metodo_pago: string;
  activa: boolean;
}

type MetodoPagoApiResponse = MetodoPago[] | PaginatedResponse<MetodoPago>;
type MetodoPagoActivaApiResponse = MetodoPagoEmpresaActiva[] | PaginatedResponse<MetodoPagoEmpresaActiva>;

interface Filtro {
  nombre: string;
  tipo: string;
  visibilidad: string;
}

const TIPO_METODO = [
  { value: '', label: 'Todos' },
  { value: 'TRANSFERENCIA', label: 'Transferencia' },
  { value: 'TARJETA', label: 'Tarjeta' },
  { value: 'EFECTIVO', label: 'Efectivo' },
  { value: 'CHEQUE', label: 'Cheque' },
  { value: 'OTRO', label: 'Otro' },
];

// ── Componente ───────────────────────────────────────────────────────────────

const MetodoPagoListPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { user } = useAuth();
  const esSuperusuario = user?.es_superusuario_innova ?? false;
  const { data: empresasData = [] } = useEmpresas();
  const empresas = empresasData.map(e => ({ id: e.id_empresa, nombre_comercial: e.nombre_comercial }));

  const [filtro, setFiltro] = useState<Filtro>({ nombre: '', tipo: '', visibilidad: '' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // Construye la URL con los filtros y paginación actuales
  const buildUrl = () => {
    let url = `/finanzas/metodos-pago/?id_empresa=${id_empresa}&limit=${pageSize}&offset=${(page - 1) * pageSize}`;
    if (filtro.nombre) url += `&nombre_metodo=${encodeURIComponent(filtro.nombre)}`;
    if (filtro.tipo) url += `&tipo_metodo=${filtro.tipo}`;
    if (filtro.visibilidad === 'generico') url += `&es_generico=true`;
    if (filtro.visibilidad === 'publico') url += `&es_publico=true`;
    if (filtro.visibilidad === 'empresa') url += `&empresa=${id_empresa}`;
    return url;
  };

  // ── Query: lista de métodos (paginada + filtros) ──────────────────────────
  const {
    data: metodosData,
    isLoading: loadingMetodos,
    isError,
  } = useQuery<MetodoPagoApiResponse, Error>({
    queryKey: ['finanzas/metodos-pago', id_empresa, filtro, page, pageSize],
    queryFn: () => get<MetodoPagoApiResponse>(buildUrl()),
    enabled: !!id_empresa,
  });

  const metodos: MetodoPago[] = toList(metodosData ?? []);
  const count = toCount(metodosData ?? []);

  // ── Query: activaciones por empresa ──────────────────────────────────────
  const activasQueryKey = ['finanzas/metodos-pago-empresa-activas', id_empresa];

  const { data: activasArr = [] } = useQuery<MetodoPagoActivaApiResponse, Error, MetodoPagoEmpresaActiva[]>({
    queryKey: activasQueryKey,
    queryFn: () =>
      get<MetodoPagoActivaApiResponse>(`/finanzas/metodos-pago-empresa-activas/?empresa=${id_empresa}`),
    select: toList,
    enabled: !!id_empresa,
  });

  // Mapa id_metodo_pago → registro activa para O(1) lookup
  const activas: Record<string, MetodoPagoEmpresaActiva> = {};
  activasArr.forEach(a => {
    activas[a.metodo_pago] = a;
  });

  // ── Mutation: toggle activa/inactiva ─────────────────────────────────────
  const toggleMutation = useMutation<
    MetodoPagoEmpresaActiva,
    Error,
    { metodo: MetodoPago; nuevaActivo: boolean }
  >({
    mutationFn: ({ metodo, nuevaActivo }) => {
      const actual = activas[metodo.id_metodo_pago];
      if (actual?.id) {
        return patch<MetodoPagoEmpresaActiva>(
          `/finanzas/metodos-pago-empresa-activas/${actual.id}/`,
          { activa: nuevaActivo },
        );
      }
      return post<MetodoPagoEmpresaActiva>('/finanzas/metodos-pago-empresa-activas/', {
        metodo_pago: metodo.id_metodo_pago,
        empresa: id_empresa,
        activa: nuevaActivo,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: activasQueryKey }),
  });

  const handleToggleEmpresa = (metodo: MetodoPago) => {
    const actual = activas[metodo.id_metodo_pago];
    const nuevaActivo = !(actual?.activa ?? true);
    toggleMutation.mutate({ metodo, nuevaActivo });
  };

  const resetFiltro = () => {
    setFiltro({ nombre: '', tipo: '', visibilidad: '' });
    setPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  return (
    <PageLayout maxWidth={900}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Métodos de Pago</h2>

      {/* Filtros */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
        <input
          placeholder="Buscar por nombre"
          value={filtro.nombre}
          onChange={e => setFiltro(f => ({ ...f, nombre: e.target.value }))}
          style={{
            padding: 10,
            borderRadius: 8,
            border: '1px solid #cfd8dc',
            minWidth: 180,
            background: '#f6fafd',
          }}
        />
        <select
          value={filtro.tipo}
          onChange={e => setFiltro(f => ({ ...f, tipo: e.target.value }))}
          style={{
            padding: 10,
            borderRadius: 8,
            border: '1px solid #cfd8dc',
            minWidth: 140,
            background: '#f6fafd',
          }}
        >
          {TIPO_METODO.map(t => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <select
          value={filtro.visibilidad}
          onChange={e => setFiltro(f => ({ ...f, visibilidad: e.target.value }))}
          style={{
            padding: 10,
            borderRadius: 8,
            border: '1px solid #cfd8dc',
            minWidth: 140,
            background: '#f6fafd',
          }}
        >
          <option value="">Todas las visibilidades</option>
          <option value="generico">Genéricos</option>
          <option value="publico">Públicos</option>
          <option value="empresa">Solo de mi empresa</option>
        </select>
        <Button variant="contained" color="secondary" onClick={resetFiltro}>
          Limpiar
        </Button>
        <div style={{ flex: 1 }} />
        <Button
          variant="contained"
          onClick={() => navigate(`/empresas/${id_empresa}/metodos-pago/new`)}
        >
          + Nuevo método de pago
        </Button>
      </div>

      {toggleMutation.isError && (
        <div style={{ color: '#d32f2f', marginBottom: 12, fontWeight: 500 }}>
          No se pudo actualizar el estado de uso en empresa
        </div>
      )}

      {/* Tabla */}
      {loadingMetodos ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : isError ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32 }}>
          Error al cargar métodos de pago
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              background: '#f6fafd',
              borderRadius: 12,
              boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            }}
          >
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Tipo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>
                  Visibilidad
                </th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>
                  Uso Empresa
                </th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {metodos.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#888' }}>
                    No hay métodos registrados.
                  </td>
                </tr>
              ) : (
                metodos.map(m => (
                  <tr
                    key={m.id_metodo_pago}
                    style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}
                  >
                    <td style={{ padding: '10px 8px' }}>
                      {m.nombre_metodo}
                      {m.es_generico && (
                        <span
                          style={{ marginLeft: 6, color: '#1976d2', fontWeight: 600, fontSize: 12 }}
                        >
                          [Genérico]
                        </span>
                      )}
                      {m.es_publico && (
                        <span
                          style={{ marginLeft: 6, color: '#43a047', fontWeight: 600, fontSize: 12 }}
                        >
                          [Público]
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '10px 8px' }}>{m.tipo_metodo}</td>
                    <td style={{ padding: '10px 8px' }}>
                      {m.es_generico ? 'Genérico' : m.es_publico ? 'Público' : 'Empresa'}
                      {esSuperusuario && m.empresa && (
                        <span style={{ marginLeft: 6, color: '#888', fontSize: 12 }}>
                          ({empresas.find(e => e.id === m.empresa)?.nombre_comercial ?? m.empresa})
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                      {m.activo ? 'Sí' : 'No'}
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={activas[m.id_metodo_pago]?.activa ?? true}
                        onChange={() => handleToggleEmpresa(m)}
                        disabled={toggleMutation.isPending}
                        style={{ transform: 'scale(1.2)' }}
                      />
                    </td>
                    <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                      <Button
                        variant="contained"
                        onClick={() => navigate(`/metodos-pago/${m.id_metodo_pago}`)}
                      >
                        Ver/Editar
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginación */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          marginTop: 24,
          gap: 8,
        }}
      >
        <Button
          variant="contained"
          color="secondary"
          onClick={() => setPage(p => Math.max(1, p - 1))}
          disabled={page === 1}
        >
          Anterior
        </Button>
        <span style={{ fontWeight: 500 }}>
          Página {page} de {totalPages}
        </span>
        <Button
          variant="contained"
          color="secondary"
          onClick={() => setPage(p => (p < totalPages ? p + 1 : p))}
          disabled={page >= totalPages}
        >
          Siguiente
        </Button>
        <span style={{ marginLeft: 16 }}>
          <label style={{ fontWeight: 500 }}>
            Tamaño:
            <select
              value={pageSize}
              onChange={e => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              style={{ marginLeft: 4, padding: 6, borderRadius: 6, border: '1px solid #cfd8dc' }}
            >
              {[10, 20, 50, 100].map(sz => (
                <option key={sz} value={sz}>
                  {sz}
                </option>
              ))}
            </select>
          </label>
        </span>
      </div>
    </PageLayout>
  );
};

export default MetodoPagoListPage;
