import React, { useState } from 'react';
import { Box, Tab, Tabs } from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import EventosTab from './EventosTab';
import DisponibilidadTab from './DisponibilidadTab';
import CalendariosTab from './CalendariosTab';

const TABS = ['Eventos', 'Disponibilidad', 'Calendarios y recursos'] as const;

const ActivacionesPage: React.FC = () => {
  const [tab, setTab] = useState(0);

  return (
    <PageContainer>
      <PageHeader
        title="Activaciones"
        subtitle="Eventos en puntos de venta: reservas, capacidad de promotoras e igloos y calendarios."
      />
      <Tabs
        value={tab}
        onChange={(_, v: number) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Secciones de activaciones"
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        {TABS.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>
      <Box role="tabpanel">
        {tab === 0 && <EventosTab />}
        {tab === 1 && <DisponibilidadTab />}
        {tab === 2 && <CalendariosTab />}
      </Box>
    </PageContainer>
  );
};

export default ActivacionesPage;
