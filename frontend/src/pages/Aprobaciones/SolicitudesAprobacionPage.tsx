import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  solicitudesAprobacionService,
  registrosAprobacionService,
  tiposAprobacionService,
  flujosAprobacionService,
  solicitudEstaCerrada,
  ESTADO_SOLICITUD_OPCIONES,
  TIPO_DECISION_OPCIONES,
  type SolicitudAprobacion,
  type SolicitudAprobacionPayload,
  type FlujoAprobacion,
  type TipoDecision,
  type EstadoSolicitud,
} from '../../services/aprobacionesService';
import { fetchUsuarios, type Usuario } from '../../services/users';
import { aprobacionesKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

// Lookups por valor sin indexación dinámica (Map evita el sink de
// security/detect-object-injection, CTF-006).
const ESTADO_LABEL = new Map<string, string>(
  ESTADO_SOLICITUD_OPCIONES.map((o) => [o.value, o.label]),
);
const labelEstado = (s: string): string => ESTADO_LABEL.get(s) ?? s;

const ESTADO_COLOR: Record<string, 'warning' | 'info' | 'success' | 'error' | 'default'> = {
  pendiente: 'warning',
  en_proceso: 'info',
  aprobada: 'success',
  rechazada: 'error',
  cancelada: 'default',
};

interface FormState {
  id_tipo_aprobacion: string;
  id_entidad_origen: string;
  nombre_modelo_origen: string;
  id_usuario_solicitante: string;
  estado_solicitud: EstadoSolicitud;
  comentarios_solicitante: string;
}

const formVacio = (): FormState => ({
  id_tipo_aprobacion: '',
  id_entidad_origen: '',
  nombre_modelo_origen: '',
  id_usuario_solicitante: '',
  estado_solicitud: 'PENDIENTE',
  comentarios_solicitante: '',
});

const SolicitudesAprobacionPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<SolicitudAprobacion | null>(null);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<SolicitudAprobacion | null>(null);

  const { data: solicitudes = [], isLoading } = useQuery({
    queryKey: aprobacionesKeys.solicitudes(null, filtroEstado || null),
    queryFn: () =>
      solicitudesAprobacionService.getAll({ estado: filtroEstado || undefined }),
  });

  const { data: tipos = [] } = useQuery({
    queryKey: aprobacionesKeys.tipos(empresaId),
    queryFn: () => tiposAprobacionService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: usuarios = [] } = useQuery({
    queryKey: ['core', 'usuarios', empresaId],
    queryFn: () => fetchUsuarios(empresaId || undefined),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprobacionesKeys.solicitudesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (s: SolicitudAprobacion) => {
    setEditando(s);
    setForm({
      id_tipo_aprobacion: s.id_tipo_aprobacion,
      id_entidad_origen: s.id_entidad_origen,
      nombre_modelo_origen: s.nombre_modelo_origen,
      id_usuario_solicitante: s.id_usuario_solicitante,
      estado_solicitud: (s.estado_solicitud as EstadoSolicitud) || 'PENDIENTE',
      comentarios_solicitante: s.comentarios_solicitante ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: SolicitudAprobacionPayload) =>
      editando
        ? solicitudesAprobacionService.update(editando.id_solicitud_aprobacion, payload)
        : solicitudesAprobacionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la solicitud.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => solicitudesAprobacionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la solicitud.')),
  });

  const handleGuardar = () => {
    if (
      !form.id_tipo_aprobacion ||
      !form.id_entidad_origen.trim() ||
      !form.nombre_modelo_origen.trim() ||
      !form.id_usuario_solicitante
    ) {
      setErrorMsg('Complete tipo, entidad de origen, modelo y solicitante.');
      return;
    }
    guardar.mutate({
      id_tipo_aprobacion: form.id_tipo_aprobacion,
      id_entidad_origen: form.id_entidad_origen.trim(),
      nombre_modelo_origen: form.nombre_modelo_origen.trim(),
      id_usuario_solicitante: form.id_usuario_solicitante,
      estado_solicitud: form.estado_solicitud,
      comentarios_solicitante: form.comentarios_solicitante.trim() || null,
      etapa_actual_flujo: editando?.etapa_actual_flujo ?? null,
    });
  };

  const handleEliminar = (s: SolicitudAprobacion) => {
    if (window.confirm('¿Eliminar esta solicitud de aprobación?')) {
      eliminar.mutate(s.id_solicitud_aprobacion);
    }
  };

  const tipoLabel = (id: string) =>
    tipos.find((t) => t.id_tipo_aprobacion === id)?.nombre_tipo ?? id;
  const usuarioLabel = (id: string) =>
    usuarios.find((u) => u.id === id)?.username ?? id;

  const columns: Column<SolicitudAprobacion>[] = [
    { key: 'tipo', header: 'Tipo', render: (s) => tipoLabel(s.id_tipo_aprobacion) },
    { key: 'nombre_modelo_origen', header: 'Modelo', render: (s) => s.nombre_modelo_origen },
    {
      key: 'id_usuario_solicitante',
      header: 'Solicitante',
      render: (s) => usuarioLabel(s.id_usuario_solicitante),
    },
    {
      key: 'estado_solicitud',
      header: 'Estado',
      render: (s) => (
        <StatusChip
          value={s.estado_solicitud}
          label={labelEstado(s.estado_solicitud)}
          colorMap={ESTADO_COLOR}
        />
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (s) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(s)}>
            Detalle
          </Button>
          <Button size="small" onClick={() => abrirEditar(s)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(s)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Solicitudes de Aprobación"
        subtitle="Aprobaciones en curso: revisa el historial de decisiones y registra aprobaciones o rechazos."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nueva solicitud
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Estado"
          value={filtroEstado}
          onChange={(e) => setFiltroEstado(e.target.value)}
          size="small"
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADO_SOLICITUD_OPCIONES.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <DataTable
        columns={columns}
        rows={solicitudes}
        getRowKey={(s) => s.id_solicitud_aprobacion}
        loading={isLoading}
        emptyMessage="Sin solicitudes de aprobación."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar solicitud' : 'Nueva solicitud'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Tipo de aprobación"
              value={form.id_tipo_aprobacion}
              onChange={(e) => setForm((f) => ({ ...f, id_tipo_aprobacion: e.target.value }))}
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {tipos.map((t) => (
                <MenuItem key={t.id_tipo_aprobacion} value={t.id_tipo_aprobacion}>
                  {t.nombre_tipo}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Modelo de origen"
              value={form.nombre_modelo_origen}
              onChange={(e) => setForm((f) => ({ ...f, nombre_modelo_origen: e.target.value }))}
              required
              helperText="P. ej. OrdenCompra, Gasto."
              fullWidth
            />
            <TextField
              label="ID de la entidad de origen"
              value={form.id_entidad_origen}
              onChange={(e) => setForm((f) => ({ ...f, id_entidad_origen: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Solicitante"
              value={form.id_usuario_solicitante}
              onChange={(e) => setForm((f) => ({ ...f, id_usuario_solicitante: e.target.value }))}
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {usuarios.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Estado"
              value={form.estado_solicitud}
              onChange={(e) =>
                setForm((f) => ({ ...f, estado_solicitud: e.target.value as EstadoSolicitud }))
              }
              fullWidth
            >
              {ESTADO_SOLICITUD_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Comentarios del solicitante"
              value={form.comentarios_solicitante}
              onChange={(e) => setForm((f) => ({ ...f, comentarios_solicitante: e.target.value }))}
              multiline
              minRows={2}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleGuardar} disabled={guardar.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={Boolean(detalle)}
        onClose={() => setDetalle(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 600 }, p: 3 } } }}
      >
        {detalle && (
          <DetalleSolicitudDrawer
            solicitud={detalle}
            tipoNombre={tipoLabel(detalle.id_tipo_aprobacion)}
            solicitanteNombre={usuarioLabel(detalle.id_usuario_solicitante)}
            usuarios={usuarios}
            onClose={() => setDetalle(null)}
            onMutated={(actualizada) => {
              setDetalle(actualizada);
              invalidate();
            }}
          />
        )}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle de la solicitud: timeline de decisiones + registrar decisión ──────

interface DetalleSolicitudDrawerProps {
  solicitud: SolicitudAprobacion;
  tipoNombre: string;
  solicitanteNombre: string;
  usuarios: Usuario[];
  onClose: () => void;
  onMutated: (s: SolicitudAprobacion) => void;
}

const DetalleSolicitudDrawer: React.FC<DetalleSolicitudDrawerProps> = ({
  solicitud,
  tipoNombre,
  solicitanteNombre,
  usuarios,
  onClose,
  onMutated,
}) => {
  const queryClient = useQueryClient();
  const [etapaId, setEtapaId] = useState('');
  const [aprobadorId, setAprobadorId] = useState('');
  const [decision, setDecision] = useState<TipoDecision>('APROBADO');
  const [comentario, setComentario] = useState('');
  const [error, setError] = useState('');

  const cerrada = solicitudEstaCerrada(solicitud.estado_solicitud);

  const { data: registros = [] } = useQuery({
    queryKey: aprobacionesKeys.registros(solicitud.id_solicitud_aprobacion),
    queryFn: () =>
      registrosAprobacionService.getAll({ solicitud: solicitud.id_solicitud_aprobacion }),
  });

  // Etapas del flujo del tipo de la solicitud (para elegir en qué etapa decide).
  const { data: etapas = [] } = useQuery<FlujoAprobacion[]>({
    queryKey: aprobacionesKeys.flujos(solicitud.id_tipo_aprobacion),
    queryFn: () => flujosAprobacionService.getAll({ tipo: solicitud.id_tipo_aprobacion }),
  });

  const invalidarRegistros = () =>
    queryClient.invalidateQueries({
      queryKey: aprobacionesKeys.registros(solicitud.id_solicitud_aprobacion),
    });

  // Registrar decisión = crear RegistroAprobacion + PATCH del estado de la
  // solicitud (no hay endpoint dedicado: se modela sobre los CRUD disponibles).
  const registrar = useMutation({
    mutationFn: async () => {
      await registrosAprobacionService.create({
        id_solicitud_aprobacion: solicitud.id_solicitud_aprobacion,
        id_flujo_aprobacion_etapa: etapaId,
        id_usuario_aprobador: aprobadorId,
        tipo_decision: decision,
        comentarios: comentario.trim() || null,
      });
      const nuevoEstado = decision === 'APROBADO' ? 'APROBADA' : 'RECHAZADA';
      return solicitudesAprobacionService.cambiarEstado(
        solicitud.id_solicitud_aprobacion,
        nuevoEstado,
      );
    },
    onSuccess: (s) => {
      setComentario('');
      setAprobadorId('');
      invalidarRegistros();
      onMutated(s);
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo registrar la decisión.')),
  });

  const handleRegistrar = () => {
    if (!etapaId) {
      setError('Seleccione la etapa del flujo.');
      return;
    }
    if (!aprobadorId) {
      setError('Seleccione el usuario aprobador.');
      return;
    }
    registrar.mutate();
  };

  const usuarioLabel = (id: string) => usuarios.find((u) => u.id === id)?.username ?? id;
  const etapaLabel = (id: string) =>
    etapas.find((e) => e.id_flujo_aprobacion === id)?.nombre_etapa ?? id;

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">Solicitud {solicitud.nombre_modelo_origen}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Stack direction="row" spacing={1}>
        <StatusChip
          value={solicitud.estado_solicitud}
          label={labelEstado(solicitud.estado_solicitud)}
          colorMap={ESTADO_COLOR}
        />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Tipo: {tipoNombre} · Solicitante: {solicitanteNombre} · Entidad: {solicitud.id_entidad_origen}
      </Typography>
      {solicitud.comentarios_solicitante && (
        <Typography variant="body2" color="text.secondary">
          {solicitud.comentarios_solicitante}
        </Typography>
      )}

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Divider />

      {/* Registrar una decisión (gated según estado terminal) */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Registrar decisión
        </Typography>
        {cerrada ? (
          <Typography variant="caption" color="text.secondary">
            La solicitud está cerrada: no admite más decisiones.
          </Typography>
        ) : (
          <Stack spacing={2}>
            <TextField
              select
              label="Etapa del flujo"
              value={etapaId}
              onChange={(e) => setEtapaId(e.target.value)}
              size="small"
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {etapas.map((e) => (
                <MenuItem key={e.id_flujo_aprobacion} value={e.id_flujo_aprobacion}>
                  {e.orden_etapa}. {e.nombre_etapa}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Usuario aprobador"
              value={aprobadorId}
              onChange={(e) => setAprobadorId(e.target.value)}
              size="small"
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {usuarios.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Decisión"
              value={decision}
              onChange={(e) => setDecision(e.target.value as TipoDecision)}
              size="small"
              fullWidth
            >
              {TIPO_DECISION_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Comentario"
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              size="small"
              multiline
              minRows={2}
              fullWidth
            />
            <Box>
              <Button
                variant="contained"
                onClick={handleRegistrar}
                disabled={registrar.isPending}
              >
                Registrar decisión
              </Button>
            </Box>
          </Stack>
        )}
      </Box>

      <Divider />

      {/* Timeline de decisiones */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Historial de decisiones
        </Typography>
        <Stack spacing={1}>
          {registros.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Sin decisiones todavía.
            </Typography>
          ) : (
            registros.map((r) => (
              <Box
                key={r.id_registro_aprobacion}
                sx={{ borderLeft: '2px solid', borderColor: 'divider', pl: 1.5 }}
              >
                <Typography variant="caption" color="text.secondary">
                  {r.tipo_decision} · {etapaLabel(r.id_flujo_aprobacion_etapa)} ·{' '}
                  {usuarioLabel(r.id_usuario_aprobador)}
                  {r.fecha_decision ? ` · ${r.fecha_decision}` : ''}
                </Typography>
                {r.comentarios && <Typography variant="body2">{r.comentarios}</Typography>}
              </Box>
            ))
          )}
        </Stack>
      </Box>
    </Stack>
  );
};

export default SolicitudesAprobacionPage;
