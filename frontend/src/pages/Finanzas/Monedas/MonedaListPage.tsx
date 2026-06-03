import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, post, patch } from '../../../services/api';
import { getEmpresaId } from '../../../utils/empresa';
import { finanzasKeys } from '../../../lib/queryKeys';
import { Alert, Box, Button, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField } from '@mui/material';
import { PageContainer, PageHeader, StatusChip } from '../../../components/ui';

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
      queryKey: finanzasKeys.monedas.all(),
      queryFn: () => get<MonedaApiResponse>('/finanzas/monedas/'),
      select: toList,
    });

  const { data: activasArr = [], isLoading: loadingActivas } =
    useQuery<MonedaEmpresaActivaApiResponse, Error, MonedaEmpresaActiva[]>({
      queryKey: finanzasKeys.monedas.empresaActivas(),
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
      queryClientHook.invalidateQueries({ queryKey: finanzasKeys.monedas.empresaActivas() });
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
    <PageContainer>
      <PageHeader
        title="Monedas"
        actions={
          <Button variant="contained" component={Link} to="/finanzas/monedas/new">
            Nueva Moneda
          </Button>
        }
      />
      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <TextField
          size="small"
          placeholder="Buscar..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          sx={{ minWidth: 180 }}
        />
      </Box>

      {toggleError && <Alert severity="error" sx={{ mb: 2 }}>{toggleError}</Alert>}

      {isLoading ? (
        <Box sx={{ textAlign: 'center', color: 'text.secondary', py: 4 }}>Cargando...</Box>
      ) : errorMonedas ? (
        <Alert severity="error">Error al cargar monedas</Alert>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Código ISO</TableCell>
                <TableCell>Nombre</TableCell>
                <TableCell>Símbolo</TableCell>
                <TableCell align="center">Activo</TableCell>
                <TableCell align="center">Uso Empresa</TableCell>
                <TableCell align="center">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">No hay monedas</TableCell>
                </TableRow>
              ) : filtered.map(moneda => (
                <TableRow key={moneda.id_moneda} hover>
                  <TableCell>{moneda.codigo_iso}</TableCell>
                  <TableCell>{moneda.nombre}</TableCell>
                  <TableCell>{moneda.simbolo}</TableCell>
                  <TableCell align="center"><StatusChip value={moneda.activo} /></TableCell>
                  <TableCell align="center">
                    <Switch
                      size="small"
                      checked={activas[moneda.id_moneda]?.activa ?? true}
                      onChange={() => handleToggle(moneda)}
                      disabled={toggleMutation.isPending}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Button size="small" variant="outlined" component={Link} to={`/finanzas/monedas/${moneda.id_moneda}`}>
                      Ver/Editar
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </PageContainer>
  );
};

export default MonedaListPage;
