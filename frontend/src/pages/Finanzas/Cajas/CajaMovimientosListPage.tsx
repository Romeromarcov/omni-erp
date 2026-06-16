import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getMovimientosCaja } from '../../../services/cajaService';
import { toList } from '../../../utils/api';
import { Box, Button, Stack, TextField, Typography } from '@mui/material';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';
import { downloadCsv } from '../../../utils/csv';

type MovimientoCaja = {
  id_movimiento: string;
  fecha_movimiento: string;
  hora_movimiento: string;
  tipo_movimiento: string;
  monto: number | string;
  id_moneda__codigo_iso?: string;
  moneda_codigo_iso?: string;
  concepto: string;
  referencia: string;
  id_caja__nombre_caja?: string;
  caja_nombre?: string;
  sucursal_nombre?: string;
  empresa_nombre?: string;
  saldo_anterior: number | string;
  saldo_nuevo: number | string;
  id_usuario_registro__username?: string;
  usuario_registro_username?: string;
};

type MovimientoApiResponse = MovimientoCaja[] | { results: MovimientoCaja[] };

const CajaMovimientosListPage: React.FC = () => {
  const { id_caja } = useParams<{ id_caja: string }>();
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ fecha_inicio: '', fecha_fin: '', tipo: '', moneda: '', concepto: '', referencia: '', usuario: '' });

  const { data: data = [], isLoading } = useQuery<MovimientoApiResponse, Error, MovimientoCaja[]>({
    queryKey: ['/finanzas/movimientos-caja/', id_caja, filters],
    queryFn: () => getMovimientosCaja(id_caja!, filters) as Promise<MovimientoApiResponse>,
    select: toList,
    enabled: !!id_caja,
  });

  // Extraer info de la caja si hay datos
  const cajaNombre = data[0]?.caja_nombre || '-';
  const sucursalNombre = data[0]?.sucursal_nombre || '-';
  const empresaNombre = data[0]?.empresa_nombre || '-';

  const columns: Column<MovimientoCaja>[] = [
    { key: 'fecha', header: 'Fecha', render: (row) => row.fecha_movimiento },
    { key: 'hora', header: 'Hora', render: (row) => row.hora_movimiento },
    { key: 'tipo', header: 'Tipo', render: (row) => row.tipo_movimiento },
    { key: 'monto', header: 'Monto', align: 'right', render: (row) => Number(row.monto).toFixed(2) },
    { key: 'moneda', header: 'Moneda', render: (row) => row.moneda_codigo_iso || '-' },
    { key: 'concepto', header: 'Concepto', render: (row) => row.concepto },
    { key: 'referencia', header: 'Referencia', render: (row) => row.referencia },
    { key: 'caja', header: 'Caja', render: (row) => row.caja_nombre || '-' },
    { key: 'saldo_anterior', header: 'Saldo Anterior', align: 'right', render: (row) => Number(row.saldo_anterior).toFixed(2) },
    { key: 'saldo_nuevo', header: 'Saldo Nuevo', align: 'right', render: (row) => Number(row.saldo_nuevo).toFixed(2) },
    { key: 'usuario', header: 'Usuario', render: (row) => row.usuario_registro_username || '-' },
  ];

  // TD-1: exportar el informe de movimientos a CSV. El monto/saldos se exportan
  // como string crudo (no Number()/float) para no perder precisión (R-CODE-4).
  const exportCSV = () => {
    downloadCsv(
      `movimientos_caja_${cajaNombre}.csv`,
      ['Fecha', 'Hora', 'Tipo', 'Monto', 'Moneda', 'Concepto', 'Referencia', 'Caja', 'Saldo Anterior', 'Saldo Nuevo', 'Usuario'],
      data.map((m) => [
        m.fecha_movimiento,
        m.hora_movimiento,
        m.tipo_movimiento,
        String(m.monto),
        m.moneda_codigo_iso || '',
        m.concepto,
        m.referencia,
        m.caja_nombre || '',
        String(m.saldo_anterior),
        String(m.saldo_nuevo),
        m.usuario_registro_username || '',
      ]),
    );
  };

  return (
    <PageContainer>
      <PageHeader
        title="Movimientos de Caja"
        actions={
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={exportCSV} disabled={data.length === 0}>Exportar</Button>
            <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
          </Stack>
        }
      />
      {cajaNombre !== '-' && (
        <Typography variant="body2" color="text.secondary" mb={2}>
          <b>{cajaNombre}</b>
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
        loading={isLoading}
        emptyMessage="No hay movimientos registrados."
      />
    </PageContainer>
  );
};

export default CajaMovimientosListPage;
