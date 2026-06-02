import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Box,
  Divider,
  IconButton,
  List,
  ListItemButton,
  Popover,
  Tooltip,
  Typography,
} from '@mui/material';
import NotificationsNoneOutlined from '@mui/icons-material/NotificationsNoneOutlined';
import { fetcher } from '../services/api';

interface Notificacion {
  id_notificacion: string;
  tipo: string;
  titulo: string;
  mensaje: string;
  leida: boolean;
  fecha_lectura: string | null;
  url_accion: string;
  fecha_creacion: string;
}

const POLL_INTERVAL_MS = 30_000;

const NotificationBell: React.FC = () => {
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const { data: notificaciones = [], refetch } = useQuery<Notificacion[], Error>({
    queryKey: ['notificaciones', 'no-leidas'],
    queryFn: async () => {
      const data = await fetcher<Notificacion[]>(
        '/notificaciones/notificaciones/mis-notificaciones/?no_leidas=true',
      );
      return Array.isArray(data) ? data : [];
    },
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });

  const marcarLeida = async (id: string) => {
    try {
      await fetcher(`/notificaciones/notificaciones/${id}/marcar-leida/`, {
        method: 'PATCH',
        body: JSON.stringify({}),
      });
      refetch();
    } catch {
      /* ignorar errores de red */
    }
  };

  const handleClick = (n: Notificacion) => {
    marcarLeida(n.id_notificacion);
    if (n.url_accion) {
      navigate(n.url_accion);
      setAnchorEl(null);
    }
  };

  const count = notificaciones.length;

  return (
    <>
      <Tooltip title="Notificaciones">
        <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} aria-label="Notificaciones">
          <Badge badgeContent={count} color="error">
            <NotificationsNoneOutlined />
          </Badge>
        </IconButton>
      </Tooltip>
      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
        transformOrigin={{ horizontal: 'right', vertical: 'top' }}
        slotProps={{ paper: { sx: { width: 360, maxHeight: 480, mt: 1 } } }}
      >
        <Box sx={{ px: 2, py: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="subtitle1">Notificaciones</Typography>
          {count > 0 && (
            <Typography variant="caption" color="error">
              {count} sin leer
            </Typography>
          )}
        </Box>
        <Divider />
        {count === 0 ? (
          <Box sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>
            <Typography variant="body2">Sin notificaciones pendientes</Typography>
          </Box>
        ) : (
          <List disablePadding>
            {notificaciones.map((n) => (
              <ListItemButton
                key={n.id_notificacion}
                onClick={() => handleClick(n)}
                sx={{ display: 'block', borderBottom: '1px solid', borderColor: 'divider', py: 1.25 }}
              >
                <Typography variant="body2" fontWeight={600}>{n.titulo}</Typography>
                <Typography variant="body2" color="text.secondary">{n.mensaje}</Typography>
                <Typography variant="caption" color="text.disabled">
                  {new Date(n.fecha_creacion).toLocaleString()}
                </Typography>
              </ListItemButton>
            ))}
          </List>
        )}
      </Popover>
    </>
  );
};

export default NotificationBell;
