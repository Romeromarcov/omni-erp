import React, { useState } from 'react';
import { Box, Tab, Tabs } from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import BitacoraBotsTab from './BitacoraBotsTab';
import FlotaControlTab from './FlotaControlTab';
import IngestasTab from './IngestasTab';
import UsuariosBotTab from './UsuariosBotTab';

const TABS = [
  'Ingestas',
  'Flota y Control',
  'Usuarios de Telegram',
  'Bitácora',
] as const;

const IngestasBotsPage: React.FC = () => {
  const [tab, setTab] = useState(0);

  return (
    <PageContainer>
      <PageHeader
        title="Bots de Telegram"
        subtitle="Plano de control multi-tenant de la flota, borradores recibidos, sincronización en borrador con Odoo, usuarios autorizados y bitácora."
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
      <Box role="tabpanel">
        {tab === 0 && <IngestasTab />}
        {tab === 1 && <FlotaControlTab />}
        {tab === 2 && <UsuariosBotTab />}
        {tab === 3 && <BitacoraBotsTab />}
      </Box>
    </PageContainer>
  );
};

export default IngestasBotsPage;
