import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Button,
  Card,
  CardActionArea,
  CardActions,
  CardContent,
  Chip,
  Stack,
  Typography,
} from '@mui/material';
import {
  exportarConector,
  type ConectorInstancia,
} from '../../services/integrationHubService';

interface Props {
  conector: ConectorInstancia;
}

const PROVEEDOR_SHEETS = 'google_sheets';

type ChipColor = 'success' | 'warning' | 'error' | 'default';

const ESTADO_COLORS: Record<string, { color: ChipColor; label: string }> = {
  activo: { color: 'success', label: 'Activo' },
  configurando: { color: 'warning', label: 'Configurando' },
  error: { color: 'error', label: 'Error' },
  inactivo: { color: 'default', label: 'Inactivo' },
};

const ConectorCard: React.FC<Props> = ({ conector }) => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const estado = ESTADO_COLORS[conector.estado] ?? ESTADO_COLORS.inactivo;
  const esSheets = conector.proveedor_codigo === PROVEEDOR_SHEETS;

  const exportMutation = useMutation({
    mutationFn: () => exportarConector(conector.id_conector),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [`/integration-hub/instancias/${conector.id_conector}/jobs/`] });
      qc.invalidateQueries({ queryKey: ['/integration-hub/status/'] });
    },
  });

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

      {/* Acción rápida de exportación para conectores Google Sheets */}
      {esSheets && (
        <CardActions sx={{ px: 2, pb: 1.5, flexDirection: 'column', alignItems: 'flex-start' }}>
          <Button
            size="small"
            variant="outlined"
            disabled={exportMutation.isPending}
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? 'Encolando…' : 'Exportar ahora'}
          </Button>
          {exportMutation.isSuccess && (
            <Typography variant="caption" color="success.main" sx={{ mt: 0.5 }}>
              Exportación encolada
            </Typography>
          )}
          {exportMutation.isError && (
            <Typography variant="caption" color="error.main" sx={{ mt: 0.5 }}>
              {(exportMutation.error as Error).message}
            </Typography>
          )}
        </CardActions>
      )}
    </Card>
  );
};

export default ConectorCard;
