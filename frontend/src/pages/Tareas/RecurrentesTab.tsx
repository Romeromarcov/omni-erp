import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  areasTareasService,
  FRECUENCIAS_RECURRENTES,
  PRIORIDADES_TAREA,
  proyectosTareasService,
  recurrentesTareasService,
  type FrecuenciaRecurrente,
  type PlantillaTareaRecurrente,
  type PrioridadTarea,
} from '../../services/tareasService';
import { fetchUsuarios } from '../../services/users';
import { tareasKeys } from '../../lib/queryKeys';
import {
  DIAS_SEMANA_OPCIONES,
  PRIORIDAD_TAREA_COLOR,
  etiquetaFrecuencia,
  etiquetaPrioridadTarea,
  mensajeTareas,
} from './utils';

interface RecurrentesTabProps {
  empresaId: string | null;
}

const FORM_RECURRENTE_VACIO = {
  titulo: '',
  descripcion: '',
  prioridad: 'MEDIA' as PrioridadTarea,
  frecuencia: 'SEMANAL' as FrecuenciaRecurrente,
  proxima_ejecucion: '',
  dia_mes: '',
  horas_dia_csv: '09:00, 15:00',
  dias_semana: [0] as number[],
  proyecto: '',
  area: '',
  asignado_a: '',
};

const RecurrentesTab: React.FC<RecurrentesTabProps> = ({ empresaId }) => {
  const qc = useQueryClient();
  const [dialogAbierto, setDialogAbierto] = useState(false);
  const [form, setForm] = useState(FORM_RECURRENTE_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const { data: plantillas = [], isLoading } = useQuery({
    queryKey: tareasKeys.recurrentes(empresaId),
    queryFn: () => recurrentesTareasService.getAll(),
  });

  const { data: proyectos = [] } = useQuery({
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

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: tareasKeys.porEmpresa(empresaId) });
  };

  const crearPlantilla = useMutation({
    mutationFn: () => {
      const horas =
        form.frecuencia === 'INTRADIA'
          ? form.horas_dia_csv
              .split(',')
              .map((h) => h.trim())
              .filter(Boolean)
          : [];
      const dias = form.frecuencia === 'SEMANAL' ? form.dias_semana : [];
      const diaMes =
        form.frecuencia === 'MENSUAL' && form.dia_mes ? Number(form.dia_mes) : null;
      return recurrentesTareasService.create({
        titulo: form.titulo.trim(),
        descripcion: form.descripcion.trim(),
        prioridad: form.prioridad,
        frecuencia: form.frecuencia,
        proxima_ejecucion: form.proxima_ejecucion,
        dias_semana: dias,
        dia_mes: diaMes,
        horas_dia: horas,
        proyecto: form.proyecto || undefined,
        area: form.area || undefined,
        asignado_a: form.asignado_a || undefined,
      });
    },
    onSuccess: () => {
      setDialogAbierto(false);
      setForm(FORM_RECURRENTE_VACIO);
      setErrorMsg('');
      setInfoMsg('Plantilla recurrente registrada.');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo registrar la plantilla recurrente.'));
    },
  });

  const materializar = useMutation({
    mutationFn: () => recurrentesTareasService.materializar(),
    onSuccess: (res) => {
      setErrorMsg('');
      setInfoMsg(
        `Ejecución del ${res.fecha}: ${res.tareas_creadas} creadas, ${res.omitidas_idempotencia} omitidas por idempotencia.`,
      );
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudieron materializar las tareas recurrentes.'));
    },
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => recurrentesTareasService.remove(id),
    onSuccess: () => {
      setErrorMsg('');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo desactivar la plantilla recurrente.'));
    },
  });

  const alternarDiaSemana = (dia: number) => {
    setForm((prev) => ({
      ...prev,
      dias_semana: prev.dias_semana.includes(dia)
        ? prev.dias_semana.filter((d) => d !== dia)
        : [...prev.dias_semana, dia].sort((a, b) => a - b),
    }));
  };

  const columns: Column<PlantillaTareaRecurrente>[] = [
    { key: 'titulo', header: 'Plantilla', render: (r) => r.titulo },
    {
      key: 'frecuencia',
      header: 'Frecuencia',
      render: (r) => etiquetaFrecuencia(r.frecuencia),
    },
    {
      key: 'prioridad',
      header: 'Prioridad',
      render: (r) => (
        <StatusChip
          value={r.prioridad}
          label={etiquetaPrioridadTarea(r.prioridad)}
          colorMap={PRIORIDAD_TAREA_COLOR}
        />
      ),
    },
    {
      key: 'asignado',
      header: 'Responsable',
      render: (r) => r.asignado_nombre || 'Sin asignar',
    },
    {
      key: 'proxima',
      header: 'Próxima ejecución',
      render: (r) => r.proxima_ejecucion,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => (
        <Button
          size="small"
          color="error"
          disabled={eliminar.isPending}
          onClick={() => eliminar.mutate(r.id_plantilla_recurrente)}
        >
          Desactivar
        </Button>
      ),
    },
  ];

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
        sx={{ mb: 2.5 }}
      >
        <Button
          variant="outlined"
          disabled={materializar.isPending}
          onClick={() => materializar.mutate()}
        >
          Materializar pendientes de hoy
        </Button>
        <Button variant="contained" onClick={() => setDialogAbierto(true)}>
          Nueva recurrencia
        </Button>
      </Stack>

      <DataTable
        columns={columns}
        rows={plantillas}
        getRowKey={(r) => r.id_plantilla_recurrente}
        loading={isLoading}
        emptyMessage="No hay plantillas recurrentes activas."
      />

      <Dialog
        open={dialogAbierto}
        onClose={() => setDialogAbierto(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Nueva plantilla recurrente</DialogTitle>
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
                label="Frecuencia"
                fullWidth
                value={form.frecuencia}
                onChange={(ev) =>
                  setForm({
                    ...form,
                    frecuencia: ev.target.value as FrecuenciaRecurrente,
                  })
                }
              >
                {FRECUENCIAS_RECURRENTES.map((f) => (
                  <MenuItem key={f} value={f}>
                    {etiquetaFrecuencia(f)}
                  </MenuItem>
                ))}
              </TextField>
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
            </Stack>

            <TextField
              label="Próxima fecha de ejecución"
              type="date"
              required
              fullWidth
              slotProps={{ inputLabel: { shrink: true } }}
              value={form.proxima_ejecucion}
              onChange={(ev) => setForm({ ...form, proxima_ejecucion: ev.target.value })}
            />

            {form.frecuencia === 'SEMANAL' && (
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                {DIAS_SEMANA_OPCIONES.map((d) => {
                  const activo = form.dias_semana.includes(d.valor);
                  return (
                    <Chip
                      key={d.valor}
                      label={d.etiqueta}
                      color={activo ? 'primary' : 'default'}
                      variant={activo ? 'filled' : 'outlined'}
                      onClick={() => alternarDiaSemana(d.valor)}
                    />
                  );
                })}
              </Stack>
            )}

            {form.frecuencia === 'MENSUAL' && (
              <TextField
                label="Día del mes (1–31)"
                type="number"
                fullWidth
                value={form.dia_mes}
                onChange={(ev) => setForm({ ...form, dia_mes: ev.target.value })}
              />
            )}

            {form.frecuencia === 'INTRADIA' && (
              <TextField
                label="Horas del día (HH:MM separadas por coma)"
                fullWidth
                value={form.horas_dia_csv}
                onChange={(ev) => setForm({ ...form, horas_dia_csv: ev.target.value })}
              />
            )}

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <TextField
                select
                label="Proyecto"
                fullWidth
                value={form.proyecto}
                onChange={(ev) => setForm({ ...form, proyecto: ev.target.value })}
              >
                <MenuItem value="">Tablero personal</MenuItem>
                {proyectos.map((p) => (
                  <MenuItem key={p.id_proyecto} value={p.id_proyecto}>
                    {p.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Área"
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
            </Stack>

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
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogAbierto(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={
              !form.titulo.trim() || !form.proxima_ejecucion || crearPlantilla.isPending
            }
            onClick={() => crearPlantilla.mutate()}
          >
            Guardar recurrencia
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RecurrentesTab;
