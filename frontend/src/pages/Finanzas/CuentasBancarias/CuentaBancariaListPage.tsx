import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getCuentasBancarias } from '../../../services/cuentaBancariaService';
import { toList } from '../../../utils/api';
import { Alert, Box, Button, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField } from '@mui/material';
import { PageContainer, PageHeader, StatusChip } from '../../../components/ui';

type CuentaBancaria = {
  id_cuenta_bancaria: string;
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: string;
  moneda_codigo_iso: string;
  saldo_actual: number;
  activo: boolean;
};

const CuentaBancariaListPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<{ banco: string; moneda: string; activo: string }>({ banco: '', moneda: '', activo: '' });

  const { data = [], isLoading: loading } = useQuery<unknown, Error, CuentaBancaria[]>({
    queryKey: [`/finanzas/cuentas-bancarias/${id_empresa}/`, filters],
    queryFn: () => getCuentasBancarias(id_empresa!, filters),
    select: toList,
    enabled: !!id_empresa,
  });

  if (!id_empresa) {
    return (
      <PageContainer>
        <PageHeader title="Gestión de Cuentas Bancarias" />
        <Alert severity="warning">Seleccione una empresa para ver sus cuentas bancarias.</Alert>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Gestión de Cuentas Bancarias"
        actions={
          <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/cuentas-bancarias/new`)}>
            Nueva Cuenta
          </Button>
        }
      />
      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <TextField size="small" placeholder="Banco" value={filters.banco} onChange={e => setFilters(f => ({ ...f, banco: e.target.value }))} />
        <TextField size="small" placeholder="Moneda" value={filters.moneda} onChange={e => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <select
          value={filters.activo}
          onChange={e => setFilters(f => ({ ...f, activo: e.target.value }))}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.23)', minWidth: 120, height: 40 }}
        >
          <option value="">Todos</option>
          <option value="true">Activas</option>
          <option value="false">Inactivas</option>
        </select>
      </Box>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Banco</TableCell>
              <TableCell>Número de Cuenta</TableCell>
              <TableCell>Tipo</TableCell>
              <TableCell>Moneda</TableCell>
              <TableCell align="right">Saldo Actual</TableCell>
              <TableCell align="center">Activa</TableCell>
              <TableCell align="center">Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={7} align="center">Cargando...</TableCell></TableRow>
            ) : data.length === 0 ? (
              <TableRow><TableCell colSpan={7} align="center">No hay cuentas bancarias registradas.</TableCell></TableRow>
            ) : data.map((row) => (
              <TableRow key={row.id_cuenta_bancaria} hover>
                <TableCell>{row.nombre_banco}</TableCell>
                <TableCell>{row.numero_cuenta}</TableCell>
                <TableCell>{row.tipo_cuenta}</TableCell>
                <TableCell>{row.moneda_codigo_iso}</TableCell>
                <TableCell align="right">{Number(row.saldo_actual).toFixed(2)}</TableCell>
                <TableCell align="center"><StatusChip value={row.activo} /></TableCell>
                <TableCell align="center">
                  <Stack direction="row" spacing={1} justifyContent="center">
                    <Button size="small" variant="outlined" onClick={() => navigate(`/cuentas-bancarias/${row.id_cuenta_bancaria}`)}>Ver Detalle</Button>
                    <Button size="small" variant="outlined" onClick={() => navigate(`/cuentas-bancarias/${row.id_cuenta_bancaria}/movimientos`)}>Movimientos</Button>
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

export default CuentaBancariaListPage;
