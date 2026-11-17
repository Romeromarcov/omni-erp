import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { StatusChip } from '../../components/ui';
import {
  areasTareasService,
  PRIORIDADES_TAREA,
  proyectosTareasService,
  tareasService,
  type PrioridadTarea,
  type Proyecto,
  type Tarea,
} from '../../services/tareasService';
import { fetchUsuarios } from '../../services/users';
import { tareasKeys } from '../../lib/queryKeys';
import TareaDetalleDialog from './TareaDetalleDialog';
import {
  PRIORIDAD_TAREA_COLOR,
  esTareaVencida,
  etiquetaPrioridadTarea,
  mensajeTareas,
} from './utils';

interface TableroKanbanTabProps {
  empresaId: string | null;
}

const FORM_NUEVA_VACIO = {
  titulo: '',
  descripcion: '',
  prioridad: 'MEDIA' as PrioridadTarea,
  area: '',
  asignado_a: '',
  fecha_vencimiento: '',
  entidad_tipo: '',
  entidad_id: '',
};

const TableroKanbanTab: React.FC<TableroKanbanTabProps> = ({ empresaId }) => {
  const qc = useQueryClient();
  const [proyectoIdSel, setProyectoIdSel] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState('');
  const [dialogNueva, setDialogNueva] = useState(false);
  const [form, setForm] = useState(FORM_NUEVA_VACIO);
  const [detalleTarea, setDetalleTarea] = useState<Tarea | null>(null);

  const { data: proyectos = [], isLoading: cargandoProyectos } = useQuery({
    queryKey: tareasKeys.proyectos(empresaId, false),
    queryFn: () => proyectosTareasService.getAll(false),
  });

  const { data: areas = [] } = useQuery({
    queryKey: tareasKeys.areas(empresaId),
    queryFn: () => areasTareasService.getAll(),
  });

  const { data: usuarios = [] } = useQuery({
    queryKey: ['core', 'usuarios', empresaId ?? null],
    queryFn: () => fetchUsuarios(empresaId ?? undefined),
  });

  const proyectoActivo: Proyecto | null = useMemo(() => {
    if (proyectos.length === 0) return null;
    if (proyectoIdSel) {
      return proyectos.find((p) => p.id_proyecto === proyectoIdSel) ?? proyectos.at(0) ?? null;
    }
    return proyectos.at(0) ?? null;
  }, [proyectos, proyectoIdSel]);

  const idActivo = proyectoActivo?.id_proyecto ?? '';

  const { data: tareas = [], isLoading: cargandoTareas } = useQuery({
    queryKey: tareasKeys.items(empresaId, { proyecto: idActivo }),
    queryFn: () => tareasService.getAll({ proyecto: idActivo }),
    enabled: Boolean(idActivo),
  });

  const porSeccion = useMemo(() => {
    const mapa = new Map<string, Tarea[]>();
    if (!proyectoActivo) return mapa;
    for (const sec of proyectoActivo.secciones) {
      mapa.set(sec.id_seccion, []);
    }
    const primeraId = proyectoActivo.secciones.at(0)?.id_seccion ?? '';
    for (const t of tareas) {
      const clave = t.seccion && mapa.has(t.seccion) ? t.seccion : primeraId;
      if (clave) {
        const arr = mapa.get(clave);
        if (arr) arr.push(t);
      }
    }
    return mapa;
  }, [proyectoActivo, tareas]);

  const invalidarTodo = () => {
    void qc.invalidateQueries({ queryKey: tareasKeys.porEmpresa(empresaId) });
  };

  const asegurarPersonal = useMutation({
    mutationFn: () => proyectosTareasService.miTablero(),
    onSuccess: (proy) => {
      setErrorMsg('');
      setProyectoIdSel(proy.id_proyecto);
      invalidarTodo();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo inicializar tu tablero personal.'));
    },
  });

  const crearTarea = useMutation({
    mutationFn: () =>
      tareasService.create({
        titulo: form.titulo.trim(),
        descripcion: form.descripcion.trim(),
        prioridad: form.prioridad,
        proyecto: idActivo || undefined,
        area: form.area || undefined,
        asignado_a: form.asignado_a || undefined,
        fecha_vencimiento: form.fecha_vencimiento || undefined,
        entidad_tipo: form.entidad_tipo.trim() || undefined,
        entidad_id: form.entidad_id.trim() || undefined,
      }),
    onSuccess: () => {
      setDialogNueva(false);
      setForm(FORM_NUEVA_VACIO);
      setErrorMsg('');
      invalidarTodo();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo crear la tarea.'));
    },
  });

  const moverTarjeta = useMutation({
    mutationFn: (p: { tareaId: string; seccionId: string }) =>
      tareasService.mover(p.tareaId, p.seccionId),
    onSuccess: () => {
      setErrorMsg('');
      invalidarTodo();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo mover la tarea de columna.'));
    },
  });

  const completarRapido = useMutation({
    mutationFn: (tareaId: string) => tareasService.cambiarEstado(tareaId, 'COMPLETADA'),
    onSuccess: () => {
      setErrorMsg('');
      invalidarTodo();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo completar la tarea.'));
    },
  });

  return (
    <Box>
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        alignItems={{ sm: 'center' }}
        justifyContent="space-between"
        sx={{ mb: 2.5 }}
      >
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <TextField
            select
            size="small"
            label="Proyecto / Tablero"
            value={idActivo}
            onChange={(ev) => setProyectoIdSel(ev.target.value)}
            sx={{ minWidth: 260 }}
            disabled={proyectos.length === 0}
          >
            {proyectos.map((p) => (
              <MenuItem key={p.id_proyecto} value={p.id_proyecto}>
                {p.nombre} {p.es_personal ? '· Personal' : ''}
              </MenuItem>
            ))}
          </TextField>
          <Button
            variant="outlined"
            disabled={asegurarPersonal.isPending}
            onClick={() => asegurarPersonal.mutate()}
          >
            Mi tablero personal
          </Button>
        </Stack>

        <Button
          variant="contained"
          onClick={() => {
            setErrorMsg('');
            setDialogNueva(true);
          }}
        >
          Nueva tarea
        </Button>
      </Stack>

      {cargandoProyectos ? (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <CircularProgress size={28} />
        </Box>
      ) : !proyectoActivo ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="subtitle1" gutterBottom>
            Aún no tienes tableros activos en esta empresa.
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Inicializa tu tablero personal con las 5 columnas estándar o crea un proyecto de área.
          </Typography>
          <Button
            variant="contained"
            disabled={asegurarPersonal.isPending}
            onClick={() => asegurarPersonal.mutate()}
          >
            Inicializar mi tablero personal
          </Button>
        </Paper>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: 2,
            alignItems: 'start',
          }}
        >
          {proyectoActivo.secciones.map((sec) => {
            const tarjetas = porSeccion.get(sec.id_seccion) ?? [];
            return (
              <Paper
                key={sec.id_seccion}
                variant="outlined"
                sx={{ p: 1.5, bgcolor: 'background.default', minHeight: 280 }}
              >
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                  sx={{ mb: 1.5 }}
                >
                  <Typography variant="subtitle2" fontWeight={700}>
                    {sec.nombre}
                  </Typography>
                  <Chip size="small" label={tarjetas.length} />
                </Stack>

                {cargandoTareas ? (
                  <CircularProgress size={20} />
                ) : tarjetas.length === 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    Sin tareas en esta columna.
                  </Typography>
                ) : (
                  <Stack spacing={1.25}>
                    {tarjetas.map((t) => {
                      const vencida = esTareaVencida(t);
                      return (
                        <Card key={t.id_tarea} variant="outlined">
                          <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                            <Stack
                              direction="row"
                              justifyContent="space-between"
                              alignItems="center"
                              sx={{ mb: 0.75 }}
                            >
                              <StatusChip
                                value={t.prioridad}
                                label={etiquetaPrioridadTarea(t.prioridad)}
                                colorMap={PRIORIDAD_TAREA_COLOR}
                              />
                              {t.bloqueada_por_escalacion && (
                                <Chip size="small" color="error" label="72h+" />
                              )}
                            </Stack>

                            <Typography
                              variant="body2"
                              fontWeight={600}
                              sx={{ mb: 0.75, cursor: 'pointer' }}
                              onClick={() => setDetalleTarea(t)}
                            >
                              {t.titulo}
                            </Typography>

                            <Stack
                              direction="row"
                              spacing={0.5}
                              flexWrap="wrap"
                              useFlexGap
                              sx={{ mb: 1 }}
                            >
                              {t.asignado_nombre && (
                                <Chip size="small" variant="outlined" label={t.asignado_nombre} />
                              )}
                              {t.area_nombre && (
                                <Chip size="small" variant="outlined" label={t.area_nombre} />
                              )}
                              {t.fecha_vencimiento && (
                                <Chip
                                  size="small"
                                  color={vencida ? 'error' : 'default'}
                                  variant={vencida ? 'filled' : 'outlined'}
                                  label={t.fecha_vencimiento}
                                />
                              )}
                              {t.entidad_tipo && (
                                <Chip size="small" color="primary" label={t.entidad_tipo} />
                              )}
                            </Stack>

                            <Stack direction="row" spacing={1} alignItems="center">
                              <TextField
                                select
                                size="small"
                                label="Mover a"
                                value={t.seccion ?? sec.id_seccion}
                                onChange={(ev) =>
                                  moverTarjeta.mutate({
                                    tareaId: t.id_tarea,
                                    seccionId: ev.target.value,
                                  })
                                }
                                sx={{ flexGrow: 1 }}
                              >
                                {proyectoActivo.secciones.map((dest) => (
                                  <MenuItem key={dest.id_seccion} value={dest.id_seccion}>
                                    {dest.nombre}
                                  </MenuItem>
                                ))}
                              </TextField>
                              {t.estado !== 'COMPLETADA' && (
                                <Button
                                  size="small"
                                  color="success"
                                  onClick={() => completarRapido.mutate(t.id_tarea)}
                                >
                                  Listo
                                </Button>
                              )}
                              <Button size="small" onClick={() => setDetalleTarea(t)}>
                                Detalle
                              </Button>
                            </Stack>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </Stack>
                )}
              </Paper>
            );
          })}
        </Box>
      )}

      {/* Diálogo Nueva Tarea */}
      <Dialog open={dialogNueva} onClose={() => setDialogNueva(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Nueva tarea operativa</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Título"
              required
              fullWidth
              value={form.titulo}
              onChange={(ev) => setForm({ ...form, titulo: ev.target.value })}
            />
            <TextField
              label="Descripción"
              multiline
              minRows={2}
              fullWidth
              value={form.descripcion}
              onChange={(ev) => setForm({ ...form, descripcion: ev.target.value })}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <TextField
                select
                label="Prioridad"
                fullWidth
                value={form.prioridad}
                onChange={(ev) =>
                  setForm({ ...form, prioridad: ev.target.value as PrioridadTarea })
                }
              >
                {PRIORIDADES_TAREA.map((p) => (
                  <MenuItem key={p} value={p}>
                    {etiquetaPrioridadTarea(p)}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Fecha de vencimiento"
                type="date"
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
                value={form.fecha_vencimiento}
                onChange={(ev) => setForm({ ...form, fecha_vencimiento: ev.target.value })}
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <TextField
                select
                label="Área operativa"
                fullWidth
                value={form.area}
                onChange={(ev) => setForm({ ...form, area: ev.target.value })}
              >
                <MenuItem value="">Sin área</MenuItem>
                {areas.map((a) => (
                  <MenuItem key={a.id_area} value={a.id_area}>
                    {a.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Responsable"
                fullWidth
                value={form.asignado_a}
                onChange={(ev) => setForm({ ...form, asignado_a: ev.target.value })}
              >
                <MenuItem value="">Sin asignar</MenuItem>
                {usuarios.map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    {`${u.first_name} ${u.last_name}`.trim() || u.username}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <TextField
                label="Tipo entidad ERP (opcional)"
                placeholder="p. ej. cxc.factura, ventas.pedido"
                fullWidth
                value={form.entidad_tipo}
                onChange={(ev) => setForm({ ...form, entidad_tipo: ev.target.value })}
              />
              <TextField
                label="UUID entidad ERP (opcional)"
                fullWidth
                value={form.entidad_id}
                onChange={(ev) => setForm({ ...form, entidad_id: ev.target.value })}
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogNueva(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!form.titulo.trim() || crearTarea.isPending}
            onClick={() => crearTarea.mutate()}
          >
            Guardar tarea
          </Button>
        </DialogActions>
      </Dialog>

      <TareaDetalleDialog
        empresaId={empresaId}
        tarea={detalleTarea}
        candidatasDependencia={tareas}
        onClose={() => setDetalleTarea(null)}
      />
    </Box>
  );
};

export default TableroKanbanTab;
