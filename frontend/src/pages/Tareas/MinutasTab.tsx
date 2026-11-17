import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { StatusChip } from '../../components/ui';
import {
  minutasTareasService,
  proyectosTareasService,
  type MinutaReunion,
} from '../../services/tareasService';
import { tareasKeys } from '../../lib/queryKeys';
import {
  ESTADO_MINUTA_COLOR,
  PRIORIDAD_TAREA_COLOR,
  etiquetaPrioridadTarea,
  mensajeTareas,
  parsearLineasMinuta,
} from './utils';

interface MinutasTabProps {
  empresaId: string | null;
}

const ESTADO_MINUTA_LABEL = new Map<string, string>([
  ['BORRADOR', 'Borrador por confirmar'],
  ['CONFIRMADA', 'Confirmada'],
  ['DESCARTADA', 'Descartada'],
]);

const FORM_MINUTA_VACIO = {
  titulo: '',
  fecha_reunion: '',
  texto_fuente: '',
  acuerdos_lineas: '',
};

const MinutasTab: React.FC<MinutasTabProps> = ({ empresaId }) => {
  const qc = useQueryClient();
  const [dialogAbierto, setDialogAbierto] = useState(false);
  const [form, setForm] = useState(FORM_MINUTA_VACIO);
  const [proyectoDestino, setProyectoDestino] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const { data: minutas = [], isLoading } = useQuery({
    queryKey: tareasKeys.minutas(empresaId),
    queryFn: () => minutasTareasService.getAll(),
  });

  const { data: proyectos = [] } = useQuery({
    queryKey: tareasKeys.proyectos(empresaId, false),
    queryFn: () => proyectosTareasService.getAll(false),
  });

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: tareasKeys.porEmpresa(empresaId) });
  };

  const crearBorrador = useMutation({
    mutationFn: () =>
      minutasTareasService.create({
        titulo: form.titulo.trim(),
        fecha_reunion: form.fecha_reunion || undefined,
        texto_fuente: form.texto_fuente.trim(),
        items_propuestos: parsearLineasMinuta(form.acuerdos_lineas),
      }),
    onSuccess: () => {
      setDialogAbierto(false);
      setForm(FORM_MINUTA_VACIO);
      setErrorMsg('');
      setInfoMsg('Borrador de minuta creado y enriquecido con responsables, áreas y fechas.');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo generar el borrador de la minuta.'));
    },
  });

  const confirmar = useMutation({
    mutationFn: (m: MinutaReunion) =>
      minutasTareasService.confirmar(m.id_minuta, {
        proyecto: proyectoDestino || undefined,
      }),
    onSuccess: (res) => {
      setErrorMsg('');
      setInfoMsg(
        `Minuta confirmada: se generaron ${res.tareas_creadas.length} tareas operativas.`,
      );
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo confirmar la minuta.'));
    },
  });

  return (
    <Box>
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      {infoMsg && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setInfoMsg('')}>
          {infoMsg}
        </Alert>
      )}

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        justifyContent="space-between"
        alignItems={{ sm: 'center' }}
        sx={{ mb: 2.5 }}
      >
        <TextField
          select
          size="small"
          label="Proyecto destino al confirmar (opcional)"
          value={proyectoDestino}
          onChange={(ev) => setProyectoDestino(ev.target.value)}
          sx={{ minWidth: 280 }}
        >
          <MenuItem value="">Tablero personal de cada responsable</MenuItem>
          {proyectos.map((p) => (
            <MenuItem key={p.id_proyecto} value={p.id_proyecto}>
              {p.nombre}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" onClick={() => setDialogAbierto(true)}>
          Nueva minuta
        </Button>
      </Stack>

      {isLoading ? (
        <Typography variant="body2" color="text.secondary">
          Cargando minutas…
        </Typography>
      ) : minutas.length === 0 ? (
        <Card variant="outlined">
          <CardContent sx={{ textAlign: 'center', py: 5 }}>
            <Typography variant="subtitle1" gutterBottom>
              Sin minutas registradas
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Registra acuerdos de comité para pre-asignar responsables, áreas e hitos de
              vencimiento antes de materializarlos en tareas reales.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={2}>
          {minutas.map((m) => (
            <Card key={m.id_minuta} variant="outlined">
              <CardContent>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  justifyContent="space-between"
                  alignItems={{ sm: 'center' }}
                  spacing={1}
                  sx={{ mb: 1.5 }}
                >
                  <Box>
                    <Typography variant="subtitle1" fontWeight={700}>
                      {m.titulo}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Fecha reunión: {m.fecha_reunion ?? 'Sin fecha'} · Ítems:{' '}
                      {m.borrador_tareas.length}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <StatusChip
                      value={m.estado}
                      label={ESTADO_MINUTA_LABEL.get(m.estado) ?? m.estado}
                      colorMap={ESTADO_MINUTA_COLOR}
                    />
                    {m.estado === 'BORRADOR' && (
                      <Button
                        size="small"
                        variant="contained"
                        disabled={confirmar.isPending || m.borrador_tareas.length === 0}
                        onClick={() => confirmar.mutate(m)}
                      >
                        Confirmar y crear tareas
                      </Button>
                    )}
                  </Stack>
                </Stack>

                {m.texto_fuente && (
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 1.5, whiteSpace: 'pre-wrap' }}
                  >
                    {m.texto_fuente}
                  </Typography>
                )}

                <Stack spacing={1}>
                  {m.borrador_tareas.map((it, idx) => (
                    <Box
                      key={`${m.id_minuta}-${idx}`}
                      sx={{
                        p: 1,
                        borderRadius: 1,
                        border: 1,
                        borderColor: 'divider',
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 1,
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <Typography variant="body2" fontWeight={600}>
                        {it.titulo}
                      </Typography>
                      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                        <StatusChip
                          value={it.prioridad ?? 'MEDIA'}
                          label={etiquetaPrioridadTarea(it.prioridad ?? 'MEDIA')}
                          colorMap={PRIORIDAD_TAREA_COLOR}
                        />
                        {it.asignado_nombre && (
                          <Chip size="small" variant="outlined" label={it.asignado_nombre} />
                        )}
                        {it.area && <Chip size="small" variant="outlined" label={it.area} />}
                        {it.fecha_vencimiento && (
                          <Chip
                            size="small"
                            variant="outlined"
                            label={`Vence: ${it.fecha_vencimiento}`}
                          />
                        )}
                      </Stack>
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      <Dialog
        open={dialogAbierto}
        onClose={() => setDialogAbierto(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Registrar minuta y acuerdos</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <TextField
                label="Título de la reunión"
                required
                fullWidth
                value={form.titulo}
                onChange={(ev) => setForm({ ...form, titulo: ev.target.value })}
              />
              <TextField
                label="Fecha de reunión"
                type="date"
                slotProps={{ inputLabel: { shrink: true } }}
                value={form.fecha_reunion}
                onChange={(ev) => setForm({ ...form, fecha_reunion: ev.target.value })}
                sx={{ minWidth: 190 }}
              />
            </Stack>
            <TextField
              label="Resumen o transcripción de contexto (opcional)"
              multiline
              minRows={2}
              fullWidth
              value={form.texto_fuente}
              onChange={(ev) => setForm({ ...form, texto_fuente: ev.target.value })}
            />
            <TextField
              label="Acuerdos propuestos (uno por línea: Título | Responsable | Fecha | Prioridad)"
              placeholder={'Conciliar banco Mercantil | Ana | mañana | ALTA\nValidar despacho Valencia | viernes'}
              multiline
              minRows={4}
              required
              fullWidth
              value={form.acuerdos_lineas}
              onChange={(ev) => setForm({ ...form, acuerdos_lineas: ev.target.value })}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogAbierto(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={
              !form.titulo.trim() ||
              parsearLineasMinuta(form.acuerdos_lineas).length === 0 ||
              crearBorrador.isPending
            }
            onClick={() => crearBorrador.mutate()}
          >
            Previsualizar borrador
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MinutasTab;
