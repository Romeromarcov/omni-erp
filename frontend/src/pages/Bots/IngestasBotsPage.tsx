import React, { useState } from 'react';
import { Box, Tab, Tabs } from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import IngestasTab from './IngestasTab';
import UsuariosBotTab from './UsuariosBotTab';

const TABS = ['Ingestas', 'Usuarios de Telegram'] as const;

const IngestasBotsPage: React.FC = () => {
  const [tab, setTab] = useState(0);

  return (
    <PageContainer>
      <PageHeader
        title="Bots de Telegram"
        subtitle="Lo que envían los bots (pedidos, cotizaciones, pagos, eventos), pagos por completar y usuarios autorizados."
      />
      <Tabs
        value={tab}
        onChange={(_, v: number) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Secciones de bots"
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        {TABS.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>
      <Box role="tabpanel">{tab === 0 ? <IngestasTab /> : <UsuariosBotTab />}</Box>
    </PageContainer>
  );
};

export default IngestasBotsPage;
