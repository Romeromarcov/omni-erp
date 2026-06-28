import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  productoInventarioService,
  recepcionesService,
  entregasService,
  type CrearOperacionLinea,
  type CrearOperacionPayload,
  type OperacionInventario,
  type TipoOperacion,
} from '../../services/inventarioService';
import { almacenesService } from '../../services/almacenesService';
import { inventarioKeys } from '../../lib/queryKeys';

interface OperacionesPageProps {
  tipo: TipoOperacion;
  titulo: string;
}

interface LineaForm {
  producto: string;
  cantidad: string;
  costo_unitario: string;
}

function origenesPara(tipo: TipoOperacion): { value: string; label: string }[] {
  return tipo === 'RECEPCION'
    ? [{ value: 'PURCHASE', label: 'Compra' }]
    : [
        { value: 'SALE', label: 'Venta' },
        { value: 'TRANSFER', label: 'Transferencia' },
        { value: 'RETURN', label: 'Devolución' },
        { value: 'SCRAP', label: 'Desecho' },
      ];
}

function estadoTone(estado: OperacionInventario['estado']): 'default' | 'success' | 'warning' {
  if (estado === 'COMPLETADA') return 'success';
  if (estado === 'CANCELADA') return 'default';
  return 'warning';
}

const OperacionesPage: React.FC<OperacionesPageProps> = ({ tipo, titulo }) => {
  const queryClient = useQueryClient();
  const service = tipo === 'RECEPCION' ? recepcionesService : entregasService;
  const listKey = tipo === 'RECEPCION' ? inventarioKeys.recepciones() : inventarioKeys.entregas();

  const [seleccion, setSeleccion] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [almacen, setAlmacen] = useState('');
  const [origenTipo, setOrigenTipo] = useState(origenesPara(tipo)[0].value);
  const [contraparte, setContraparte] = useState('');
  const [origenId, setOrigenId] = useState('');
  const [motivo, setMotivo] = useState('');
  const [lineas, setLineas] = useState<LineaForm[]>([{ producto: '', cantidad: '', costo_unitario: '' }]);

  const { data: operaciones = [] } = useQuery({
    queryKey: listKey,
    queryFn: () => service.list(),
  });
  const { data: almacenes = [] } = useQuery({
    queryKey: ['almacenes'],
    queryFn: () => almacenesService.getAll(),
  });
  const { data: productos = [] } = useQuery({
    queryKey: inventarioKeys.productosInventario(),
    queryFn: () => productoInventarioService.getAll(),
  });

  const opActual = useMemo(
    () => operaciones.find((o) => o.id_operacion === seleccion) ?? null,
    [operaciones, seleccion],
  );

  const crear = useMutation({
    mutationFn: (payload: CrearOperacionPayload) => service.create(payload),
    onSuccess: (op) => {
      setSeleccion(op.id_operacion);
      setErrorMsg('');
      setLineas([{ producto: '', cantidad: '', costo_unitario: '' }]);
      queryClient.invalidateQueries({ queryKey: listKey });
    },
    onError: (e: unknown) => setErrorMsg(e instanceof Error ? e.message : 'No se pudo crear la operación.'),
  });

  const confirmar = useMutation({
    mutationFn: ({ opId, stepId }: { opId: string; stepId: string }) => service.confirmStep(opId, stepId),
    onSuccess: () => {
      setErrorMsg('');
      queryClient.invalidateQueries({ queryKey: listKey });
    },
    onError: (e: unknown) => setErrorMsg(e instanceof Error ? e.message : 'No se pudo confirmar el paso.'),
  });

  const handleCrear = () => {
    const lns: CrearOperacionLinea[] = lineas
      .filter((l) => l.producto && l.cantidad)
      .map((l) => ({
        producto: l.producto,
        cantidad: l.cantidad,
        costo_unitario: l.costo_unitario || null,
      }));
    if (!almacen || lns.length === 0) {
      setErrorMsg('Seleccione almacén y al menos una línea con producto y cantidad.');
      return;
    }
    const payload: CrearOperacionPayload = {
      almacen,
      origen_tipo: origenTipo,
      lineas: lns,
    };
    if (origenTipo === 'TRANSFER') payload.almacen_contraparte = contraparte || null;
    if (origenTipo === 'SALE') payload.origen_id = origenId || null;
    if (origenTipo === 'RETURN' || origenTipo === 'SCRAP') payload.motivo = motivo;
    crear.mutate(payload);
  };

  const setLinea = (i: number, patch: Partial<LineaForm>) =>
    setLineas((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  // Índice del primer paso sin confirmar (el único confirmable: bloquea fuera de orden).
  const activeStep = opActual ? opActual.pasos.findIndex((p) => !p.confirmado) : -1;

  return (
    <PageContainer>
      <PageHeader title={titulo} subtitle="Confirma los pasos configurados, uno a uno, para mover el stock." />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        {/* Crear operación */}
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="h6" gutterBottom>
            Nueva {tipo === 'RECEPCION' ? 'recepción' : 'entrega'}
          </Typography>
          <Stack spacing={2}>
            <TextField
              select
              label="Almacén"
              value={almacen}
              onChange={(e) => setAlmacen(e.target.value)}
              fullWidth
            >
              {almacenes.map((a) => (
                <MenuItem key={a.id_almacen} value={a.id_almacen}>
                  {a.nombre_almacen}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              select
              label="Origen"
              value={origenTipo}
              onChange={(e) => setOrigenTipo(e.target.value)}
              fullWidth
            >
              {origenesPara(tipo).map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>

            {origenTipo === 'TRANSFER' && (
              <TextField
                select
                label="Almacén destino"
                value={contraparte}
                onChange={(e) => setContraparte(e.target.value)}
                fullWidth
              >
                {almacenes
                  .filter((a) => a.id_almacen !== almacen)
                  .map((a) => (
                    <MenuItem key={a.id_almacen} value={a.id_almacen}>
                      {a.nombre_almacen}
                    </MenuItem>
                  ))}
              </TextField>
            )}
            {origenTipo === 'SALE' && (
              <TextField
                label="Nota de venta (ID)"
                value={origenId}
                onChange={(e) => setOrigenId(e.target.value)}
                fullWidth
              />
            )}
            {(origenTipo === 'RETURN' || origenTipo === 'SCRAP') && (
              <TextField
                label="Motivo"
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                fullWidth
                multiline
              />
            )}

            <Divider>Líneas</Divider>
            {lineas.map((l, i) => (
              <Stack direction="row" spacing={1} key={i} alignItems="center">
                <TextField
                  select
                  label="Producto"
                  value={l.producto}
                  onChange={(e) => setLinea(i, { producto: e.target.value })}
                  sx={{ flex: 2 }}
                  size="small"
                >
                  {productos.map((p) => (
                    <MenuItem key={p.id_producto} value={p.id_producto}>
                      {p.nombre_producto}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Cant."
                  value={l.cantidad}
                  onChange={(e) => setLinea(i, { cantidad: e.target.value })}
                  sx={{ flex: 1 }}
                  size="small"
                />
                {tipo === 'RECEPCION' && (
                  <TextField
                    label="Costo"
                    value={l.costo_unitario}
                    onChange={(e) => setLinea(i, { costo_unitario: e.target.value })}
                    sx={{ flex: 1 }}
                    size="small"
                  />
                )}
                <IconButton
                  aria-label="eliminar línea"
                  onClick={() => setLineas((prev) => prev.filter((_, idx) => idx !== i))}
                  disabled={lineas.length === 1}
                  size="small"
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
            <Button
              startIcon={<AddIcon />}
              onClick={() => setLineas((prev) => [...prev, { producto: '', cantidad: '', costo_unitario: '' }])}
              size="small"
            >
              Agregar línea
            </Button>

            <Button variant="contained" onClick={handleCrear} disabled={crear.isPending}>
              Crear
            </Button>
          </Stack>
        </Paper>

        {/* Lista + stepper */}
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="h6" gutterBottom>
            Operaciones
          </Typography>
          <Stack spacing={1} sx={{ mb: 2 }}>
            {operaciones.length === 0 && (
              <Typography color="text.secondary">Sin operaciones todavía.</Typography>
            )}
            {operaciones.map((o) => (
              <Box
                key={o.id_operacion}
                onClick={() => setSeleccion(o.id_operacion)}
                sx={{
                  p: 1,
                  borderRadius: 1,
                  cursor: 'pointer',
                  border: (t) =>
                    `1px solid ${o.id_operacion === seleccion ? t.palette.primary.main : t.palette.divider}`,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>{o.numero}</span>
                <Chip size="small" color={estadoTone(o.estado)} label={o.estado} />
              </Box>
            ))}
          </Stack>

          {opActual && (
            <Box>
              <Divider sx={{ mb: 2 }} />
              <Typography variant="subtitle1" gutterBottom>
                {opActual.numero} — {opActual.estado}
              </Typography>
              <Stepper activeStep={activeStep < 0 ? opActual.pasos.length : activeStep} orientation="vertical">
                {opActual.pasos.map((paso, idx) => (
                  <Step key={paso.id_operacion_paso} completed={paso.confirmado}>
                    <StepLabel
                      icon={paso.confirmado ? <CheckCircleIcon color="success" /> : idx + 1}
                    >
                      <Stack direction="row" spacing={2} alignItems="center">
                        <span>{paso.nombre_paso}</span>
                        {!paso.confirmado && idx === activeStep && opActual.estado === 'EN_PROCESO' && (
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={confirmar.isPending}
                            onClick={() =>
                              confirmar.mutate({ opId: opActual.id_operacion, stepId: paso.id_operacion_paso })
                            }
                          >
                            Confirmar
                          </Button>
                        )}
                      </Stack>
                    </StepLabel>
                  </Step>
                ))}
              </Stepper>
              {opActual.estado === 'COMPLETADA' && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  Operación completada: el stock y los asientos se generaron automáticamente.
                </Alert>
              )}
            </Box>
          )}
        </Paper>
      </Stack>
    </PageContainer>
  );
};

export default OperacionesPage;
