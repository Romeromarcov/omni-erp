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
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { StatusChip } from '../../components/ui';
import {
  tareasService,
  type EstadoTarea,
  type Tarea,
} from '../../services/tareasService';
import { tareasKeys } from '../../lib/queryKeys';
import {
  ESTADO_TAREA_COLOR,
  PRIORIDAD_TAREA_COLOR,
  etiquetaEstadoTarea,
  etiquetaOrigenTarea,
  etiquetaPrioridadTarea,
  mensajeTareas,
} from './utils';

interface TareaDetalleDialogProps {
  empresaId: string | null;
  tarea: Tarea | null;
  candidatasDependencia?: Tarea[];
  onClose: () => void;
}

const TareaDetalleDialog: React.FC<TareaDetalleDialogProps> = ({
  empresaId,
  tarea,
  candidatasDependencia = [],
  onClose,
}) => {
  const qc = useQueryClient();
  const [nuevoComentario, setNuevoComentario] = useState('');
  const [motivoBloqueo, setMotivoBloqueo] = useState('');
  const [dependeDeId, setDependeDeId] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const tareaId = tarea?.id_tarea ?? '';

  const { data: tareaFresca } = useQuery({
    queryKey: tareasKeys.item(empresaId, tareaId),
    queryFn: () => tareasService.getById(tareaId),
    enabled: Boolean(tareaId),
    initialData: tarea ?? undefined,
  });

  const actual = tareaFresca ?? tarea;

  const { data: comentarios = [] } = useQuery({
    queryKey: tareasKeys.comentarios(empresaId, tareaId),
    queryFn: () => tareasService.listarComentarios(tareaId),
    enabled: Boolean(tareaId),
  });

  const { data: dependencias = [] } = useQuery({
    queryKey: tareasKeys.dependencias(empresaId, tareaId),
    queryFn: () => tareasService.listarDependencias(tareaId),
    enabled: Boolean(tareaId),
  });

  const invalidarFamilia = () => {
    void qc.invalidateQueries({ queryKey: tareasKeys.porEmpresa(empresaId) });
  };

  const cambiarEstado = useMutation({
    mutationFn: (p: { estado: EstadoTarea; motivo?: string }) =>
      tareasService.cambiarEstado(tareaId, p.estado, p.motivo ?? ''),
    onSuccess: () => {
      setErrorMsg('');
      setMotivoBloqueo('');
      invalidarFamilia();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo actualizar el estado de la tarea.'));
    },
  });

  const comentar = useMutation({
    mutationFn: (cuerpo: string) => tareasService.agregarComentario(tareaId, cuerpo),
    onSuccess: () => {
      setErrorMsg('');
      setNuevoComentario('');
      void qc.invalidateQueries({ queryKey: tareasKeys.comentarios(empresaId, tareaId) });
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo publicar el comentario.'));
    },
  });

  const vincularDependencia = useMutation({
    mutationFn: (depId: string) => tareasService.agregarDependencia(tareaId, depId),
    onSuccess: () => {
      setErrorMsg('');
      setDependeDeId('');
      void qc.invalidateQueries({ queryKey: tareasKeys.dependencias(empresaId, tareaId) });
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo registrar la dependencia.'));
    },
  });

  if (!actual) return null;

  const opcionesDep = candidatasDependencia.filter((t) => t.id_tarea !== actual.id_tarea);

  return (
    <Dialog open={Boolean(tarea)} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="h6" component="span" sx={{ flexGrow: 1 }}>
            {actual.titulo}
          </Typography>
          <StatusChip
            value={actual.estado}
            label={etiquetaEstadoTarea(actual.estado)}
            colorMap={ESTADO_TAREA_COLOR}
          />
          <StatusChip
            value={actual.prioridad}
            label={etiquetaPrioridadTarea(actual.prioridad)}
            colorMap={PRIORIDAD_TAREA_COLOR}
          />
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        {errorMsg && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
            {errorMsg}
          </Alert>
        )}

        {actual.descripcion && (
          <Typography variant="body2" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>
            {actual.descripcion}
          </Typography>
        )}

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
          <Chip size="small" variant="outlined" label={`Origen: ${etiquetaOrigenTarea(actual.origen)}`} />
          {actual.proyecto_nombre && (
            <Chip size="small" variant="outlined" label={`Proyecto: ${actual.proyecto_nombre}`} />
          )}
          {actual.seccion_nombre && (
            <Chip size="small" variant="outlined" label={`Sección: ${actual.seccion_nombre}`} />
          )}
          {actual.area_nombre && (
            <Chip size="small" variant="outlined" label={`Área: ${actual.area_nombre}`} />
          )}
          <Chip
            size="small"
            variant="outlined"
            label={`Responsable: ${actual.asignado_nombre || 'Sin asignar'}`}
          />
          {actual.fecha_vencimiento && (
            <Chip size="small" variant="outlined" label={`Vence: ${actual.fecha_vencimiento}`} />
          )}
          {actual.entidad_tipo && (
            <Chip
              size="small"
              color="primary"
              variant="outlined"
              label={`Vínculo ERP: ${actual.entidad_tipo}${actual.entidad_id ? ` (${actual.entidad_id.slice(0, 8)})` : ''}`}
            />
          )}
          {actual.bloqueada_por_escalacion && (
            <Chip size="small" color="error" label="Bloqueada por escalación > 72h" />
          )}
        </Stack>

        {actual.motivo_bloqueo && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Motivo de bloqueo: {actual.motivo_bloqueo}
          </Alert>
        )}

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mb: 2 }}>
          {actual.estado !== 'EN_EJECUCION' && (
            <Button
              size="small"
              variant="outlined"
              disabled={cambiarEstado.isPending}
              onClick={() => cambiarEstado.mutate({ estado: 'EN_EJECUCION' })}
            >
              Iniciar ejecución
            </Button>
          )}
          {actual.estado !== 'EN_REVISION' && (
            <Button
              size="small"
              variant="outlined"
              disabled={cambiarEstado.isPending}
              onClick={() => cambiarEstado.mutate({ estado: 'EN_REVISION' })}
            >
              Pasar a revisión
            </Button>
          )}
          {actual.estado !== 'COMPLETADA' && (
            <Button
              size="small"
              variant="contained"
              color="success"
              disabled={cambiarEstado.isPending}
              onClick={() => cambiarEstado.mutate({ estado: 'COMPLETADA' })}
            >
              Marcar completada
            </Button>
          )}
          <TextField
            size="small"
            label="Motivo de bloqueo"
            value={motivoBloqueo}
            onChange={(ev) => setMotivoBloqueo(ev.target.value)}
            sx={{ minWidth: 200 }}
          />
          <Button
            size="small"
            color="error"
            variant="outlined"
            disabled={cambiarEstado.isPending}
            onClick={() => cambiarEstado.mutate({ estado: 'BLOQUEADA', motivo: motivoBloqueo })}
          >
            Bloquear tarea
          </Button>
        </Stack>

        <Divider sx={{ my: 2 }} />

        {/* Dependencias */}
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Dependencias ({dependencias.length})
        </Typography>
        {dependencias.length > 0 && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
            {dependencias.map((dep) => (
              <Chip
                key={dep.id_dependencia}
                size="small"
                label={`Depende de: ${dep.depende_de_titulo} (${etiquetaEstadoTarea(dep.depende_de_estado)})`}
              />
            ))}
          </Stack>
        )}
        {opcionesDep.length > 0 && (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
            <TextField
              select
              size="small"
              label="Agregar dependencia"
              value={dependeDeId}
              onChange={(ev) => setDependeDeId(ev.target.value)}
              sx={{ minWidth: 260 }}
            >
              <MenuItem value="">Seleccionar tarea previa…</MenuItem>
              {opcionesDep.map((op) => (
                <MenuItem key={op.id_tarea} value={op.id_tarea}>
                  {op.titulo}
                </MenuItem>
              ))}
            </TextField>
            <Button
              size="small"
              variant="outlined"
              disabled={!dependeDeId || vincularDependencia.isPending}
              onClick={() => vincularDependencia.mutate(dependeDeId)}
            >
              Vincular
            </Button>
          </Stack>
        )}

        <Divider sx={{ my: 2 }} />

        {/* Comentarios */}
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Bitácora y comentarios ({comentarios.length})
        </Typography>
        <Box sx={{ maxHeight: 220, overflowY: 'auto', mb: 1.5 }}>
          {comentarios.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Aún no hay comentarios registrados en esta tarea.
            </Typography>
          ) : (
            <Stack spacing={1}>
              {comentarios.map((c) => (
                <Box
                  key={c.id_comentario}
                  sx={{
                    p: 1.25,
                    borderRadius: 1,
                    bgcolor: c.es_sistema ? 'action.hover' : 'background.paper',
                    border: 1,
                    borderColor: 'divider',
                  }}
                >
                  <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.25 }}>
                    <Typography variant="caption" fontWeight={700}>
                      {c.autor_nombre || (c.es_sistema ? 'Sistema' : 'Colaborador')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {new Date(c.fecha_creacion).toLocaleString('es-VE')}
                    </Typography>
                  </Stack>
                  <Typography variant="body2">{c.cuerpo}</Typography>
                </Box>
              ))}
            </Stack>
          )}
        </Box>
        <Stack direction="row" spacing={1}>
          <TextField
            size="small"
            fullWidth
            label="Nuevo comentario"
            value={nuevoComentario}
            onChange={(ev) => setNuevoComentario(ev.target.value)}
          />
          <Button
            variant="contained"
            disabled={!nuevoComentario.trim() || comentar.isPending}
            onClick={() => comentar.mutate(nuevoComentario.trim())}
          >
            Comentar
          </Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  );
};

export default TareaDetalleDialog;
