import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, patch } from '../../../services/api';
import { toList, toCount, type PaginatedResponse } from '../../../utils/api';
import { Alert, Box, Button, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField } from '@mui/material';
import { PageContainer, PageHeader, StatusChip } from '../../../components/ui';
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
  const esSuperusuario = user?.es_superusuario_omni ?? false;
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
    <PageContainer>
      <PageHeader
        title="Métodos de Pago"
        actions={
          <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/metodos-pago/new`)}>
            + Nuevo método de pago
          </Button>
        }
      />

      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder="Buscar por nombre"
          value={filtro.nombre}
          onChange={e => setFiltro(f => ({ ...f, nombre: e.target.value }))}
          sx={{ minWidth: 180 }}
        />
        <select
          value={filtro.tipo}
          onChange={e => setFiltro(f => ({ ...f, tipo: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', minWidth: 140, height: 40 }}
        >
          {TIPO_METODO.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <select
          value={filtro.visibilidad}
          onChange={e => setFiltro(f => ({ ...f, visibilidad: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', minWidth: 140, height: 40 }}
        >
          <option value="">Todas las visibilidades</option>
          <option value="generico">Genéricos</option>
          <option value="publico">Públicos</option>
          <option value="empresa">Solo de mi empresa</option>
        </select>
        <Button variant="outlined" onClick={resetFiltro}>Limpiar</Button>
      </Box>

      {toggleMutation.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>No se pudo actualizar el estado de uso en empresa</Alert>
      )}

      {loadingMetodos ? (
        <Box sx={{ textAlign: 'center', color: 'text.secondary', py: 4 }}>Cargando...</Box>
      ) : isError ? (
        <Alert severity="error">Error al cargar métodos de pago</Alert>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Nombre</TableCell>
                <TableCell>Tipo</TableCell>
                <TableCell>Visibilidad</TableCell>
                <TableCell align="center">Activo</TableCell>
                <TableCell align="center">Uso Empresa</TableCell>
                <TableCell align="center">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {metodos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">No hay métodos registrados.</TableCell>
                </TableRow>
              ) : metodos.map(m => (
                <TableRow key={m.id_metodo_pago} hover>
                  <TableCell>
                    {m.nombre_metodo}
                    {m.es_generico && <StatusChip value="generico" label="Genérico" colorMap={{ generico: 'primary' }} />}
                    {m.es_publico && <StatusChip value="publico" label="Público" colorMap={{ publico: 'success' }} />}
                  </TableCell>
                  <TableCell>{m.tipo_metodo}</TableCell>
                  <TableCell>
                    {m.es_generico ? 'Genérico' : m.es_publico ? 'Público' : 'Empresa'}
                    {esSuperusuario && m.empresa && (
                      <Box component="span" sx={{ ml: 1, color: 'text.secondary', fontSize: 12 }}>
                        ({empresas.find(e => e.id === m.empresa)?.nombre_comercial ?? m.empresa})
                      </Box>
                    )}
                  </TableCell>
                  <TableCell align="center"><StatusChip value={m.activo} /></TableCell>
                  <TableCell align="center">
                    <Switch
                      size="small"
                      checked={activas[m.id_metodo_pago]?.activa ?? true}
                      onChange={() => handleToggleEmpresa(m)}
                      disabled={toggleMutation.isPending}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Button size="small" variant="outlined" onClick={() => navigate(`/metodos-pago/${m.id_metodo_pago}`)}>
                      Ver/Editar
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', mt: 3, gap: 1 }}>
        <Button variant="outlined" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Anterior</Button>
        <Box sx={{ fontWeight: 500, px: 1 }}>Página {page} de {totalPages}</Box>
        <Button variant="outlined" onClick={() => setPage(p => (p < totalPages ? p + 1 : p))} disabled={page >= totalPages}>Siguiente</Button>
        <Box sx={{ ml: 2 }}>
          <select
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
            style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid rgba(0,0,0,0.23)' }}
          >
            {[10, 20, 50, 100].map(sz => <option key={sz} value={sz}>{sz}</option>)}
          </select>
        </Box>
      </Box>
    </PageContainer>
  );
};

export default MetodoPagoListPage;
