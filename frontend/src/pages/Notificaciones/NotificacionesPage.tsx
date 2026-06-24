import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, FormControlLabel, Switch } from '@mui/material';
import DoneAllOutlined from '@mui/icons-material/DoneAllOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  notificacionesService,
  type Notificacion,
} from '../../services/notificacionesService';
import { notificacionesKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';

/** Formatea una fecha ISO a texto local legible; tolera valores inválidos. */
function formatearFecha(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

const NotificacionesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [soloNoLeidas, setSoloNoLeidas] = useState(false);

  const {
    data: notificaciones = [],
    isLoading,
    error,
  } = useQuery<Notificacion[], Error>({
    queryKey: notificacionesKeys.mis(soloNoLeidas),
    queryFn: () => notificacionesService.misNotificaciones(soloNoLeidas),
  });

  const marcarLeida = useMutation<Notificacion, Error, string>({
    mutationFn: (id) => notificacionesService.marcarLeida(id),
    onSuccess: () => {
      // Invalida toda la familia: lista (ambas vistas) e indicador de la campana.
      queryClient.invalidateQueries({ queryKey: notificacionesKeys.all() });
    },
  });

  const noLeidas = notificaciones.filter((n) => !n.leida);

  const marcarTodas = () => {
    noLeidas.forEach((n) => marcarLeida.mutate(n.id_notificacion));
  };

  const columns: Column<Notificacion>[] = [
    {
      key: 'estado',
      header: 'Estado',
      render: (n) => (
        <StatusChip
          value={n.leida ? 'Leída' : 'No leída'}
          colorMap={{ leída: 'default', 'no leída': 'info' }}
        />
      ),
    },
    { key: 'titulo', header: 'Título', render: (n) => n.titulo },
    { key: 'mensaje', header: 'Mensaje', render: (n) => n.mensaje },
    { key: 'tipo', header: 'Tipo', render: (n) => n.tipo || '—' },
    {
      key: 'fecha',
      header: 'Fecha',
      render: (n) => formatearFecha(n.fecha_creacion),
    },
    {
      key: 'acciones',
      header: '',
      align: 'right',
      render: (n) =>
        n.leida ? null : (
          <Button
            size="small"
            variant="outlined"
            onClick={() => marcarLeida.mutate(n.id_notificacion)}
            disabled={marcarLeida.isPending}
          >
            Marcar como leída
          </Button>
        ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Notificaciones"
        subtitle="Tus últimas notificaciones"
        actions={
          <Button
            variant="contained"
            startIcon={<DoneAllOutlined />}
            onClick={marcarTodas}
            disabled={noLeidas.length === 0 || marcarLeida.isPending}
          >
            Marcar todas como leídas
          </Button>
        }
      />

      <FormControlLabel
        control={
          <Switch
            checked={soloNoLeidas}
            onChange={(e) => setSoloNoLeidas(e.target.checked)}
          />
        }
        label="Solo no leídas"
        sx={{ mb: 2 }}
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeDeError(error, 'No se pudieron cargar las notificaciones.')}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={notificaciones}
        getRowKey={(n) => n.id_notificacion}
        loading={isLoading}
        emptyMessage="Sin notificaciones"
      />
    </PageContainer>
  );
};

export default NotificacionesPage;
