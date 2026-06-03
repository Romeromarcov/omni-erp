
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
interface TasaOficialBCV {
  fecha_tasa: string;
  valor_tasa: string;
}
import { useParams, useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
import { toList, toCount } from '../../../utils/api';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { Alert, Box, Button, Card, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { PageContainer, PageHeader } from '../../../components/ui';

interface TasaCambio {
  id_tasa_cambio: string;
  fecha_tasa: string;
  id_moneda_origen: string;
  id_moneda_origen__codigo_iso?: string;
  id_moneda_destino: string;
  id_moneda_destino__codigo_iso?: string;
  tipo_tasa: string;
  valor_tasa: string;
  id_usuario_registro__username?: string;
  moneda_origen_nombre?: string;
  moneda_destino_nombre?: string;
  usuario_registro_username?: string;
}

const TasaCambioListPage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  const [filtros, setFiltros] = useState({ moneda_origen: '', moneda_destino: '', fecha: '' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const { data: tasaOficial, isLoading: loadingTasaOficial, isError: errorTasaOficial } = useQuery<TasaOficialBCV>({
    queryKey: ['/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES'],
    queryFn: () => get('/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES') as Promise<TasaOficialBCV>,
    retry: false,
  });

  const { data: monedas = [] } = useQuery<Moneda[], Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/'],
    queryFn: () => fetchMonedas(),
  });

  const tasasUrl = (() => {
    let url = `/finanzas/tasas-cambio/?id_empresa=${id_empresa}&limit=${pageSize}&offset=${(page-1)*pageSize}&ordering=-fecha_tasa`;
    if (filtros.moneda_origen) url += `&id_moneda_origen=${filtros.moneda_origen}`;
    if (filtros.moneda_destino) url += `&id_moneda_destino=${filtros.moneda_destino}`;
    if (filtros.fecha) url += `&fecha_tasa=${filtros.fecha}`;
    return url;
  })();

  const { data: tasasRaw, isLoading: loading, isError } = useQuery({
    queryKey: [tasasUrl],
    queryFn: () => get(tasasUrl),
    enabled: !!id_empresa,
  });

  const tasas = toList<TasaCambio>(tasasRaw as unknown);
  const count = toCount(tasasRaw as unknown);
  const error = isError ? 'Error al cargar tasas de cambio' : '';

  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  return (
    <PageContainer>
      {/* Tasa oficial BCV destacada */}
      <Card sx={{ p: 2.5, mb: 3, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
        {loadingTasaOficial ? (
          <Typography color="text.secondary">Cargando tasa oficial BCV...</Typography>
        ) : tasaOficial ? (
          <>
            <Typography fontWeight={600} color="primary">
              Tasa Oficial BCV USD/VES hoy ({tasaOficial.fecha_tasa}):
            </Typography>
            <Typography fontWeight={700} color="success.main" variant="h6">
              {Number(tasaOficial.valor_tasa).toLocaleString('es-VE', { minimumFractionDigits: 4 })}
            </Typography>
          </>
        ) : (
          <Typography color="error.main" fontWeight={500}>{String(errorTasaOficial ?? 'No disponible')}</Typography>
        )}
      </Card>

      <PageHeader
        title="Tasas de Cambio"
        actions={
          <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/tasas-cambio/new`)}>
            + Nueva tasa de cambio
          </Button>
        }
      />

      <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
        <select
          value={filtros.moneda_origen}
          onChange={e => setFiltros(f => ({ ...f, moneda_origen: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', minWidth: 140, height: 40 }}
        >
          <option value="">Moneda Origen</option>
          {monedas.map(m => (
            <option key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</option>
          ))}
        </select>
        <select
          value={filtros.moneda_destino}
          onChange={e => setFiltros(f => ({ ...f, moneda_destino: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', minWidth: 140, height: 40 }}
        >
          <option value="">Moneda Destino</option>
          {monedas.map(m => (
            <option key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</option>
          ))}
        </select>
        <input
          type="date"
          value={filtros.fecha}
          onChange={e => setFiltros(f => ({ ...f, fecha: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', height: 40 }}
        />
        <Button variant="outlined" onClick={() => setFiltros({ moneda_origen: '', moneda_destino: '', fecha: '' })}>
          Limpiar
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ textAlign: 'center', color: 'text.secondary', py: 4 }}>Cargando...</Box>
      ) : error ? (
        <Alert severity="error">{error}</Alert>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Fecha</TableCell>
                <TableCell>Moneda Origen</TableCell>
                <TableCell>Moneda Destino</TableCell>
                <TableCell>Tipo Tasa</TableCell>
                <TableCell align="right">Valor</TableCell>
                <TableCell>Usuario</TableCell>
                <TableCell align="center">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tasas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center">No hay tasas registradas.</TableCell>
                </TableRow>
              ) : tasas.map(tc => (
                <TableRow key={tc.id_tasa_cambio} hover>
                  <TableCell>{tc.fecha_tasa}</TableCell>
                  <TableCell>{tc.moneda_origen_nombre || tc.id_moneda_origen__codigo_iso || tc.id_moneda_origen}</TableCell>
                  <TableCell>{tc.moneda_destino_nombre || tc.id_moneda_destino__codigo_iso || tc.id_moneda_destino}</TableCell>
                  <TableCell>{tc.tipo_tasa}</TableCell>
                  <TableCell align="right">{tc.valor_tasa}</TableCell>
                  <TableCell>{tc.usuario_registro_username || tc.id_usuario_registro__username || ''}</TableCell>
                  <TableCell align="center">
                    <Button size="small" variant="outlined" onClick={() => navigate(`/tasas-cambio/${tc.id_tasa_cambio}`)}>Ver / Editar</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Stack direction="row" justifyContent="center" alignItems="center" spacing={1} mt={3}>
        <Button variant="outlined" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Anterior</Button>
        <Box sx={{ fontWeight: 500 }}>Página {page} de {totalPages}</Box>
        <Button variant="outlined" onClick={() => setPage(p => (p < totalPages ? p + 1 : p))} disabled={page >= totalPages}>Siguiente</Button>
        <Box sx={{ ml: 2 }}>
          <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid rgba(0,0,0,0.23)' }}>
            {[10, 20, 50, 100].map(sz => <option key={sz} value={sz}>{sz}</option>)}
          </select>
        </Box>
      </Stack>
    </PageContainer>
  );
};

export default TasaCambioListPage;
