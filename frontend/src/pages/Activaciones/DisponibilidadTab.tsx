import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Card, CardContent, LinearProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { calendariosService } from '../../services/activacionesService';
import { activacionesKeys } from '../../lib/queryKeys';
import { localAISO, mensajeActivacion } from './utils';

/** Capacidad y recursos libres (pico simultáneo) de un calendario en un horario. */
const DisponibilidadTab: React.FC = () => {
  const [calendario, setCalendario] = useState('');
  const [inicio, setInicio] = useState('');
  const [fin, setFin] = useState('');

  const { data: calendarios = [] } = useQuery({
    queryKey: activacionesKeys.calendarios(),
    queryFn: () => calendariosService.getAll(),
  });
  const calendarioId =
    calendario || calendarios.find((c) => c.es_predeterminado)?.id_calendario || calendarios[0]?.id_calendario || '';

  const inicioISO = localAISO(inicio);
  const finISO = localAISO(fin);
  const rangoValido = inicioISO !== '' && finISO !== '' && new Date(fin) > new Date(inicio);

  const { data, isFetching, error } = useQuery({
    queryKey: activacionesKeys.disponibilidad(calendarioId, inicioISO, finISO),
    queryFn: () => calendariosService.disponibilidad(calendarioId, inicioISO, finISO),
    enabled: Boolean(calendarioId) && rangoValido,
  });

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 3 }}>
        <TextField
          select
          size="small"
          label="Calendario"
          value={calendarioId}
          onChange={(e) => setCalendario(e.target.value)}
          sx={{ minWidth: 220 }}
        >
          {calendarios.map((c) => (
            <MenuItem key={c.id_calendario} value={c.id_calendario}>
              {c.nombre}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="datetime-local"
          label="Inicio"
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          size="small"
          type="datetime-local"
          label="Fin"
          value={fin}
          onChange={(e) => setFin(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
      </Stack>

      {!rangoValido && (
        <Typography color="text.secondary">
          Indica un horario (con fin posterior al inicio) para ver cuántos recursos quedan libres.
        </Typography>
      )}
      {error && <Alert severity="error">{mensajeActivacion(error, 'No se pudo consultar la disponibilidad.')}</Alert>}
      {rangoValido && isFetching && <LinearProgress sx={{ mb: 2 }} />}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
        {(data ?? []).map((r) => {
          const pct = r.capacidad > 0 ? Math.min(100, (r.usado / r.capacidad) * 100) : 0;
          return (
            <Card key={r.codigo} variant="outlined" sx={{ minWidth: 220, flex: '1 1 220px' }}>
              <CardContent>
                <Typography variant="overline" color="text.secondary">
                  {r.nombre}
                </Typography>
                <Typography variant="h4">
                  {r.libres}
                  <Typography component="span" variant="body1" color="text.secondary">
                    {' '}
                    libres de {r.capacidad}
                  </Typography>
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={pct}
                  color={r.libres === 0 ? 'error' : 'primary'}
                  sx={{ my: 1 }}
                  aria-label={`Uso de ${r.nombre}`}
                />
                <Typography variant="caption" color="text.secondary">
                  En uso (pico simultáneo): {r.usado}
                </Typography>
              </CardContent>
            </Card>
          );
        })}
      </Stack>
      {rangoValido && !isFetching && data?.length === 0 && (
        <Typography color="text.secondary">Este calendario no tiene recursos configurados.</Typography>
      )}
    </Box>
  );
};

export default DisponibilidadTab;
