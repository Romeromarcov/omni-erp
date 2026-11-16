import React, { useMemo, useState } from 'react';
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
  calendariosService,
  eventosService,
  recursosService,
  ESTADOS_EVENTO,
  type EstadoEvento,
  type EventoActivacion,
} from '../../services/activacionesService';
import { activacionesKeys } from '../../lib/queryKeys';
import { formatearRango, localAISO, mensajeActivacion, textoUsos } from './utils';

const ESTADO_COLOR: Record<string, 'info' | 'success' | 'default'> = {
  programado: 'info',
  realizado: 'success',
  cancelado: 'default',
};

const ESTADO_LABEL = new Map<string, string>([
  ['PROGRAMADO', 'Programado'],
  ['REALIZADO', 'Realizado'],
  ['CANCELADO', 'Cancelado'],
]);

const FORM_VACIO = {
  calendario: '',
  cliente_nombre: '',
  vendedor_nombre: '',
  ubicacion: '',
  inicio: '',
  fin: '',
  materiales: '',
  notas: '',
};

const EventosTab: React.FC = () => {
  const qc = useQueryClient();
  const [estado, setEstado] = useState<EstadoEvento | ''>('');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [abierto, setAbierto] = useState(false);
  const [aCancelar, setACancelar] = useState<EventoActivacion | null>(null);

  const { data: eventos = [], isLoading } = useQuery({
    queryKey: activacionesKeys.eventos(estado, desde, hasta),
    queryFn: () => eventosService.getAll({ estado, desde, hasta }),
  });

  const cancelar = useMutation({
    mutationFn: (id: string) => eventosService.cancelar(id),
    onSuccess: () => {
      setACancelar(null);
      void qc.invalidateQueries({ queryKey: activacionesKeys.all() });
    },
    onError: (e: unknown) => {
      setACancelar(null);
      setErrorMsg(mensajeActivacion(e, 'No se pudo cancelar el evento.'));
    },
  });

  const columns: Column<EventoActivacion>[] = [
    {
      key: 'estado',
      header: 'Estado',
      render: (e) => (
        <StatusChip value={e.estado} label={ESTADO_LABEL.get(e.estado) ?? e.estado} colorMap={ESTADO_COLOR} />
      ),
    },
    { key: 'cliente', header: 'Cliente', render: (e) => e.cliente_nombre },
    { key: 'vendedor', header: 'Vendedor', render: (e) => e.vendedor_nombre || '—' },
    { key: 'ubicacion', header: 'Ubicación', render: (e) => e.ubicacion },
    { key: 'horario', header: 'Horario', render: (e) => formatearRango(e.inicio, e.fin) },
    { key: 'recursos', header: 'Recursos', render: (e) => textoUsos(e) },
    {
      key: 'origen',
      header: 'Origen',
      render: (e) => (
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Chip size="small" variant="outlined" label={e.origen === 'BOT' ? 'Bot' : 'Web'} />
          {e.sync_error && (
            <Chip size="small" color="warning" label="Sin sincronizar con Google" title={e.sync_error} />
          )}
        </Stack>
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (e) =>
        e.estado === 'PROGRAMADO' ? (
          <Button size="small" color="error" onClick={() => setACancelar(e)}>
            Cancelar
          </Button>
        ) : null,
    },
  ];

  return (
    <Box>
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} alignItems={{ md: 'center' }}>
        <TextField
          select
          size="small"
          label="Estado"
          value={estado}
          onChange={(e) => setEstado(e.target.value as EstadoEvento | '')}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADOS_EVENTO.map((s) => (
            <MenuItem key={s} value={s}>
              {ESTADO_LABEL.get(s) ?? s}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="date"
          label="Desde"
          value={desde}
          onChange={(e) => setDesde(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          size="small"
          type="date"
          label="Hasta"
          value={hasta}
          onChange={(e) => setHasta(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="contained" onClick={() => setAbierto(true)}>
          Nuevo evento
        </Button>
      </Stack>

      <DataTable
        columns={columns}
        rows={eventos}
        getRowKey={(e) => e.id_evento}
        loading={isLoading}
        emptyMessage="No hay eventos en el rango seleccionado."
      />

      {abierto && <NuevoEventoDialog onClose={() => setAbierto(false)} />}

      <Dialog open={aCancelar !== null} onClose={() => setACancelar(null)}>
        <DialogTitle>Cancelar evento</DialogTitle>
        <DialogContent>
          <DialogContentText>
            ¿Cancelar la activación de «{aCancelar?.cliente_nombre}»? Se liberan los recursos que usaba.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setACancelar(null)}>Volver</Button>
          <Button
            color="error"
            disabled={cancelar.isPending}
            onClick={() => aCancelar && cancelar.mutate(aCancelar.id_evento)}
          >
            Cancelar evento
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

// ── Diálogo de creación ─────────────────────────────────────────────────────

const NuevoEventoDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const qc = useQueryClient();
  const [form, setForm] = useState(FORM_VACIO);
  const [usos, setUsos] = useState<Record<string, string>>({});
  const [errorMsg, setErrorMsg] = useState('');

  const { data: calendarios = [] } = useQuery({
    queryKey: activacionesKeys.calendarios(),
    queryFn: () => calendariosService.getAll(),
  });
  const { data: recursos = [] } = useQuery({
    queryKey: activacionesKeys.recursos(),
    queryFn: () => recursosService.getAll(),
  });

  const calendarioId =
    form.calendario || calendarios.find((c) => c.es_predeterminado)?.id_calendario || calendarios[0]?.id_calendario || '';
  const recursosCal = useMemo(() => recursos.filter((r) => r.calendario === calendarioId), [recursos, calendarioId]);

  const set = (campo: keyof typeof FORM_VACIO) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [campo]: e.target.value }));

  const crear = useMutation({
    mutationFn: () => {
      const inicio = localAISO(form.inicio);
      const fin = localAISO(form.fin);
      const usosNum: Record<string, number> = {};
      for (const r of recursosCal) usosNum[r.codigo] = Math.max(0, Number(usos[r.codigo] || 0));
      return eventosService.create({
        calendario: calendarioId || undefined,
        cliente_nombre: form.cliente_nombre.trim(),
        vendedor_nombre: form.vendedor_nombre.trim() || undefined,
        ubicacion: form.ubicacion.trim(),
        inicio,
        fin,
        materiales: form.materiales.split(',').map((m) => m.trim()).filter(Boolean),
        notas: form.notas.trim(),
        usos: usosNum,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: activacionesKeys.all() });
      onClose();
    },
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo crear el evento.')),
  });

  const valido =
    form.cliente_nombre.trim() !== '' &&
    form.ubicacion.trim() !== '' &&
    localAISO(form.inicio) !== '' &&
    localAISO(form.fin) !== '' &&
    new Date(form.fin) > new Date(form.inicio);

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Nuevo evento de activación</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
          {calendarios.length > 1 && (
            <TextField
              select
              size="small"
              label="Calendario"
              value={calendarioId}
              onChange={(e) => {
                setForm((f) => ({ ...f, calendario: e.target.value }));
                setUsos({});
              }}
            >
              {calendarios.map((c) => (
                <MenuItem key={c.id_calendario} value={c.id_calendario}>
                  {c.nombre}
                </MenuItem>
              ))}
            </TextField>
          )}
          <TextField size="small" label="Cliente" value={form.cliente_nombre} onChange={set('cliente_nombre')} required />
          <TextField size="small" label="Vendedor" value={form.vendedor_nombre} onChange={set('vendedor_nombre')} />
          <TextField size="small" label="Ubicación (punto de venta)" value={form.ubicacion} onChange={set('ubicacion')} required />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              size="small"
              type="datetime-local"
              label="Inicio"
              value={form.inicio}
              onChange={set('inicio')}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
              required
            />
            <TextField
              size="small"
              type="datetime-local"
              label="Fin"
              value={form.fin}
              onChange={set('fin')}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
              required
            />
          </Stack>
          {recursosCal.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Recursos necesarios
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                {recursosCal.map((r) => (
                  <TextField
                    key={r.id_recurso}
                    size="small"
                    type="number"
                    label={`${r.nombre} (máx. ${r.capacidad})`}
                    value={usos[r.codigo] ?? ''}
                    onChange={(e) => setUsos((u) => ({ ...u, [r.codigo]: e.target.value }))}
                    slotProps={{ htmlInput: { min: 0, max: r.capacidad } }}
                    fullWidth
                  />
                ))}
              </Stack>
            </Box>
          )}
          <TextField
            size="small"
            label="Materiales a llevar (separados por coma)"
            value={form.materiales}
            onChange={set('materiales')}
          />
          <TextField size="small" label="Notas" value={form.notas} onChange={set('notas')} multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        <Button variant="contained" disabled={!valido || crear.isPending} onClick={() => crear.mutate()}>
          Crear evento
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default EventosTab;
