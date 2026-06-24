import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import FingerprintOutlined from '@mui/icons-material/FingerprintOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  horariosTrabajoService,
  asignacionesHorarioService,
  registrosAsistenciaService,
  resumenesAsistenciaService,
  type HorarioTrabajo,
  type HorarioTrabajoPayload,
  type AsignacionHorario,
  type AsignacionHorarioPayload,
  type RegistroAsistencia,
  type ResumenAsistenciaDiario,
  type TipoMarcado,
  type MetodoMarcado,
  type EstadoRevision,
} from '../../services/controlAsistenciaService';
import { rrhhService, type Empleado } from '../../services/rrhhService';
import { controlAsistenciaKeys, rrhhKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const hoy = () => new Date().toISOString().slice(0, 10);

const TIPOS_MARCADO: { value: TipoMarcado; label: string }[] = [
  { value: 'ENTRADA', label: 'Entrada' },
  { value: 'SALIDA', label: 'Salida' },
  { value: 'INICIO_DESCANSO', label: 'Inicio de descanso' },
  { value: 'FIN_DESCANSO', label: 'Fin de descanso' },
];

const METODOS_MARCADO: { value: MetodoMarcado; label: string }[] = [
  { value: 'WEB', label: 'Web' },
  { value: 'MANUAL', label: 'Manual' },
  { value: 'BIOMETRICO', label: 'Biométrico' },
  { value: 'MOVIL', label: 'Móvil' },
  { value: 'GPS', label: 'GPS' },
];

const ESTADO_REVISION_COLOR: Record<string, 'warning' | 'info' | 'success' | 'default'> = {
  pendiente: 'warning',
  revisado: 'info',
  aprobado: 'success',
};

const nombreEmpleado = (empleados: Empleado[], id: number | null): string => {
  if (id === null || id === undefined) return '—';
  const e = empleados.find((emp) => emp.id === id);
  return e ? `${e.nombre} ${e.apellido}` : String(id);
};

const ControlAsistenciaPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  const empresaId = getEmpresaId() || '';

  // Empleados del tenant (compartido por las pestañas que seleccionan empleado).
  const { data: empleados = [] } = useQuery<Empleado[]>({
    queryKey: rrhhKeys.empleadosDeEmpresa(empresaId),
    queryFn: () => rrhhService.getEmpleadosDeEmpresa(empresaId),
    enabled: Boolean(empresaId),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Control de Asistencia"
        subtitle="Horarios, asignaciones, marcaje de asistencia y resúmenes diarios con revisión."
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Horarios" />
        <Tab label="Asignaciones" />
        <Tab label="Registros" />
        <Tab label="Resúmenes" />
      </Tabs>

      {tab === 0 && <HorariosTab empresaId={empresaId} />}
      {tab === 1 && <AsignacionesTab empleados={empleados} />}
      {tab === 2 && <RegistrosTab empleados={empleados} />}
      {tab === 3 && <ResumenesTab empleados={empleados} />}
    </PageContainer>
  );
};

// ── Pestaña: Horarios de trabajo ──────────────────────────────────────────────

interface HorarioForm {
  nombre_horario: string;
  descripcion: string;
  total_horas_semanales: string;
}

const HORARIO_VACIO: HorarioForm = {
  nombre_horario: '',
  descripcion: '',
  total_horas_semanales: '',
};

const HorariosTab: React.FC<{ empresaId: string }> = ({ empresaId }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<HorarioTrabajo | null>(null);
  const [form, setForm] = useState<HorarioForm>(HORARIO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: horarios = [], isLoading } = useQuery({
    queryKey: controlAsistenciaKeys.horarios(empresaId),
    queryFn: () => horariosTrabajoService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: controlAsistenciaKeys.horariosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(HORARIO_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (h: HorarioTrabajo) => {
    setEditando(h);
    setForm({
      nombre_horario: h.nombre_horario,
      descripcion: h.descripcion ?? '',
      total_horas_semanales: h.total_horas_semanales,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: HorarioTrabajoPayload) =>
      editando
        ? horariosTrabajoService.update(editando.id_horario, payload)
        : horariosTrabajoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el horario.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => horariosTrabajoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el horario.')),
  });

  const desactivar = useMutation({
    mutationFn: (id: string) => horariosTrabajoService.desactivar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo desactivar el horario.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_horario.trim() || !form.total_horas_semanales.trim()) {
      setErrorMsg('Indique el nombre y el total de horas semanales.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      nombre_horario: form.nombre_horario.trim(),
      descripcion: form.descripcion.trim() || null,
      dias_semana_json: null,
      total_horas_semanales: form.total_horas_semanales.trim(),
    });
  };

  const handleEliminar = (h: HorarioTrabajo) => {
    if (window.confirm(`¿Eliminar el horario "${h.nombre_horario}"?`)) {
      eliminar.mutate(h.id_horario);
    }
  };

  const handleDesactivar = (h: HorarioTrabajo) => {
    if (window.confirm(`¿Desactivar el horario "${h.nombre_horario}"?`)) {
      desactivar.mutate(h.id_horario);
    }
  };

  const columns: Column<HorarioTrabajo>[] = [
    { key: 'nombre_horario', header: 'Nombre', render: (h) => h.nombre_horario },
    { key: 'descripcion', header: 'Descripción', render: (h) => h.descripcion ?? '—' },
    {
      key: 'total_horas_semanales',
      header: 'Horas/semana',
      render: (h) => h.total_horas_semanales,
    },
    {
      key: 'activo',
      header: 'Estado',
      render: (h) => <StatusChip value={h.activo} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (h) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(h)}>
            Editar
          </Button>
          <Button
            size="small"
            color="warning"
            disabled={!h.activo || desactivar.isPending}
            onClick={() => handleDesactivar(h)}
          >
            Desactivar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(h)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nuevo horario
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={horarios}
        getRowKey={(h) => h.id_horario}
        loading={isLoading}
        emptyMessage="Sin horarios. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar horario' : 'Nuevo horario'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre del horario"
              value={form.nombre_horario}
              onChange={(e) => setForm((f) => ({ ...f, nombre_horario: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
              multiline
              minRows={2}
              fullWidth
            />
            <TextField
              label="Total de horas semanales"
              value={form.total_horas_semanales}
              onChange={(e) => setForm((f) => ({ ...f, total_horas_semanales: e.target.value }))}
              required
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
    </>
  );
};

// ── Pestaña: Asignaciones de horario ──────────────────────────────────────────

interface AsignacionForm {
  id_empleado: string;
  id_horario: string;
  fecha_inicio: string;
  fecha_fin: string;
}

const asignacionVacia = (): AsignacionForm => ({
  id_empleado: '',
  id_horario: '',
  fecha_inicio: hoy(),
  fecha_fin: '',
});

const AsignacionesTab: React.FC<{ empleados: Empleado[] }> = ({ empleados }) => {
  const queryClient = useQueryClient();
  const [filtroEmpleado, setFiltroEmpleado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<AsignacionHorario | null>(null);
  const [form, setForm] = useState<AsignacionForm>(asignacionVacia());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: asignaciones = [], isLoading } = useQuery({
    queryKey: controlAsistenciaKeys.asignaciones(filtroEmpleado || null),
    queryFn: () =>
      filtroEmpleado
        ? asignacionesHorarioService.porEmpleado(filtroEmpleado)
        : asignacionesHorarioService.getAll(),
  });

  const { data: horarios = [] } = useQuery({
    queryKey: controlAsistenciaKeys.horariosActivos(),
    queryFn: () => horariosTrabajoService.activos(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: controlAsistenciaKeys.asignacionesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(asignacionVacia());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (a: AsignacionHorario) => {
    setEditando(a);
    setForm({
      id_empleado: a.id_empleado !== null ? String(a.id_empleado) : '',
      id_horario: a.id_horario,
      fecha_inicio: a.fecha_inicio,
      fecha_fin: a.fecha_fin ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: AsignacionHorarioPayload) =>
      editando
        ? asignacionesHorarioService.update(editando.id_asignacion_horario, payload)
        : asignacionesHorarioService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la asignación.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => asignacionesHorarioService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la asignación.')),
  });

  const finalizar = useMutation({
    mutationFn: (id: string) => asignacionesHorarioService.finalizar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo finalizar la asignación.')),
  });

  const handleGuardar = () => {
    if (!form.id_empleado || !form.id_horario || !form.fecha_inicio) {
      setErrorMsg('Seleccione empleado, horario y fecha de inicio.');
      return;
    }
    guardar.mutate({
      id_empleado: Number(form.id_empleado),
      id_horario: form.id_horario,
      fecha_inicio: form.fecha_inicio,
      fecha_fin: form.fecha_fin || null,
    });
  };

  const handleEliminar = (a: AsignacionHorario) => {
    if (window.confirm('¿Eliminar esta asignación de horario?')) {
      eliminar.mutate(a.id_asignacion_horario);
    }
  };

  const handleFinalizar = (a: AsignacionHorario) => {
    if (window.confirm('¿Finalizar esta asignación? Quedará inactiva.')) {
      finalizar.mutate(a.id_asignacion_horario);
    }
  };

  const nombreHorario = (id: string) =>
    horarios.find((h) => h.id_horario === id)?.nombre_horario ?? id;

  const columns: Column<AsignacionHorario>[] = [
    {
      key: 'id_empleado',
      header: 'Empleado',
      render: (a) => nombreEmpleado(empleados, a.id_empleado),
    },
    { key: 'id_horario', header: 'Horario', render: (a) => nombreHorario(a.id_horario) },
    { key: 'fecha_inicio', header: 'Desde', render: (a) => a.fecha_inicio },
    { key: 'fecha_fin', header: 'Hasta', render: (a) => a.fecha_fin ?? '—' },
    {
      key: 'activo',
      header: 'Estado',
      render: (a) => <StatusChip value={a.activo} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (a) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(a)}>
            Editar
          </Button>
          <Button
            size="small"
            color="warning"
            disabled={!a.activo || finalizar.isPending}
            onClick={() => handleFinalizar(a)}
          >
            Finalizar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(a)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 2 }} flexWrap="wrap" gap={2}>
        <TextField
          select
          label="Filtrar por empleado"
          value={filtroEmpleado}
          onChange={(e) => setFiltroEmpleado(e.target.value)}
          size="small"
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {empleados.map((emp) => (
            <MenuItem key={emp.id} value={String(emp.id)}>
              {emp.nombre} {emp.apellido}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva asignación
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={asignaciones}
        getRowKey={(a) => a.id_asignacion_horario}
        loading={isLoading}
        emptyMessage="Sin asignaciones."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar asignación' : 'Nueva asignación'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Empleado"
              value={form.id_empleado}
              onChange={(e) => setForm((f) => ({ ...f, id_empleado: e.target.value }))}
              required
              fullWidth
            >
              {empleados.map((emp) => (
                <MenuItem key={emp.id} value={String(emp.id)}>
                  {emp.nombre} {emp.apellido}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Horario"
              value={form.id_horario}
              onChange={(e) => setForm((f) => ({ ...f, id_horario: e.target.value }))}
              required
              fullWidth
            >
              {horarios.map((h) => (
                <MenuItem key={h.id_horario} value={h.id_horario}>
                  {h.nombre_horario}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha de inicio"
              type="date"
              value={form.fecha_inicio}
              onChange={(e) => setForm((f) => ({ ...f, fecha_inicio: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Fecha de fin (opcional)"
              type="date"
              value={form.fecha_fin}
              onChange={(e) => setForm((f) => ({ ...f, fecha_fin: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
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
    </>
  );
};

// ── Pestaña: Registros de asistencia ──────────────────────────────────────────

const RegistrosTab: React.FC<{ empleados: Empleado[] }> = ({ empleados }) => {
  const queryClient = useQueryClient();
  const [empleadoSel, setEmpleadoSel] = useState('');
  const [verHoy, setVerHoy] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [marca, setMarca] = useState<{ tipo_marcado: TipoMarcado; metodo_marcado: MetodoMarcado }>(
    { tipo_marcado: 'ENTRADA', metodo_marcado: 'WEB' },
  );

  const { data: registros = [], isLoading } = useQuery({
    queryKey: verHoy
      ? controlAsistenciaKeys.registrosHoy(empleadoSel || null)
      : controlAsistenciaKeys.registros(empleadoSel || null),
    queryFn: () =>
      verHoy
        ? registrosAsistenciaService.hoy(empleadoSel || undefined)
        : empleadoSel
          ? registrosAsistenciaService.porEmpleadoFecha({ empleado: empleadoSel })
          : registrosAsistenciaService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: controlAsistenciaKeys.registrosAll() });

  const marcar = useMutation({
    mutationFn: () =>
      registrosAsistenciaService.marcarAsistencia({
        empleado_id: empleadoSel,
        tipo_marcado: marca.tipo_marcado,
        metodo_marcado: marca.metodo_marcado,
      }),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar el marcaje.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => registrosAsistenciaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el registro.')),
  });

  const abrirMarcar = () => {
    if (!empleadoSel) {
      setErrorMsg('Seleccione un empleado para marcar asistencia.');
      return;
    }
    setMarca({ tipo_marcado: 'ENTRADA', metodo_marcado: 'WEB' });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const handleEliminar = (r: RegistroAsistencia) => {
    if (window.confirm('¿Eliminar este registro de asistencia?')) {
      eliminar.mutate(r.id_registro_asistencia);
    }
  };

  const tipoLabel = (t: string) => TIPOS_MARCADO.find((x) => x.value === t)?.label ?? t;

  const columns: Column<RegistroAsistencia>[] = [
    {
      key: 'id_empleado',
      header: 'Empleado',
      render: (r) => nombreEmpleado(empleados, r.id_empleado),
    },
    {
      key: 'fecha_hora_marcado',
      header: 'Fecha/hora',
      render: (r) => new Date(r.fecha_hora_marcado).toLocaleString('es-VE'),
    },
    { key: 'tipo_marcado', header: 'Tipo', render: (r) => tipoLabel(r.tipo_marcado) },
    { key: 'metodo_marcado', header: 'Método', render: (r) => r.metodo_marcado },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => (
        <Button
          size="small"
          color="error"
          disabled={eliminar.isPending}
          onClick={() => handleEliminar(r)}
        >
          Eliminar
        </Button>
      ),
    },
  ];

  return (
    <>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 2 }} flexWrap="wrap" gap={2}>
        <Stack direction="row" spacing={2} flexWrap="wrap">
          <TextField
            select
            label="Empleado"
            value={empleadoSel}
            onChange={(e) => setEmpleadoSel(e.target.value)}
            size="small"
            sx={{ minWidth: 240 }}
          >
            <MenuItem value="">Todos</MenuItem>
            {empleados.map((emp) => (
              <MenuItem key={emp.id} value={String(emp.id)}>
                {emp.nombre} {emp.apellido}
              </MenuItem>
            ))}
          </TextField>
          <Button
            variant={verHoy ? 'contained' : 'outlined'}
            onClick={() => setVerHoy((v) => !v)}
          >
            {verHoy ? 'Viendo: Hoy' : 'Ver hoy'}
          </Button>
        </Stack>
        <Button variant="contained" startIcon={<FingerprintOutlined />} onClick={abrirMarcar}>
          Marcar asistencia
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={registros}
        getRowKey={(r) => r.id_registro_asistencia}
        loading={isLoading}
        emptyMessage="Sin registros de asistencia."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Marcar asistencia</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Empleado"
              value={nombreEmpleado(empleados, Number(empleadoSel))}
              disabled
              fullWidth
            />
            <TextField
              select
              label="Tipo de marcado"
              value={marca.tipo_marcado}
              onChange={(e) =>
                setMarca((m) => ({ ...m, tipo_marcado: e.target.value as TipoMarcado }))
              }
              fullWidth
            >
              {TIPOS_MARCADO.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Método"
              value={marca.metodo_marcado}
              onChange={(e) =>
                setMarca((m) => ({ ...m, metodo_marcado: e.target.value as MetodoMarcado }))
              }
              fullWidth
            >
              {METODOS_MARCADO.map((m) => (
                <MenuItem key={m.value} value={m.value}>
                  {m.label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => marcar.mutate()} disabled={marcar.isPending}>
            Registrar marcaje
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

// ── Pestaña: Resúmenes diarios (con flujo de revisión) ────────────────────────

const ESTADOS_REVISION: { value: EstadoRevision | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'REVISADO', label: 'Revisado' },
  { value: 'APROBADO', label: 'Aprobado' },
];

const ResumenesTab: React.FC<{ empleados: Empleado[] }> = ({ empleados }) => {
  const queryClient = useQueryClient();
  const [filtroEstado, setFiltroEstado] = useState<EstadoRevision | ''>('');
  const [fechaGenerar, setFechaGenerar] = useState(hoy());
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const { data: resumenes = [], isLoading } = useQuery({
    queryKey: controlAsistenciaKeys.resumenes(null, null, filtroEstado || null),
    queryFn: () =>
      resumenesAsistenciaService.getAll({ estado: filtroEstado || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: controlAsistenciaKeys.resumenesAll() });

  const generar = useMutation({
    mutationFn: () => resumenesAsistenciaService.generarResumenDiario({ fecha: fechaGenerar }),
    onSuccess: (r) => {
      setInfoMsg(r.mensaje);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudieron generar los resúmenes.')),
  });

  const aprobar = useMutation({
    mutationFn: (id: string) => resumenesAsistenciaService.aprobar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo aprobar el resumen.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => resumenesAsistenciaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el resumen.')),
  });

  const handleAprobar = (r: ResumenAsistenciaDiario) => {
    if (window.confirm('¿Aprobar este resumen de asistencia?')) {
      aprobar.mutate(r.id_resumen_diario);
    }
  };

  const handleEliminar = (r: ResumenAsistenciaDiario) => {
    if (window.confirm('¿Eliminar este resumen de asistencia?')) {
      eliminar.mutate(r.id_resumen_diario);
    }
  };

  const columns: Column<ResumenAsistenciaDiario>[] = [
    {
      key: 'id_empleado',
      header: 'Empleado',
      render: (r) => nombreEmpleado(empleados, r.id_empleado),
    },
    { key: 'fecha', header: 'Fecha', render: (r) => r.fecha },
    {
      key: 'horas_trabajadas_netas',
      header: 'Horas netas',
      render: (r) => r.horas_trabajadas_netas,
    },
    { key: 'minutos_tardanza', header: 'Tardanza (min)', render: (r) => String(r.minutos_tardanza) },
    {
      key: 'es_ausencia',
      header: 'Ausencia',
      render: (r) => <StatusChip value={r.es_ausencia} />,
    },
    {
      key: 'estado_revision',
      header: 'Revisión',
      render: (r) => <StatusChip value={r.estado_revision} colorMap={ESTADO_REVISION_COLOR} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => {
        const aprobado = r.estado_revision === 'APROBADO';
        return (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              color="success"
              disabled={aprobado || aprobar.isPending}
              onClick={() => handleAprobar(r)}
            >
              Aprobar
            </Button>
            <Button
              size="small"
              color="error"
              disabled={eliminar.isPending}
              onClick={() => handleEliminar(r)}
            >
              Eliminar
            </Button>
          </Stack>
        );
      },
    },
  ];

  return (
    <>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 2 }} flexWrap="wrap" gap={2}>
        <TextField
          select
          label="Estado de revisión"
          value={filtroEstado}
          onChange={(e) => setFiltroEstado(e.target.value as EstadoRevision | '')}
          size="small"
          sx={{ minWidth: 220 }}
        >
          {ESTADOS_REVISION.map((e) => (
            <MenuItem key={e.value || 'todos'} value={e.value}>
              {e.label}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
          <TextField
            label="Fecha a generar"
            type="date"
            value={fechaGenerar}
            onChange={(e) => setFechaGenerar(e.target.value)}
            size="small"
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <Button variant="contained" onClick={() => generar.mutate()} disabled={generar.isPending}>
            Generar resúmenes
          </Button>
        </Stack>
      </Stack>

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

      <DataTable
        columns={columns}
        rows={resumenes}
        getRowKey={(r) => r.id_resumen_diario}
        loading={isLoading}
        emptyMessage="Sin resúmenes. Genera los del día."
      />
    </>
  );
};

export default ControlAsistenciaPage;
