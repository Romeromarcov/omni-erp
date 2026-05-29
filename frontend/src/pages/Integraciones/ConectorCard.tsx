import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Card, CardActionArea, CardContent, Chip, Stack, Typography } from '@mui/material';
import type { ConectorInstancia } from '../../services/integrationHubService';

interface Props {
  conector: ConectorInstancia;
}

type ChipColor = 'success' | 'warning' | 'error' | 'default';

const ESTADO_COLORS: Record<string, { color: ChipColor; label: string }> = {
  activo: { color: 'success', label: 'Activo' },
  configurando: { color: 'warning', label: 'Configurando' },
  error: { color: 'error', label: 'Error' },
  inactivo: { color: 'default', label: 'Inactivo' },
};

const ConectorCard: React.FC<Props> = ({ conector }) => {
  const navigate = useNavigate();
  const estado = ESTADO_COLORS[conector.estado] ?? ESTADO_COLORS.inactivo;

  const ultimoSync = conector.ultimo_sync
    ? new Date(conector.ultimo_sync).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })
    : 'Nunca';

  return (
    <Card variant="outlined">
      <CardActionArea onClick={() => navigate(`/integraciones/conectores/${conector.id_conector}`)}>
        <CardContent>
          <Stack spacing={1.25}>
            {/* Header */}
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
              <Box>
                <Typography sx={{ fontWeight: 700 }}>{conector.nombre}</Typography>
                <Typography variant="caption" color="text.secondary">{conector.proveedor_nombre}</Typography>
              </Box>
              <Chip size="small" label={estado.label} color={estado.color} variant={estado.color === 'default' ? 'outlined' : 'filled'} />
            </Stack>

            {/* Host */}
            {conector.configuracion_publica?.host && (
              <Typography
                variant="body2"
                sx={{ fontFamily: 'monospace', bgcolor: 'action.hover', px: 1, py: 0.5, borderRadius: 1, wordBreak: 'break-all' }}
              >
                {conector.configuracion_publica.host}
              </Typography>
            )}

            {/* Entidades */}
            {conector.entidades_activas.length > 0 && (
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {conector.entidades_activas.map(e => (
                  <Chip key={e} size="small" label={e} color="info" variant="outlined" />
                ))}
              </Stack>
            )}

            {/* Footer */}
            <Typography variant="caption" color="text.secondary">
              Último sync: {ultimoSync}
              {conector.version_detectada && ` · v${conector.version_detectada}`}
            </Typography>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default ConectorCard;
