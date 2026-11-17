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
  DialogContentText,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  areasTareasService,
  ESTADOS_TAREA,
  PRIORIDADES_TAREA,
  tareasService,
  type EstadoTarea,
  type PrioridadTarea,
  type Tarea,
} from '../../services/tareasService';
import { tareasKeys } from '../../lib/queryKeys';
import TareaDetalleDialog from './TareaDetalleDialog';
import {
  ESTADO_TAREA_COLOR,
  PRIORIDAD_TAREA_COLOR,
  esTareaVencida,
  etiquetaEstadoTarea,
  etiquetaPrioridadTarea,
  mensajeTareas,
} from './utils';

interface ListaTareasTabProps {
  empresaId: string | null;
}

const ListaTareasTab: React.FC<ListaTareasTabProps> = ({ empresaId }) => {
  const qc = useQueryClient();
  const [estado, setEstado] = useState<EstadoTarea | ''>('');
  const [prioridad, setPrioridad] = useState<PrioridadTarea | ''>('');
  const [area, setArea] = useState('');
  const [soloVencidas, setSoloVencidas] = useState(false);
  const [search, setSearch] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [detalleTarea, setDetalleTarea] = useState<Tarea | null>(null);
  const [aArchivar, setAArchivar] = useState<Tarea | null>(null);

  const { data: areas = [] } = useQuery({
    queryKey: tareasKeys.areas(empresaId),
    queryFn: () => areasTareasService.getAll(),
  });

  const { data: tareas = [], isLoading } = useQuery({
    queryKey: tareasKeys.items(empresaId, {
      estado: estado || null,
      prioridad: prioridad || null,
      area: area || null,
      vencidas: soloVencidas || null,
      search: search || null,
    }),
    queryFn: () =>
      tareasService.getAll({
        estado,
        prioridad,
        area: area || undefined,
        vencidas: soloVencidas || undefined,
        search: search || undefined,
      }),
  });

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: tareasKeys.porEmpresa(empresaId) });
  };

  const completar = useMutation({
    mutationFn: (id: string) => tareasService.cambiarEstado(id, 'COMPLETADA'),
    onSuccess: () => {
      setErrorMsg('');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo completar la tarea.'));
    },
  });

  const archivar = useMutation({
    mutationFn: (id: string) => tareasService.remove(id),
    onSuccess: () => {
      setAArchivar(null);
      setErrorMsg('');
      invalidar();
    },
    onError: (e: unknown) => {
      setAArchivar(null);
      setErrorMsg(mensajeTareas(e, 'No se pudo archivar la tarea.'));
    },
  });

  const columns: Column<Tarea>[] = [
    {
      key: 'estado',
      header: 'Estado',
      render: (t) => (
        <StatusChip
          value={t.estado}
          label={etiquetaEstadoTarea(t.estado)}
          colorMap={ESTADO_TAREA_COLOR}
        />
      ),
    },
    {
      key: 'prioridad',
      header: 'Prioridad',
      render: (t) => (
        <StatusChip
          value={t.prioridad}
          label={etiquetaPrioridadTarea(t.prioridad)}
          colorMap={PRIORIDAD_TAREA_COLOR}
        />
      ),
    },
    {
      key: 'titulo',
      header: 'Tarea',
      render: (t) => (
        <Stack spacing={0.5}>
          <Typography variant="body2" fontWeight={600}>
            {t.titulo}
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {t.entidad_tipo && (
              <Chip size="small" color="primary" variant="outlined" label={t.entidad_tipo} />
            )}
            {t.bloqueada_por_escalacion && (
              <Chip size="small" color="error" label="Escalación 72h+" />
            )}
          </Stack>
        </Stack>
      ),
    },
    {
      key: 'proyecto',
      header: 'Proyecto / Área',
      render: (t) =>
        [t.proyecto_nombre, t.area_nombre].filter(Boolean).join(' · ') || '—',
    },
    {
      key: 'asignado',
      header: 'Responsable',
      render: (t) => t.asignado_nombre || 'Sin asignar',
    },
    {
      key: 'vencimiento',
      header: 'Vencimiento',
      render: (t) => {
        if (!t.fecha_vencimiento) return '—';
        const vencida = esTareaVencida(t);
        return (
          <Typography
            variant="body2"
            color={vencida ? 'error.main' : 'text.primary'}
            fontWeight={vencida ? 700 : 400}
          >
            {t.fecha_vencimiento}
          </Typography>
        );
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (t) => (
        <Stack direction="row" spacing={0.75}>
          <Button size="small" onClick={() => setDetalleTarea(t)}>
            Detalle
          </Button>
          {t.estado !== 'COMPLETADA' && (
            <Button
              size="small"
              color="success"
              disabled={completar.isPending}
              onClick={() => completar.mutate(t.id_tarea)}
            >
              Completar
            </Button>
          )}
          <Button size="small" color="error" onClick={() => setAArchivar(t)}>
            Archivar
          </Button>
        </Stack>
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

      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.5}
        alignItems={{ md: 'center' }}
        sx={{ mb: 2.5 }}
      >
        <TextField
          size="small"
          label="Buscar tarea"
          value={search}
          onChange={(ev) => setSearch(ev.target.value)}
          sx={{ minWidth: 220 }}
        />
        <TextField
          select
          size="small"
          label="Estado"
          value={estado}
          onChange={(ev) => setEstado(ev.target.value as EstadoTarea | '')}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADOS_TAREA.map((e) => (
            <MenuItem key={e} value={e}>
              {etiquetaEstadoTarea(e)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Prioridad"
          value={prioridad}
          onChange={(ev) => setPrioridad(ev.target.value as PrioridadTarea | '')}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {PRIORIDADES_TAREA.map((p) => (
            <MenuItem key={p} value={p}>
              {etiquetaPrioridadTarea(p)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Área"
          value={area}
          onChange={(ev) => setArea(ev.target.value)}
          sx={{ minWidth: 170 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {areas.map((a) => (
            <MenuItem key={a.id_area} value={a.id_area}>
              {a.nombre}
            </MenuItem>
          ))}
        </TextField>
        <Button
          variant={soloVencidas ? 'contained' : 'outlined'}
          color={soloVencidas ? 'error' : 'inherit'}
          onClick={() => setSoloVencidas((prev) => !prev)}
        >
          Solo vencidas
        </Button>
      </Stack>

      <DataTable
        columns={columns}
        rows={tareas}
        getRowKey={(t) => t.id_tarea}
        loading={isLoading}
        emptyMessage="No hay tareas que coincidan con los filtros seleccionados."
      />

      <Dialog open={Boolean(aArchivar)} onClose={() => setAArchivar(null)}>
        <DialogTitle>Archivar tarea</DialogTitle>
        <DialogContent>
          <DialogContentText>
            ¿Deseas archivar lógicamente la tarea «{aArchivar?.titulo}»? Se conservará el rastro
            de auditoría pero dejará de mostrarse como activa.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAArchivar(null)}>Cancelar</Button>
          <Button
            color="error"
            variant="contained"
            disabled={archivar.isPending}
            onClick={() => aArchivar && archivar.mutate(aArchivar.id_tarea)}
          >
            Confirmar archivo
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

export default ListaTareasTab;
