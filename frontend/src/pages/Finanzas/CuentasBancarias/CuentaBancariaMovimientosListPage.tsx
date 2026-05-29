import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getMovimientosCuentaBancaria } from '../../../services/cuentaBancariaService';
import { toList } from '../../../utils/api';
import { Box, Button, Stack, TextField, Typography } from '@mui/material';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';

// Ajusta los campos según el serializer de movimientos de cuenta bancaria
interface MovimientoCuentaBancaria {
  id_movimiento: string;
  fecha_movimiento: string;
  hora_movimiento: string;
  tipo_movimiento: string;
  monto: number | string;
  moneda_codigo_iso?: string;
  concepto: string;
  referencia: string;
  cuenta_bancaria_nombre?: string;
  sucursal_nombre?: string;
  empresa_nombre?: string;
  saldo_anterior: number | string;
  saldo_nuevo: number | string;
  usuario_registro_username?: string;
}

const CuentaBancariaMovimientosListPage: React.FC = () => {
  const { id_cuenta } = useParams<{ id_cuenta: string }>();
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ fecha_inicio: '', fecha_fin: '', tipo: '', moneda: '', concepto: '', referencia: '', usuario: '' });

  const { data = [], isLoading: loading } = useQuery<unknown, Error, MovimientoCuentaBancaria[]>({
    queryKey: [`/finanzas/movimientos-cuenta-bancaria/${id_cuenta}/`, filters],
    queryFn: () => getMovimientosCuentaBancaria(id_cuenta!, filters),
    select: toList,
    enabled: !!id_cuenta,
  });

  // Extraer info de la cuenta si hay datos
  const cuentaNombre = data[0]?.cuenta_bancaria_nombre || '-';
  const sucursalNombre = data[0]?.sucursal_nombre || '-';
  const empresaNombre = data[0]?.empresa_nombre || '-';

  const columns: Column<MovimientoCuentaBancaria>[] = [
    { key: 'fecha', header: 'Fecha', render: (row) => row.fecha_movimiento },
    { key: 'hora', header: 'Hora', render: (row) => row.hora_movimiento },
    { key: 'tipo', header: 'Tipo', render: (row) => row.tipo_movimiento },
    { key: 'monto', header: 'Monto', align: 'right', render: (row) => Number(row.monto).toFixed(2) },
    { key: 'moneda', header: 'Moneda', render: (row) => row.moneda_codigo_iso || '-' },
    { key: 'concepto', header: 'Concepto', render: (row) => row.concepto },
    { key: 'referencia', header: 'Referencia', render: (row) => row.referencia },
    { key: 'cuenta', header: 'Cuenta Bancaria', render: (row) => row.cuenta_bancaria_nombre || '-' },
    { key: 'saldo_anterior', header: 'Saldo Anterior', align: 'right', render: (row) => Number(row.saldo_anterior).toFixed(2) },
    { key: 'saldo_nuevo', header: 'Saldo Nuevo', align: 'right', render: (row) => Number(row.saldo_nuevo).toFixed(2) },
    { key: 'usuario', header: 'Usuario', render: (row) => row.usuario_registro_username || '-' },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Movimientos de Cuenta Bancaria"
        actions={
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={() => { /* TODO: exportar informe */ }}>Exportar</Button>
            <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
          </Stack>
        }
      />
      {cuentaNombre !== '-' && (
        <Typography variant="body2" color="text.secondary" mb={2}>
          <b>{cuentaNombre}</b>
          {sucursalNombre !== '-' && <> &nbsp;| Sucursal: <b>{sucursalNombre}</b></>}
          {empresaNombre !== '-' && <> &nbsp;| Empresa: <b>{empresaNombre}</b></>}
        </Typography>
      )}
      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <TextField size="small" type="date" label="Desde" slotProps={{ inputLabel: { shrink: true } }} value={filters.fecha_inicio} onChange={e => setFilters(f => ({ ...f, fecha_inicio: e.target.value }))} />
        <TextField size="small" type="date" label="Hasta" slotProps={{ inputLabel: { shrink: true } }} value={filters.fecha_fin} onChange={e => setFilters(f => ({ ...f, fecha_fin: e.target.value }))} />
        <TextField size="small" placeholder="Tipo" value={filters.tipo} onChange={e => setFilters(f => ({ ...f, tipo: e.target.value }))} />
        <TextField size="small" placeholder="Moneda" value={filters.moneda} onChange={e => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <TextField size="small" placeholder="Concepto" value={filters.concepto} onChange={e => setFilters(f => ({ ...f, concepto: e.target.value }))} />
        <TextField size="small" placeholder="Referencia" value={filters.referencia} onChange={e => setFilters(f => ({ ...f, referencia: e.target.value }))} />
        <TextField size="small" placeholder="Usuario" value={filters.usuario} onChange={e => setFilters(f => ({ ...f, usuario: e.target.value }))} />
        <Button variant="outlined" onClick={() => setFilters({ fecha_inicio: '', fecha_fin: '', tipo: '', moneda: '', concepto: '', referencia: '', usuario: '' })}>Limpiar</Button>
      </Box>
      <DataTable
        columns={columns}
        rows={data}
        getRowKey={(row) => row.id_movimiento}
        loading={loading}
        emptyMessage="No hay movimientos registrados."
      />
    </PageContainer>
  );
};

export default CuentaBancariaMovimientosListPage;
