import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, FormControlLabel, Switch } from '@mui/material';
import { PageContainer, PageHeader, DataTable, StatusChip, type Column } from '../../components/ui';
import {
  getProveedoresAdmin,
  deactivateProveedor,
  type ConectorProveedor,
} from '../../services/integrationHubService';

const ProveedorIntegracionListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [error, setError] = useState('');

  const { data: proveedores = [], isLoading } = useQuery<ConectorProveedor[], Error>({
    queryKey: ['integration-hub/proveedores-admin', incluirInactivos],
    queryFn: () => getProveedoresAdmin(incluirInactivos),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => deactivateProveedor(id),
    onSuccess: () => {
      setError('');
      queryClient.invalidateQueries({ queryKey: ['integration-hub/proveedores-admin'] });
      // El selector de "Nuevo conector" también consume el catálogo.
      queryClient.invalidateQueries({ queryKey: ['/integration-hub/proveedores/'] });
    },
    onError: (e: Error) => setError(e.message || 'No se pudo desactivar el proveedor.'),
  });

  const handleDeactivate = (p: ConectorProveedor) => {
    if (
      window.confirm(
        `¿Desactivar el proveedor "${p.nombre}"? Dejará de ofrecerse al crear nuevos conectores.`,
      )
    ) {
      deactivateMutation.mutate(p.id_proveedor);
    }
  };

  const columns: Column<ConectorProveedor>[] = [
    { key: 'nombre', header: 'Nombre', render: (p) => p.nombre },
    { key: 'codigo', header: 'Código', render: (p) => p.codigo },
    { key: 'estado', header: 'Estado', render: (p) => <StatusChip value={p.estado} label={p.estado} /> },
    {
      key: 'capacidades',
      header: 'Entidades',
      align: 'right',
      render: (p) => p.capacidades.length,
    },
    { key: 'requiere_url', header: 'URL', align: 'center', render: (p) => <StatusChip value={!!p.requiere_url} /> },
    { key: 'requiere_db', header: 'BD', align: 'center', render: (p) => <StatusChip value={!!p.requiere_db} /> },
    { key: 'activo', header: 'Activo', align: 'center', render: (p) => <StatusChip value={!!p.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => (
        <Box sx={{ display: 'flex', gap: 1 }} onClick={(e) => e.stopPropagation()}>
          <Button
            size="small"
            variant="outlined"
            onClick={() => navigate(`/admin-saas/proveedores/${p.id_proveedor}`)}
          >
            Editar
          </Button>
          {p.activo && (
            <Button
              size="small"
              color="error"
              onClick={() => handleDeactivate(p)}
              disabled={deactivateMutation.isPending}
            >
              Desactivar
            </Button>
          )}
        </Box>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Proveedores de integración"
        subtitle="Catálogo de plataformas externas que tus clientes pueden conectar (Odoo, Google Sheets, etc.)."
        actions={
          <Button variant="contained" onClick={() => navigate('/admin-saas/proveedores/new')}>
            + Nuevo proveedor
          </Button>
        }
      />

      <Alert severity="info" sx={{ mb: 2 }}>
        Un proveedor solo puede <strong>sincronizar</strong> si su conector está implementado en el
        backend (hoy: <code>odoo</code> y <code>google_sheets</code>). Los demás aparecen como
        “Próximamente”.
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={<Switch checked={incluirInactivos} onChange={(e) => setIncluirInactivos(e.target.checked)} />}
          label="Mostrar proveedores inactivos"
        />
      </Box>

      <DataTable
        columns={columns}
        rows={proveedores}
        getRowKey={(p) => p.id_proveedor}
        loading={isLoading}
        emptyMessage="No hay proveedores en el catálogo."
        onRowClick={(p) => navigate(`/admin-saas/proveedores/${p.id_proveedor}`)}
      />
    </PageContainer>
  );
};

export default ProveedorIntegracionListPage;
