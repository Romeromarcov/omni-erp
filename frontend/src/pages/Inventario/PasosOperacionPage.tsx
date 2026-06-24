import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import AddIcon from '@mui/icons-material/Add';
import { PageContainer, PageHeader } from '../../components/ui';
import { almacenesService } from '../../services/almacenesService';
import {
  pasosOperacionService,
  type CrearPasoPayload,
  type TipoOperacion,
} from '../../services/inventarioService';
import { inventarioKeys } from '../../lib/queryKeys';

const PasosOperacionPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  // Permite enlazar desde Almacenes con ?almacen=<id> para abrir su configuración.
  const [almacen, setAlmacen] = useState(() => searchParams.get('almacen') ?? '');
  const [tipo, setTipo] = useState<TipoOperacion>('RECEPCION');
  const [nombrePaso, setNombrePaso] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const { data: almacenes = [] } = useQuery({
    queryKey: ['almacenes'],
    queryFn: () => almacenesService.getAll(),
  });

  const pasosQuery = useQuery({
    queryKey: inventarioKeys.pasosOperacion(almacen, tipo),
    queryFn: () => pasosOperacionService.list(almacen, tipo),
    enabled: Boolean(almacen),
  });
  const pasos = pasosQuery.data ?? [];

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: inventarioKeys.pasosOperacion(almacen, tipo) });

  const crear = useMutation({
    mutationFn: (payload: CrearPasoPayload) => pasosOperacionService.create(payload),
    onSuccess: () => {
      setNombrePaso('');
      setErrorMsg('');
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(e instanceof Error ? e.message : 'No se pudo agregar el paso.'),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => pasosOperacionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(e instanceof Error ? e.message : 'No se pudo eliminar el paso.'),
  });

  const almacenObj = almacenes.find((a) => a.id_almacen === almacen);

  const handleAgregar = () => {
    if (!almacen || !nombrePaso.trim()) {
      setErrorMsg('Seleccione un almacén e ingrese el nombre del paso.');
      return;
    }
    const siguienteSecuencia = pasos.reduce((max, p) => Math.max(max, p.secuencia), 0) + 1;
    crear.mutate({
      id_empresa: almacenObj?.id_empresa ?? '',
      id_almacen: almacen,
      tipo_operacion: tipo,
      nombre_paso: nombrePaso.trim(),
      secuencia: siguienteSecuencia,
    });
  };

  return (
    <PageContainer>
      <PageHeader
        title="Pasos de operación"
        subtitle="Configura, por almacén y operación, los pasos que recepciones y entregas confirman uno a uno."
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          <TextField
            select
            label="Almacén"
            value={almacen}
            onChange={(e) => setAlmacen(e.target.value)}
            sx={{ maxWidth: 360 }}
          >
            {almacenes.map((a) => (
              <MenuItem key={a.id_almacen} value={a.id_almacen}>
                {a.nombre_almacen}
              </MenuItem>
            ))}
          </TextField>

          <ToggleButtonGroup
            exclusive
            value={tipo}
            onChange={(_, v: TipoOperacion | null) => v && setTipo(v)}
            size="small"
          >
            <ToggleButton value="RECEPCION">Recepción</ToggleButton>
            <ToggleButton value="ENTREGA">Entrega</ToggleButton>
          </ToggleButtonGroup>

          {!almacen && <Typography color="text.secondary">Seleccione un almacén para ver sus pasos.</Typography>}

          {almacen && (
            <Box>
              <List dense>
                {pasos.length === 0 && (
                  <Typography color="text.secondary">Sin pasos configurados para esta operación.</Typography>
                )}
                {pasos.map((p) => (
                  <ListItem
                    key={p.id_paso_operacion}
                    secondaryAction={
                      <IconButton
                        aria-label={`eliminar ${p.nombre_paso}`}
                        edge="end"
                        onClick={() => eliminar.mutate(p.id_paso_operacion)}
                        disabled={eliminar.isPending}
                        size="small"
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    }
                  >
                    <Chip size="small" label={p.secuencia} sx={{ mr: 1 }} />
                    <ListItemText primary={p.nombre_paso} />
                  </ListItem>
                ))}
              </List>

              <Stack direction="row" spacing={1} sx={{ mt: 1 }} alignItems="center">
                <TextField
                  label="Nuevo paso"
                  value={nombrePaso}
                  onChange={(e) => setNombrePaso(e.target.value)}
                  size="small"
                  sx={{ flex: 1, maxWidth: 360 }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAgregar();
                  }}
                />
                <Button startIcon={<AddIcon />} onClick={handleAgregar} disabled={crear.isPending} variant="contained">
                  Agregar
                </Button>
              </Stack>
            </Box>
          )}
        </Stack>
      </Paper>
    </PageContainer>
  );
};

export default PasosOperacionPage;
