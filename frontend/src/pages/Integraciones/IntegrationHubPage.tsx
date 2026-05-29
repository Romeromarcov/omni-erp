import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Card, CardContent, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import {
  getConectores,
  getIntegrationHubStatus,
} from '../../services/integrationHubService';
import { PageContainer, PageHeader } from '../../components/ui';
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

  const stat = (label: string, value: number | string, color = 'text.primary') => (
    <Card variant="outlined" sx={{ minWidth: 120, flex: '0 1 auto' }}>
      <CardContent>
        <Typography variant="h5" sx={{ fontWeight: 700, color }}>{value}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  );

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
      {status && (
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap mb={4}>
          {stat('Conectores activos', status.conectores_activos, 'primary.main')}
          {stat('Total conectores', status.conectores_total)}
          {stat('Jobs (24h)', status.ultima_24h.total)}
          {stat('Completados', status.ultima_24h.completados, 'success.main')}
          {status.ultima_24h.fallidos > 0 && stat('Fallidos', status.ultima_24h.fallidos, 'error.main')}
          {status.ultima_24h.en_progreso > 0 && stat('En progreso', status.ultima_24h.en_progreso, 'warning.main')}
        </Stack>
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
