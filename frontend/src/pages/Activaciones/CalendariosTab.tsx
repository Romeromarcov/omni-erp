import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  calendariosService,
  recursosService,
  type Calendario,
  type Recurso,
} from '../../services/activacionesService';
import { activacionesKeys } from '../../lib/queryKeys';
import { mensajeActivacion } from './utils';

type Borrar = { tipo: 'calendario'; item: Calendario } | { tipo: 'recurso'; item: Recurso } | null;

const CalendariosTab: React.FC = () => {
  const qc = useQueryClient();
  const [errorMsg, setErrorMsg] = useState('');
  const [calDialog, setCalDialog] = useState<Calendario | 'nuevo' | null>(null);
  const [recDialog, setRecDialog] = useState<Recurso | 'nuevo' | null>(null);
  const [borrar, setBorrar] = useState<Borrar>(null);

  const { data: calendarios = [], isLoading: cargandoCal } = useQuery({
    queryKey: activacionesKeys.calendarios(),
    queryFn: () => calendariosService.getAll(),
  });
  const { data: recursos = [], isLoading: cargandoRec } = useQuery({
    queryKey: activacionesKeys.recursos(),
    queryFn: () => recursosService.getAll(),
  });

  const refrescar = () => qc.invalidateQueries({ queryKey: activacionesKeys.all() });

  const eliminar = useMutation({
    mutationFn: (b: NonNullable<Borrar>) =>
      b.tipo === 'calendario' ? calendariosService.remove(b.item.id_calendario) : recursosService.remove(b.item.id_recurso),
    onSuccess: () => {
      setBorrar(null);
      void refrescar();
    },
    onError: (e: unknown) => {
      setBorrar(null);
      setErrorMsg(mensajeActivacion(e, 'No se pudo eliminar.'));
    },
  });

  const nombreCal = (id: string) => calendarios.find((c) => c.id_calendario === id)?.nombre ?? '—';

  const colsCal: Column<Calendario>[] = [
    { key: 'nombre', header: 'Nombre', render: (c) => c.nombre },
    {
      key: 'pred',
      header: 'Predeterminado',
      render: (c) => <StatusChip value={c.es_predeterminado} />,
    },
    { key: 'tz', header: 'Zona horaria', render: (c) => c.zona_horaria },
    { key: 'g', header: 'Google Calendar', render: (c) => c.google_calendar_id || 'No sincroniza' },
    {
      key: 'acc',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setCalDialog(c)}>
            Editar
          </Button>
          <Button size="small" color="error" onClick={() => setBorrar({ tipo: 'calendario', item: c })}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  const colsRec: Column<Recurso>[] = [
    { key: 'cal', header: 'Calendario', render: (r) => nombreCal(r.calendario) },
    { key: 'cod', header: 'Código', render: (r) => r.codigo },
    { key: 'nom', header: 'Recurso', render: (r) => r.nombre },
    { key: 'cap', header: 'Capacidad simultánea', align: 'right', render: (r) => r.capacidad },
    {
      key: 'acc',
      header: 'Acciones',
      render: (r) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setRecDialog(r)}>
            Editar
          </Button>
          <Button size="small" color="error" onClick={() => setBorrar({ tipo: 'recurso', item: r })}>
            Eliminar
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

      <Stack direction="row" alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          Calendarios
        </Typography>
        <Button variant="contained" onClick={() => setCalDialog('nuevo')}>
          Nuevo calendario
        </Button>
      </Stack>
      <DataTable
        columns={colsCal}
        rows={calendarios}
        getRowKey={(c) => c.id_calendario}
        loading={cargandoCal}
        emptyMessage="Aún no hay calendarios. Crea uno para empezar a reservar eventos."
      />

      <Stack direction="row" alignItems="center" sx={{ mt: 4, mb: 1.5 }}>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          Recursos y capacidad
        </Typography>
        <Button variant="contained" disabled={calendarios.length === 0} onClick={() => setRecDialog('nuevo')}>
          Nuevo recurso
        </Button>
      </Stack>
      <DataTable
        columns={colsRec}
        rows={recursos}
        getRowKey={(r) => r.id_recurso}
        loading={cargandoRec}
        emptyMessage="Sin recursos. Ej.: promotoras (2), igloos (3)."
      />

      {calDialog !== null && (
        <CalendarioDialog
          inicial={calDialog === 'nuevo' ? null : calDialog}
          onClose={() => setCalDialog(null)}
          onSaved={() => {
            setCalDialog(null);
            void refrescar();
          }}
        />
      )}
      {recDialog !== null && (
        <RecursoDialog
          inicial={recDialog === 'nuevo' ? null : recDialog}
          calendarios={calendarios}
          onClose={() => setRecDialog(null)}
          onSaved={() => {
            setRecDialog(null);
            void refrescar();
          }}
        />
      )}

      <Dialog open={borrar !== null} onClose={() => setBorrar(null)}>
        <DialogTitle>Eliminar {borrar?.tipo}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            ¿Eliminar «{borrar?.item.nombre}»? Esta acción lo desactiva (borrado lógico).
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBorrar(null)}>Volver</Button>
          <Button color="error" disabled={eliminar.isPending} onClick={() => borrar && eliminar.mutate(borrar)}>
            Eliminar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

// ── Diálogos ────────────────────────────────────────────────────────────────

const CalendarioDialog: React.FC<{
  inicial: Calendario | null;
  onClose: () => void;
  onSaved: () => void;
}> = ({ inicial, onClose, onSaved }) => {
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [gid, setGid] = useState(inicial?.google_calendar_id ?? '');
  const [tz, setTz] = useState(inicial?.zona_horaria ?? 'America/Caracas');
  const [pred, setPred] = useState(inicial?.es_predeterminado ?? false);
  const [errorMsg, setErrorMsg] = useState('');

  const guardar = useMutation({
    mutationFn: () => {
      const p = { nombre: nombre.trim(), google_calendar_id: gid.trim(), zona_horaria: tz.trim(), es_predeterminado: pred };
      return inicial ? calendariosService.update(inicial.id_calendario, p) : calendariosService.create(p);
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo guardar el calendario.')),
  });

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{inicial ? 'Editar calendario' : 'Nuevo calendario'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
          <TextField size="small" label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
          <TextField
            size="small"
            label="ID de Google Calendar"
            helperText="Opcional. Compártelo con la cuenta de servicio para sincronizar."
            value={gid}
            onChange={(e) => setGid(e.target.value)}
          />
          <TextField size="small" label="Zona horaria" value={tz} onChange={(e) => setTz(e.target.value)} />
          <FormControlLabel
            control={<Checkbox checked={pred} onChange={(e) => setPred(e.target.checked)} />}
            label="Calendario predeterminado (el que usan los bots)"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        <Button variant="contained" disabled={!nombre.trim() || guardar.isPending} onClick={() => guardar.mutate()}>
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const RecursoDialog: React.FC<{
  inicial: Recurso | null;
  calendarios: Calendario[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ inicial, calendarios, onClose, onSaved }) => {
  const [calendario, setCalendario] = useState(
    inicial?.calendario ?? calendarios.find((c) => c.es_predeterminado)?.id_calendario ?? calendarios[0]?.id_calendario ?? '',
  );
  const [codigo, setCodigo] = useState(inicial?.codigo ?? '');
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [capacidad, setCapacidad] = useState(String(inicial?.capacidad ?? ''));
  const [errorMsg, setErrorMsg] = useState('');

  const guardar = useMutation({
    mutationFn: () =>
      inicial
        ? recursosService.update(inicial.id_recurso, { nombre: nombre.trim(), capacidad: Number(capacidad) })
        : recursosService.create({
            calendario,
            codigo: codigo.trim().toLowerCase(),
            nombre: nombre.trim(),
            capacidad: Number(capacidad),
          }),
    onSuccess: onSaved,
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo guardar el recurso.')),
  });

  const capNum = Number(capacidad);
  const valido =
    nombre.trim() !== '' &&
    capacidad !== '' &&
    Number.isInteger(capNum) &&
    capNum >= 0 &&
    (inicial !== null || (codigo.trim() !== '' && calendario !== ''));

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{inicial ? 'Editar recurso' : 'Nuevo recurso'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
          {!inicial && (
            <>
              <TextField
                select
                size="small"
                label="Calendario"
                value={calendario}
                onChange={(e) => setCalendario(e.target.value)}
                slotProps={{ select: { native: true } }}
              >
                {calendarios.map((c) => (
                  <option key={c.id_calendario} value={c.id_calendario}>
                    {c.nombre}
                  </option>
                ))}
              </TextField>
              <TextField
                size="small"
                label="Código"
                helperText="Identificador estable, p. ej. promotoras, igloos (el bot lo usa)."
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                required
              />
            </>
          )}
          <TextField size="small" label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
          <TextField
            size="small"
            type="number"
            label="Capacidad simultánea"
            value={capacidad}
            onChange={(e) => setCapacidad(e.target.value)}
            slotProps={{ htmlInput: { min: 0 } }}
            required
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        <Button variant="contained" disabled={!valido || guardar.isPending} onClick={() => guardar.mutate()}>
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default CalendariosTab;
