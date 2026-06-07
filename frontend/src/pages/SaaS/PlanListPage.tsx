import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, FormControlLabel, Switch } from '@mui/material';
import { PageContainer, PageHeader, DataTable, StatusChip, type Column } from '../../components/ui';
import { fetchPlanes, deactivatePlan, type Plan } from '../../services/saasService';

function fmtMoney(v: string): string {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : v;
}

function fmtLimite(v: number): string {
  return v === 0 ? 'Ilimitado' : String(v);
}

const PlanListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [error, setError] = useState('');

  const { data: planes = [], isLoading } = useQuery<Plan[], Error>({
    queryKey: ['saas/planes', incluirInactivos],
    queryFn: () => fetchPlanes(incluirInactivos),
  });

  const deactivateMutation = useMutation({
    mutationFn: (idPlan: string) => deactivatePlan(idPlan),
    onSuccess: () => {
      setError('');
      queryClient.invalidateQueries({ queryKey: ['saas/planes'] });
    },
    onError: (e: Error) => setError(e.message || 'No se pudo desactivar el plan.'),
  });

  const handleDeactivate = (plan: Plan) => {
    if (window.confirm(`¿Desactivar el plan "${plan.nombre}"? Dejará de ofrecerse a nuevos clientes.`)) {
      deactivateMutation.mutate(plan.id_plan);
    }
  };

  const columns: Column<Plan>[] = [
    { key: 'nombre', header: 'Nombre', render: (p) => p.nombre },
    { key: 'nivel', header: 'Nivel', render: (p) => <StatusChip value={p.nivel} label={p.nivel} /> },
    { key: 'precio_mensual', header: 'Mensual', align: 'right', render: (p) => fmtMoney(p.precio_mensual) },
    { key: 'precio_anual', header: 'Anual', align: 'right', render: (p) => fmtMoney(p.precio_anual) },
    { key: 'max_usuarios', header: 'Usuarios', align: 'right', render: (p) => fmtLimite(p.max_usuarios) },
    { key: 'max_empresas', header: 'Empresas', align: 'right', render: (p) => fmtLimite(p.max_empresas) },
    { key: 'ia', header: 'IA', align: 'center', render: (p) => <StatusChip value={p.permite_ia} /> },
    { key: 'api', header: 'API', align: 'center', render: (p) => <StatusChip value={p.permite_api} /> },
    { key: 'activo', header: 'Activo', align: 'center', render: (p) => <StatusChip value={p.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => (
        <Box sx={{ display: 'flex', gap: 1 }} onClick={(e) => e.stopPropagation()}>
          <Button size="small" variant="outlined" onClick={() => navigate(`/admin-saas/planes/${p.id_plan}`)}>
            Editar
          </Button>
          {p.activo && (
            <Button size="small" color="error" onClick={() => handleDeactivate(p)} disabled={deactivateMutation.isPending}>
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
        title="Planes"
        subtitle="Catálogo de planes ofrecidos a los clientes del SaaS."
        actions={
          <Button variant="contained" onClick={() => navigate('/admin-saas/planes/new')}>
            + Nuevo plan
          </Button>
        }
      />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box sx={{ mb: 2 }}>
        <FormControlLabel
          control={<Switch checked={incluirInactivos} onChange={(e) => setIncluirInactivos(e.target.checked)} />}
          label="Mostrar planes inactivos"
        />
      </Box>

      <DataTable
        columns={columns}
        rows={planes}
        getRowKey={(p) => p.id_plan}
        loading={isLoading}
        emptyMessage="No hay planes registrados."
        onRowClick={(p) => navigate(`/admin-saas/planes/${p.id_plan}`)}
      />
    </PageContainer>
  );
};

export default PlanListPage;
