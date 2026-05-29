import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getTransaccionesFinancieras, exportTransaccionesFinancieras } from '../../../services/transaccionFinancieraService';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import { Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const tipoTransaccionOptions = [
  { value: '', label: 'Todos' },
  { value: 'ingreso', label: 'Ingreso' },
  { value: 'egreso', label: 'Egreso' },
];

type TransaccionFinanciera = {
  id: string;
  fecha_hora_transaccion: string;
  tipo_transaccion: string;
  monto_transaccion: number;
  id_moneda_transaccion__codigo_iso: string;
  id_moneda_base__codigo_iso?: string;
  monto_base_empresa: number;
  id_moneda_pais_empresa__codigo_iso?: string;
  monto_moneda_pais?: number;
  id_metodo_pago__nombre_metodo: string;
  referencia_pago: string;
  descripcion: string;
  id_usuario_registro__username: string;
  empresa_id?: string;
  estado?: string;
  observaciones?: string;
};

const TransaccionFinancieraListPage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ tipo: '', moneda: '', metodo: '', usuario: '', fecha_inicio: '', fecha_fin: '' });

  const empresaIdToUse = id_empresa;

  const { data = [], isLoading: loading } = useQuery<unknown, Error, TransaccionFinanciera[]>({
    queryKey: [`/finanzas/transacciones-financieras/${empresaIdToUse}/`, filters],
    queryFn: () => getTransaccionesFinancieras(empresaIdToUse, filters),
    select: toList,
    enabled: !!empresaIdToUse,
  });

  const columns: Column<TransaccionFinanciera>[] = [
    { key: 'fecha', header: 'Fecha', align: 'center', render: (row) => row.fecha_hora_transaccion },
    { key: 'tipo', header: 'Tipo', align: 'center', render: (row) => row.tipo_transaccion },
    { key: 'monto', header: 'Monto', align: 'right', render: (row) => row.monto_transaccion },
    { key: 'moneda', header: 'Moneda', align: 'center', render: (row) => row.id_moneda_transaccion__codigo_iso },
    { key: 'moneda_base', header: 'Moneda Base', align: 'center', render: (row) => row.id_moneda_base__codigo_iso || '-' },
    { key: 'monto_base', header: 'Monto Base', align: 'right', render: (row) => row.monto_base_empresa },
    { key: 'moneda_pais', header: 'Moneda País', render: (row) => row.id_moneda_pais_empresa__codigo_iso || '-' },
    { key: 'monto_pais', header: 'Monto País', render: (row) => row.monto_moneda_pais !== undefined ? row.monto_moneda_pais : '-' },
    { key: 'metodo', header: 'Método de Pago', render: (row) => row.id_metodo_pago__nombre_metodo },
    { key: 'referencia', header: 'Referencia', render: (row) => row.referencia_pago },
    { key: 'descripcion', header: 'Descripción', render: (row) => row.descripcion },
    { key: 'usuario', header: 'Usuario', render: (row) => row.id_usuario_registro__username },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (row) => (
        <Button size="small" variant="outlined" onClick={() => navigate(`/transacciones-financieras/${row.id}`)}>
          Ver Detalle
        </Button>
      ),
    },
  ];

  if (!empresaIdToUse) {
    return (
      <PageLayout>
        <Box sx={{ textAlign: 'center', mt: 6 }}>
          <Typography variant="h5" mb={1}>Empresa no especificada</Typography>
          <Typography color="text.secondary">Por favor, selecciona una empresa para ver las transacciones financieras.</Typography>
        </Box>
      </PageLayout>
    );
  }

  return (
    <PageContainer>
      <PageHeader title="Transacciones Financieras" />
      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          select
          size="small"
          label="Tipo"
          value={filters.tipo}
          onChange={(e) => setFilters(f => ({ ...f, tipo: e.target.value }))}
          sx={{ minWidth: 140 }}
        >
          {tipoTransaccionOptions.map(opt => (
            <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
          ))}
        </TextField>
        <TextField size="small" placeholder="Moneda" value={filters.moneda} onChange={(e) => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <TextField size="small" placeholder="Método de Pago" value={filters.metodo} onChange={(e) => setFilters(f => ({ ...f, metodo: e.target.value }))} />
        <TextField size="small" placeholder="Usuario" value={filters.usuario} onChange={(e) => setFilters(f => ({ ...f, usuario: e.target.value }))} />
        <TextField size="small" type="date" label="Desde" slotProps={{ inputLabel: { shrink: true } }} value={filters.fecha_inicio} onChange={(e) => setFilters(f => ({ ...f, fecha_inicio: e.target.value }))} />
        <TextField size="small" type="date" label="Hasta" slotProps={{ inputLabel: { shrink: true } }} value={filters.fecha_fin} onChange={(e) => setFilters(f => ({ ...f, fecha_fin: e.target.value }))} />
        <Stack direction="row" spacing={1} sx={{ ml: 'auto' }}>
          <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/transacciones-financieras/new`)}>Nueva Transacción</Button>
          <Button variant="outlined" onClick={() => exportTransaccionesFinancieras(id_empresa, filters)}>Exportar</Button>
        </Stack>
      </Box>
      <DataTable
        columns={columns}
        rows={data}
        getRowKey={(row) => row.id}
        loading={loading}
        emptyMessage="No se encontraron transacciones financieras."
      />
    </PageContainer>
  );
};

export default TransaccionFinancieraListPage;
