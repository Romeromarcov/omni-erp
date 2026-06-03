import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getCajas } from '../../../services/cajaService';
import { toList } from '../../../utils/api';
import { Alert, Box, Button, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField } from '@mui/material';
import { PageContainer, PageHeader, StatusChip } from '../../../components/ui';

type Caja = {
  id_caja: string;
  nombre: string;
  sucursal_nombre: string;
  moneda_codigo_iso: string;
  saldo_actual: number;
  activa: boolean;
  tipo_caja: string;
  tipo_caja_display?: string;
};

type CajaApiResponse = Caja[] | { results: Caja[] };

const CajaListPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<{ sucursal: string; moneda: string; activo: string }>({ sucursal: '', moneda: '', activo: '' });

  const { data: data = [], isLoading } = useQuery<CajaApiResponse, Error, Caja[]>({
    queryKey: ['/finanzas/cajas/', id_empresa, filters],
    queryFn: () => getCajas(id_empresa!, filters) as Promise<CajaApiResponse>,
    select: toList,
    enabled: !!id_empresa,
  });

  if (!id_empresa) {
    return (
      <PageContainer>
        <PageHeader title="Gestión de Cajas" />
        <Alert severity="warning">Seleccione una empresa para ver sus cajas.</Alert>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Gestión de Cajas"
        actions={
          <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/cajas/new`)}>
            Nueva Caja
          </Button>
        }
      />
      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <TextField size="small" placeholder="Sucursal" value={filters.sucursal} onChange={e => setFilters(f => ({ ...f, sucursal: e.target.value }))} />
        <TextField size="small" placeholder="Moneda" value={filters.moneda} onChange={e => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <select
          value={filters.activo}
          onChange={e => setFilters(f => ({ ...f, activo: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', minWidth: 120, height: 40 }}
        >
          <option value="">Todos</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </select>
      </Box>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Nombre Caja</TableCell>
              <TableCell>Tipo</TableCell>
              <TableCell>Sucursal</TableCell>
              <TableCell>Moneda</TableCell>
              <TableCell align="right">Saldo Actual</TableCell>
              <TableCell align="center">Activo</TableCell>
              <TableCell align="center">Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={7} align="center">Cargando...</TableCell></TableRow>
            ) : data.length === 0 ? (
              <TableRow><TableCell colSpan={7} align="center">No hay cajas registradas.</TableCell></TableRow>
            ) : data.map((row) => (
              <TableRow key={row.id_caja} hover>
                <TableCell>{row.nombre}</TableCell>
                <TableCell>{row.tipo_caja_display || row.tipo_caja}</TableCell>
                <TableCell>{row.sucursal_nombre}</TableCell>
                <TableCell>{row.moneda_codigo_iso}</TableCell>
                <TableCell align="right">{Number(row.saldo_actual).toFixed(2)}</TableCell>
                <TableCell align="center">
                  <StatusChip value={row.activa} />
                </TableCell>
                <TableCell align="center">
                  <Stack direction="row" spacing={1} justifyContent="center">
                    <Button size="small" variant="outlined" onClick={() => navigate(`/cajas/${row.id_caja}`)}>Ver Detalle</Button>
                    <Button size="small" variant="outlined" onClick={() => navigate(`/cajas/${row.id_caja}/movimientos-caja-banco`)}>Movimientos</Button>
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </PageContainer>
  );
};

export default CajaListPage;
