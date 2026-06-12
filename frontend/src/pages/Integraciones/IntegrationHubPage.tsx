import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, CircularProgress, Paper, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import HubOutlined from '@mui/icons-material/HubOutlined';
import SwapHorizOutlined from '@mui/icons-material/SwapHorizOutlined';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import ErrorOutlineOutlined from '@mui/icons-material/ErrorOutlineOutlined';
import {
  getConectores,
  getIntegrationHubStatus,
} from '../../services/integrationHubService';
import { PageContainer, PageHeader, KpiCard } from '../../components/ui';
import ConectorCard from './ConectorCard';
import NuevoConectorModal from './NuevoConectorModal';

const IntegrationHubPage: React.FC = () => {
  const [showModal, setShowModal] = useState(false);

  const { data: conectoresData, isLoading } = useQuery({
    queryKey: ['/integration-hub/instancias/'],
    queryFn: getConectores,
  });

  const { data: status } = useQuery({
    queryKey: ['/integration-hub/status/'],
    queryFn: getIntegrationHubStatus,
    refetchInterval: 30_000,
  });

  const conectores = conectoresData?.results ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Integration Hub"
        subtitle="Conecta Omni ERP con cualquier sistema externo"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setShowModal(true)}>
            Nuevo conector
          </Button>
        }
      />

      {/* Stats */}
      {status?.conectores && status?.jobs_24h && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(auto-fill, minmax(160px, 1fr))' }, gap: 2, mb: 4 }}>
          <KpiCard label="Conectores activos" value={status.conectores.activos} icon={<HubOutlined />} tone="brand" />
          <KpiCard label="Total conectores" value={status.conectores.total} icon={<SwapHorizOutlined />} tone="tint" />
          <KpiCard label="Jobs (24h)" value={status.jobs_24h.total} icon={<SwapHorizOutlined />} tone="ai" />
          <KpiCard label="Completados" value={status.jobs_24h.completados} icon={<CheckCircleOutlined />} tone="success" />
          {status.jobs_24h.fallidos > 0 && (
            <KpiCard label="Fallidos" value={status.jobs_24h.fallidos} icon={<ErrorOutlineOutlined />} tone="error" emphasizeError />
          )}
        </Box>
      )}

      {/* Grid de conectores */}
      {isLoading ? (
        <Box display="flex" justifyContent="center" py={6}><CircularProgress /></Box>
      ) : conectores.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 6, textAlign: 'center', borderStyle: 'dashed' }}>
          <Typography variant="h6" gutterBottom>Sin conectores configurados</Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Conecta tu primera plataforma externa para empezar a sincronizar datos.
          </Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setShowModal(true)}>
            Agregar primer conector
          </Button>
        </Paper>
      ) : (
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 2 }}>
          {conectores.map(c => (
            <ConectorCard key={c.id_conector} conector={c} />
          ))}
        </Box>
      )}

      {showModal && <NuevoConectorModal onClose={() => setShowModal(false)} />}
    </PageContainer>
  );
};

export default IntegrationHubPage;
