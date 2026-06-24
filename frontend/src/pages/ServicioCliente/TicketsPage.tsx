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
  ticketsSoporteService,
  categoriasTicketService,
  interaccionesTicketService,
  ticketEstaCerrado,
  type TicketSoporte,
  type TicketSoportePayload,
  type EstadoTicket,
  type PrioridadTicket,
  type CategoriaTicket,
} from '../../services/servicioClienteService';
import { servicioClienteKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const PRIORIDAD_OPCIONES: { value: PrioridadTicket; label: string }[] = [
  { value: 'BAJA', label: 'Baja' },
  { value: 'MEDIA', label: 'Media' },
  { value: 'ALTA', label: 'Alta' },
  { value: 'URGENTE', label: 'Urgente' },
];

const ESTADO_OPCIONES: { value: EstadoTicket; label: string }[] = [
  { value: 'ABIERTO', label: 'Abierto' },
  { value: 'ASIGNADO', label: 'Asignado' },
  { value: 'EN_PROGRESO', label: 'En progreso' },
  { value: 'PENDIENTE_CLIENTE', label: 'Pendiente cliente' },
  { value: 'RESUELTO', label: 'Resuelto' },
  { value: 'CERRADO', label: 'Cerrado' },
  { value: 'ESCALADO', label: 'Escalado' },
];

// Lookups por valor sin indexación dinámica (Map evita el sink CWE de
// security/detect-object-injection y blinda contra claves especiales, CTF-006).
const PRIORIDAD_LABEL = new Map<string, string>(PRIORIDAD_OPCIONES.map((o) => [o.value, o.label]));
const ESTADO_LABEL = new Map<string, string>(ESTADO_OPCIONES.map((o) => [o.value, o.label]));

const labelPrioridad = (p: PrioridadTicket): string => PRIORIDAD_LABEL.get(p) ?? p;
const labelEstado = (s: EstadoTicket): string => ESTADO_LABEL.get(s) ?? s;

const PRIORIDAD_COLOR: Record<string, 'success' | 'info' | 'warning' | 'error' | 'default'> = {
  baja: 'success',
  media: 'info',
  alta: 'warning',
  urgente: 'error',
};

const ESTADO_COLOR: Record<string, 'warning' | 'info' | 'success' | 'error' | 'default'> = {
  abierto: 'warning',
  asignado: 'info',
  en_progreso: 'info',
  pendiente_cliente: 'warning',
  resuelto: 'success',
  cerrado: 'default',
  escalado: 'error',
};

interface FormState {
  numero_ticket: string;
  asunto: string;
  descripcion: string;
  id_categoria_ticket: string;
  prioridad: PrioridadTicket;
  estado_ticket: EstadoTicket;
}

const formVacio = (): FormState => ({
  numero_ticket: '',
  asunto: '',
  descripcion: '',
  id_categoria_ticket: '',
  prioridad: 'MEDIA',
  estado_ticket: 'ABIERTO',
});

const TicketsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState<EstadoTicket | ''>('');
  const [filtroPrioridad, setFiltroPrioridad] = useState<PrioridadTicket | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<TicketSoporte | null>(null);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<TicketSoporte | null>(null);

  const { data: tickets = [], isLoading } = useQuery({
    queryKey: servicioClienteKeys.tickets(empresaId, filtroEstado, filtroPrioridad),
    queryFn: () =>
      ticketsSoporteService.getAll({
        empresa: empresaId || undefined,
        estado: filtroEstado || undefined,
        prioridad: filtroPrioridad || undefined,
      }),
  });

  const { data: categorias = [] } = useQuery<CategoriaTicket[]>({
    queryKey: servicioClienteKeys.categoriasActivas(),
    queryFn: () => categoriasTicketService.activas(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: servicioClienteKeys.ticketsAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (t: TicketSoporte) => {
    setEditando(t);
    setForm({
      numero_ticket: t.numero_ticket,
      asunto: t.asunto,
      descripcion: t.descripcion,
      id_categoria_ticket: t.id_categoria_ticket,
      prioridad: t.prioridad,
      estado_ticket: t.estado_ticket,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: TicketSoportePayload) =>
      editando
        ? ticketsSoporteService.update(editando.id_ticket, payload)
        : ticketsSoporteService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el ticket.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => ticketsSoporteService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el ticket.')),
  });

  const handleGuardar = () => {
    if (!form.numero_ticket.trim() || !form.asunto.trim() || !form.descripcion.trim() || !form.id_categoria_ticket) {
      setErrorMsg('Complete número, categoría, asunto y descripción.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      numero_ticket: form.numero_ticket.trim(),
      asunto: form.asunto.trim(),
      descripcion: form.descripcion.trim(),
      id_categoria_ticket: form.id_categoria_ticket,
      prioridad: form.prioridad,
      estado_ticket: form.estado_ticket,
      id_cliente_temp: null,
      id_agente_asignado_temp: null,
      sla_vencimiento: null,
    });
  };

  const handleEliminar = (t: TicketSoporte) => {
    if (window.confirm(`¿Eliminar el ticket "${t.numero_ticket}"?`)) {
      eliminar.mutate(t.id_ticket);
    }
  };

  const nombreCategoria = (id: string) =>
    categorias.find((c) => c.id_categoria_ticket === id)?.nombre_categoria ?? '—';

  const columns: Column<TicketSoporte>[] = [
    { key: 'numero_ticket', header: 'Número', render: (t) => t.numero_ticket },
    { key: 'asunto', header: 'Asunto', render: (t) => t.asunto },
    {
      key: 'id_categoria_ticket',
      header: 'Categoría',
      render: (t) => nombreCategoria(t.id_categoria_ticket),
    },
    {
      key: 'prioridad',
      header: 'Prioridad',
      render: (t) => (
        <StatusChip value={t.prioridad} label={labelPrioridad(t.prioridad)} colorMap={PRIORIDAD_COLOR} />
      ),
    },
    {
      key: 'estado_ticket',
      header: 'Estado',
      render: (t) => (
        <StatusChip value={t.estado_ticket} label={labelEstado(t.estado_ticket)} colorMap={ESTADO_COLOR} />
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (t) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(t)}>
            Detalle
          </Button>
          <Button size="small" onClick={() => abrirEditar(t)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(t)}
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
        title="Tickets de soporte"
        subtitle="Mesa de ayuda: registro, seguimiento y resolución de tickets de soporte."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo ticket
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
          onChange={(e) => setFiltroEstado(e.target.value as EstadoTicket | '')}
          size="small"
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADO_OPCIONES.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Prioridad"
          value={filtroPrioridad}
          onChange={(e) => setFiltroPrioridad(e.target.value as PrioridadTicket | '')}
          size="small"
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {PRIORIDAD_OPCIONES.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <DataTable
        columns={columns}
        rows={tickets}
        getRowKey={(t) => t.id_ticket}
        loading={isLoading}
        emptyMessage="Sin tickets. Registra el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar ticket' : 'Nuevo ticket'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Número de ticket"
              value={form.numero_ticket}
              onChange={(e) => setForm((f) => ({ ...f, numero_ticket: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Categoría"
              value={form.id_categoria_ticket}
              onChange={(e) => setForm((f) => ({ ...f, id_categoria_ticket: e.target.value }))}
              required
              fullWidth
            >
              {categorias.map((c) => (
                <MenuItem key={c.id_categoria_ticket} value={c.id_categoria_ticket}>
                  {c.nombre_categoria}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Asunto"
              value={form.asunto}
              onChange={(e) => setForm((f) => ({ ...f, asunto: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
              required
              multiline
              minRows={3}
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                select
                label="Prioridad"
                value={form.prioridad}
                onChange={(e) => setForm((f) => ({ ...f, prioridad: e.target.value as PrioridadTicket }))}
                fullWidth
              >
                {PRIORIDAD_OPCIONES.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Estado"
                value={form.estado_ticket}
                onChange={(e) => setForm((f) => ({ ...f, estado_ticket: e.target.value as EstadoTicket }))}
                fullWidth
              >
                {ESTADO_OPCIONES.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
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
          <DetalleTicketDrawer
            ticket={detalle}
            categoriaNombre={nombreCategoria(detalle.id_categoria_ticket)}
            onClose={() => setDetalle(null)}
            onMutated={(actualizado) => {
              setDetalle(actualizado);
              invalidate();
            }}
          />
        )}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle del ticket: timeline + acciones gated ─────────────────────────────

interface DetalleTicketDrawerProps {
  ticket: TicketSoporte;
  categoriaNombre: string;
  onClose: () => void;
  onMutated: (t: TicketSoporte) => void;
}

const DetalleTicketDrawer: React.FC<DetalleTicketDrawerProps> = ({
  ticket,
  categoriaNombre,
  onClose,
  onMutated,
}) => {
  const queryClient = useQueryClient();
  const [comentario, setComentario] = useState('');
  const [agenteId, setAgenteId] = useState('');
  const [nuevoEstado, setNuevoEstado] = useState<EstadoTicket>(ticket.estado_ticket);
  const [comentarioEstado, setComentarioEstado] = useState('');
  const [razonEscalar, setRazonEscalar] = useState('');
  const [error, setError] = useState('');

  const cerrado = ticketEstaCerrado(ticket.estado_ticket);

  const { data: interacciones = [] } = useQuery({
    queryKey: servicioClienteKeys.interacciones(ticket.id_ticket),
    queryFn: () => interaccionesTicketService.getAll({ ticket: ticket.id_ticket }),
  });

  const invalidarInteracciones = () =>
    queryClient.invalidateQueries({
      queryKey: servicioClienteKeys.interacciones(ticket.id_ticket),
    });

  const comentar = useMutation({
    mutationFn: () => interaccionesTicketService.agregarComentario(ticket.id_ticket, comentario.trim()),
    onSuccess: () => {
      setComentario('');
      invalidarInteracciones();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo agregar el comentario.')),
  });

  const asignar = useMutation({
    mutationFn: () => ticketsSoporteService.asignarAgente(ticket.id_ticket, agenteId.trim()),
    onSuccess: (t) => {
      setAgenteId('');
      invalidarInteracciones();
      onMutated(t);
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo asignar el agente.')),
  });

  const cambiarEstado = useMutation({
    mutationFn: () =>
      ticketsSoporteService.cambiarEstado(ticket.id_ticket, nuevoEstado, comentarioEstado.trim() || undefined),
    onSuccess: (t) => {
      setComentarioEstado('');
      invalidarInteracciones();
      onMutated(t);
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo cambiar el estado.')),
  });

  const escalar = useMutation({
    mutationFn: () => ticketsSoporteService.escalar(ticket.id_ticket, { razon: razonEscalar.trim() || undefined }),
    onSuccess: (t) => {
      setRazonEscalar('');
      invalidarInteracciones();
      onMutated(t);
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo escalar el ticket.')),
  });

  const handleAsignar = () => {
    if (!agenteId.trim()) {
      setError('Indique el ID del agente.');
      return;
    }
    asignar.mutate();
  };

  const handleComentar = () => {
    if (!comentario.trim()) {
      setError('Escriba un comentario.');
      return;
    }
    comentar.mutate();
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">Ticket {ticket.numero_ticket}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="subtitle1">{ticket.asunto}</Typography>
      <Typography variant="body2" color="text.secondary">
        {ticket.descripcion}
      </Typography>
      <Stack direction="row" spacing={1}>
        <StatusChip value={ticket.prioridad} label={labelPrioridad(ticket.prioridad)} colorMap={PRIORIDAD_COLOR} />
        <StatusChip value={ticket.estado_ticket} label={labelEstado(ticket.estado_ticket)} colorMap={ESTADO_COLOR} />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Categoría: {categoriaNombre}
        {ticket.id_agente_asignado_temp ? ` · Agente: ${ticket.id_agente_asignado_temp}` : ''}
      </Typography>

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Divider />

      {/* Acciones del workflow (gated según estado) */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Acciones
        </Typography>
        {cerrado ? (
          <Typography variant="caption" color="text.secondary">
            El ticket está cerrado: no admite más acciones.
          </Typography>
        ) : (
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                label="ID del agente"
                value={agenteId}
                onChange={(e) => setAgenteId(e.target.value)}
                size="small"
                fullWidth
              />
              <Button
                variant="outlined"
                onClick={handleAsignar}
                disabled={asignar.isPending}
              >
                Asignar agente
              </Button>
            </Stack>

            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                select
                label="Nuevo estado"
                value={nuevoEstado}
                onChange={(e) => setNuevoEstado(e.target.value as EstadoTicket)}
                size="small"
                sx={{ minWidth: 180 }}
              >
                {ESTADO_OPCIONES.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Comentario"
                value={comentarioEstado}
                onChange={(e) => setComentarioEstado(e.target.value)}
                size="small"
                fullWidth
              />
              <Button
                variant="outlined"
                onClick={() => cambiarEstado.mutate()}
                disabled={cambiarEstado.isPending}
              >
                Cambiar estado
              </Button>
            </Stack>

            {ticket.estado_ticket !== 'ESCALADO' && (
              <Stack direction="row" spacing={1} alignItems="flex-start">
                <TextField
                  label="Razón de escalamiento"
                  value={razonEscalar}
                  onChange={(e) => setRazonEscalar(e.target.value)}
                  size="small"
                  fullWidth
                />
                <Button
                  variant="outlined"
                  color="error"
                  onClick={() => escalar.mutate()}
                  disabled={escalar.isPending}
                >
                  Escalar
                </Button>
              </Stack>
            )}
          </Stack>
        )}
      </Box>

      <Divider />

      {/* Timeline de interacciones */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Historial de interacciones
        </Typography>
        <Stack spacing={1} sx={{ mb: 2 }}>
          {interacciones.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Sin interacciones todavía.
            </Typography>
          ) : (
            interacciones.map((i) => (
              <Box key={i.id_interaccion} sx={{ borderLeft: '2px solid', borderColor: 'divider', pl: 1.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {i.tipo_interaccion}
                  {i.fecha_hora_interaccion ? ` · ${i.fecha_hora_interaccion}` : ''}
                </Typography>
                <Typography variant="body2">{i.contenido}</Typography>
              </Box>
            ))
          )}
        </Stack>
        <Stack spacing={1}>
          <TextField
            label="Agregar comentario"
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            size="small"
            multiline
            minRows={2}
            fullWidth
          />
          <Box>
            <Button variant="contained" size="small" onClick={handleComentar} disabled={comentar.isPending}>
              Agregar comentario
            </Button>
          </Box>
        </Stack>
      </Box>
    </Stack>
  );
};

export default TicketsPage;
