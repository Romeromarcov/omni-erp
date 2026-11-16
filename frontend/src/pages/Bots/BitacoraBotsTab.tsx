import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Chip, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  botsControlService,
  CODIGOS_BOT_ESTANDAR,
  type EntradaBitacoraBot,
} from '../../services/botsIngestService';
import { botsKeys } from '../../lib/queryKeys';
import { mensajeActivacion } from '../Activaciones/utils';
import { etiquetaBot } from './utils';

const ACCION_COLOR = new Map<string, 'success' | 'info' | 'warning' | 'error' | 'default'>([
  ['alta', 'success'],
  ['actualizar', 'info'],
  ['baja', 'warning'],
]);

function formatearCambioBitacora(b: EntradaBitacoraBot): string {
  const tieneAntes = Object.keys(b.antes ?? {}).length > 0;
  const tieneDespues = Object.keys(b.despues ?? {}).length > 0;
  if (tieneAntes && tieneDespues) {
    return `${JSON.stringify(b.antes)} → ${JSON.stringify(b.despues)}`;
  }
  if (tieneDespues) return JSON.stringify(b.despues);
  return JSON.stringify(b.antes ?? {});
}

function etiquetaEntidadBitacora(entidad: string): string {
  if (entidad.startsWith('bot:')) {
    const cod = entidad.slice(4);
    return `${etiquetaBot(cod)} (${entidad})`;
  }
  if (entidad.startsWith('usuario:')) {
    return `Usuario Telegram ${entidad.slice(8)} (${entidad})`;
  }
  return entidad;
}

const BitacoraBotsTab: React.FC = () => {
  const [entidad, setEntidad] = useState<string>('');

  const { data: items = [], isLoading, isError, error } = useQuery({
    queryKey: botsKeys.bitacora(entidad || null, 50),
    queryFn: () => botsControlService.listarBitacora({ entidad: entidad || undefined, limite: 50 }),
  });

  const opcionesEntidad = Array.from(
    new Set([
      ...CODIGOS_BOT_ESTANDAR.map((cod) => `bot:${cod}`),
      ...items.map((x) => x.entidad),
      ...(entidad ? [entidad] : []),
    ]),
  );

  const columns: Column<EntradaBitacoraBot>[] = [
    {
      key: 'fecha',
      header: 'Fecha',
      render: (b) => new Date(b.en).toLocaleString('es-VE'),
    },
    {
      key: 'actor',
      header: 'Actor',
      render: (b) => b.actor || 'sistema',
    },
    {
      key: 'entidad',
      header: 'Entidad',
      render: (b) => <Chip size="small" variant="outlined" label={b.entidad} />,
    },
    {
      key: 'accion',
      header: 'Acción',
      render: (b) => (
        <Chip
          size="small"
          color={ACCION_COLOR.get(b.accion) ?? 'default'}
          label={b.accion}
        />
      ),
    },
    {
      key: 'cambio',
      header: 'Detalle del cambio',
      render: (b) => (
        <Typography
          component="span"
          variant="caption"
          sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}
        >
          {formatearCambioBitacora(b)}
        </Typography>
      ),
    },
  ];

  return (
    <Box>
      {isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeActivacion(error, 'No se pudo cargar la bitácora del plano de control.')}
        </Alert>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label="Filtrar entidad"
          value={entidad}
          onChange={(e) => setEntidad(e.target.value)}
          sx={{ minWidth: 280 }}
        >
          <MenuItem value="">Todas las entidades</MenuItem>
          {opcionesEntidad.map((ent) => (
            <MenuItem key={ent} value={ent}>
              {etiquetaEntidadBitacora(ent)}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(b) => b.id}
        loading={isLoading}
        emptyMessage="Aún no hay cambios registrados en la bitácora."
      />
    </Box>
  );
};

export default BitacoraBotsTab;
