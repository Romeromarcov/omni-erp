import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Tab, Tabs } from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import { tareasService } from '../../services/tareasService';
import { tareasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import ListaTareasTab from './ListaTareasTab';
import MinutasTab from './MinutasTab';
import RecurrentesTab from './RecurrentesTab';
import ResumenEquiposTab from './ResumenEquiposTab';
import TableroKanbanTab from './TableroKanbanTab';
import TareaDetalleDialog from './TareaDetalleDialog';

const TABS = [
  'Tablero Kanban',
  'Lista y Seguimiento',
  'Minutas y Acuerdos',
  'Recurrentes',
  'Resumen y Equipos',
] as const;

const TareasPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  const { tareaId } = useParams<{ tareaId?: string }>();
  const navigate = useNavigate();
  const empresaId = getEmpresaId();

  const { data: tareaRuta = null } = useQuery({
    queryKey: tareasKeys.item(empresaId, tareaId ?? ''),
    queryFn: () => tareasService.getById(tareaId ?? ''),
    enabled: Boolean(tareaId),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Tareas y Proyectos"
        subtitle="Ejecución operativa multi-tenant: tableros Kanban, minutas con IA, recurrencias y seguimiento determinístico vinculado al ERP."
      />
      <Tabs
        value={tab}
        onChange={(_, v: number) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Secciones de tareas operativas"
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        {TABS.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>
      <Box role="tabpanel">
        {tab === 0 && <TableroKanbanTab empresaId={empresaId} />}
        {tab === 1 && <ListaTareasTab empresaId={empresaId} />}
        {tab === 2 && <MinutasTab empresaId={empresaId} />}
        {tab === 3 && <RecurrentesTab empresaId={empresaId} />}
        {tab === 4 && <ResumenEquiposTab empresaId={empresaId} />}
      </Box>

      {tareaId && tareaRuta && (
        <TareaDetalleDialog
          empresaId={empresaId}
          tarea={tareaRuta}
          onClose={() => {
            void navigate('/tareas');
          }}
        />
      )}
    </PageContainer>
  );
};

export default TareasPage;
