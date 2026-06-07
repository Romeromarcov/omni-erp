import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button } from '@mui/material';
import GroupsOutlined from '@mui/icons-material/GroupsOutlined';
import HourglassBottomOutlined from '@mui/icons-material/HourglassBottomOutlined';
import PaidOutlined from '@mui/icons-material/PaidOutlined';
import BusinessOutlined from '@mui/icons-material/BusinessOutlined';
import { PageContainer, PageHeader, KpiCard, DataTable, StatusChip, type Column } from '../../components/ui';
import {
  fetchSuscripciones,
  fetchPlanes,
  estimarMrr,
  type Suscripcion,
} from '../../services/saasService';
import { fetchEmpresas } from '../../services/empresas';

const DIAS_POR_VENCER = 30;
const ESTADOS_VIGENTES = ['ACTIVA', 'TRIAL'];

function fmtMoney(n: number): string {
  return n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const AdminSaasDashboardPage: React.FC = () => {
  const navigate = useNavigate();

  const { data: suscripciones = [], isLoading: loadingSus, isError: errSus } = useQuery<Suscripcion[], Error>({
    queryKey: ['saas/suscripciones'],
    queryFn: () => fetchSuscripciones(),
  });
  const { data: planes = [] } = useQuery({
    queryKey: ['saas/planes', 'all'],
    queryFn: () => fetchPlanes(true),
  });
  const { data: empresas = [] } = useQuery({
    queryKey: ['empresas', 'visible'],
    queryFn: fetchEmpresas,
  });

  const vigentes = suscripciones.filter((s) => ESTADOS_VIGENTES.includes(s.estado));
  const porVencer = vigentes.filter((s) => s.dias_restantes >= 0 && s.dias_restantes <= DIAS_POR_VENCER);
  const mrr = estimarMrr(suscripciones, planes);

  const columnsPorVencer: Column<Suscripcion>[] = [
    { key: 'plan', header: 'Plan', render: (s) => s.plan_nombre },
    { key: 'estado', header: 'Estado', render: (s) => <StatusChip value={s.estado.toLowerCase()} label={s.estado} /> },
    { key: 'fecha_fin', header: 'Vence', render: (s) => s.fecha_fin },
    {
      key: 'dias',
      header: 'Días restantes',
      align: 'right',
      render: (s) => s.dias_restantes,
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Panel SaaS"
        subtitle="Resumen del negocio: clientes, vencimientos e ingresos recurrentes."
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate('/admin-saas/planes')}>
              Planes
            </Button>
            <Button variant="contained" onClick={() => navigate('/admin-saas/suscripciones')}>
              Suscripciones
            </Button>
          </>
        }
      />

      {errSus && <Alert severity="error" sx={{ mb: 2 }}>No se pudieron cargar las suscripciones.</Alert>}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
          gap: 2,
          mb: 3,
        }}
      >
        <KpiCard
          label="Clientes activos"
          value={loadingSus ? '…' : vigentes.length}
          icon={<GroupsOutlined />}
          tone="success"
          caption="Suscripciones ACTIVA o TRIAL"
        />
        <KpiCard
          label="Por vencer (30 días)"
          value={loadingSus ? '…' : porVencer.length}
          icon={<HourglassBottomOutlined />}
          tone="warning"
          emphasizeError={porVencer.length > 0}
          caption="Vigentes que vencen pronto"
        />
        <KpiCard
          label="MRR estimado"
          value={loadingSus ? '…' : fmtMoney(mrr)}
          icon={<PaidOutlined />}
          tone="brand"
          caption="Ingreso recurrente mensual"
        />
        <KpiCard
          label="Tenants"
          value={empresas.length}
          icon={<BusinessOutlined />}
          tone="tint"
          caption="Empresas registradas"
        />
      </Box>

      <PageHeader
        title="Suscripciones por vencer"
        subtitle={`Vigentes con ${DIAS_POR_VENCER} días o menos para su vencimiento.`}
      />
      <DataTable
        columns={columnsPorVencer}
        rows={porVencer}
        getRowKey={(s) => s.id_suscripcion}
        loading={loadingSus}
        emptyMessage="No hay suscripciones próximas a vencer."
        onRowClick={() => navigate('/admin-saas/suscripciones')}
      />
    </PageContainer>
  );
};

export default AdminSaasDashboardPage;
