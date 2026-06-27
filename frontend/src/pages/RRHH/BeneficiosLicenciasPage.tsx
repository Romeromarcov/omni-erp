import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  beneficiosService,
  beneficiosEmpleadoService,
  tiposLicenciaService,
  licenciasEmpleadoService,
  type Beneficio,
  type BeneficioPayload,
  type TipoBeneficio,
  type BeneficioEmpleado,
  type BeneficioEmpleadoPayload,
  type TipoLicencia,
  type TipoLicenciaPayload,
  type LicenciaEmpleado,
  type LicenciaEmpleadoPayload,
  type EstadoLicencia,
} from '../../services/beneficiosLicenciasService';
import { rrhhService, type Empleado } from '../../services/rrhhService';
import { beneficiosLicenciasKeys, rrhhKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const hoy = () => new Date().toISOString().slice(0, 10);

const TIPOS_BENEFICIO: { value: TipoBeneficio; label: string }[] = [
  { value: 'MONETARIO', label: 'Monetario' },
  { value: 'NO_MONETARIO', label: 'No monetario' },
  { value: 'TIEMPO', label: 'Tiempo' },
  { value: 'SALUD', label: 'Salud' },
  { value: 'EDUCACION', label: 'Educación' },
  { value: 'TRANSPORTE', label: 'Transporte' },
  { value: 'ALIMENTACION', label: 'Alimentación' },
  { value: 'OTRO', label: 'Otro' },
];

const ESTADOS_ASIGNACION: { value: string; label: string }[] = [
  { value: 'ACTIVO', label: 'Activo' },
  { value: 'SUSPENDIDO', label: 'Suspendido' },
  { value: 'TERMINADO', label: 'Terminado' },
];

const ESTADO_ASIGNACION_COLOR: Record<string, 'success' | 'warning' | 'default'> = {
  activo: 'success',
  suspendido: 'warning',
  terminado: 'default',
};

const ESTADOS_LICENCIA: { value: EstadoLicencia; label: string }[] = [
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'APROBADA', label: 'Aprobada' },
  { value: 'RECHAZADA', label: 'Rechazada' },
  { value: 'EN_CURSO', label: 'En curso' },
  { value: 'FINALIZADA', label: 'Finalizada' },
  { value: 'CANCELADA', label: 'Cancelada' },
];

const ESTADO_LICENCIA_COLOR: Record<
  string,
  'warning' | 'success' | 'error' | 'info' | 'default'
> = {
  pendiente: 'warning',
  aprobada: 'success',
  rechazada: 'error',
  en_curso: 'info',
  finalizada: 'default',
  cancelada: 'default',
};

const tipoBeneficioLabel = (t: string) =>
  TIPOS_BENEFICIO.find((x) => x.value === t)?.label ?? t;

const nombreEmpleado = (empleados: Empleado[], id: number | null): string => {
  if (id === null || id === undefined) return '—';
  const e = empleados.find((emp) => emp.id === id);
  return e ? `${e.nombre} ${e.apellido}` : String(id);
};

const BeneficiosLicenciasPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  const empresaId = getEmpresaId() || '';

  const { data: empleados = [] } = useQuery<Empleado[]>({
    queryKey: rrhhKeys.empleadosDeEmpresa(empresaId),
    queryFn: () => rrhhService.getEmpleadosDeEmpresa(empresaId),
    enabled: Boolean(empresaId),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Beneficios y Licencias"
        subtitle="Catálogo de beneficios, asignaciones a empleados, tipos de licencia y solicitudes de licencia."
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Beneficios" />
        <Tab label="Asignaciones" />
        <Tab label="Tipos de Licencia" />
        <Tab label="Licencias" />
      </Tabs>

      {tab === 0 && <BeneficiosTab empresaId={empresaId} />}
      {tab === 1 && <AsignacionesTab empresaId={empresaId} empleados={empleados} />}
      {tab === 2 && <TiposLicenciaTab empresaId={empresaId} />}
      {tab === 3 && <LicenciasTab empleados={empleados} />}
    </PageContainer>
  );
};

// ── Pestaña: Beneficios (catálogo) ────────────────────────────────────────────

interface BeneficioForm {
  nombre_beneficio: string;
  descripcion: string;
  tipo_beneficio: TipoBeneficio;
  monto_fijo: string;
  porcentaje_salario: string;
  es_obligatorio: boolean;
  activo: boolean;
}

const BENEFICIO_VACIO: BeneficioForm = {
  nombre_beneficio: '',
  descripcion: '',
  tipo_beneficio: 'MONETARIO',
  monto_fijo: '',
  porcentaje_salario: '',
  es_obligatorio: false,
  activo: true,
};

const BeneficiosTab: React.FC<{ empresaId: string }> = ({ empresaId }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<Beneficio | null>(null);
  const [form, setForm] = useState<BeneficioForm>(BENEFICIO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: beneficios = [], isLoading } = useQuery({
    queryKey: beneficiosLicenciasKeys.beneficios(),
    queryFn: () => beneficiosService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: beneficiosLicenciasKeys.beneficiosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(BENEFICIO_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (b: Beneficio) => {
    setEditando(b);
    setForm({
      nombre_beneficio: b.nombre_beneficio,
      descripcion: b.descripcion ?? '',
      tipo_beneficio: (b.tipo_beneficio as TipoBeneficio) ?? 'MONETARIO',
      monto_fijo: b.monto_fijo ?? '',
      porcentaje_salario: b.porcentaje_salario ?? '',
      es_obligatorio: b.es_obligatorio,
      activo: b.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: BeneficioPayload) =>
      editando
        ? beneficiosService.update(editando.id_beneficio, payload)
        : beneficiosService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el beneficio.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => beneficiosService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el beneficio.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_beneficio.trim()) {
      setErrorMsg('Indique el nombre del beneficio.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      nombre_beneficio: form.nombre_beneficio.trim(),
      descripcion: form.descripcion.trim() || null,
      tipo_beneficio: form.tipo_beneficio,
      monto_fijo: form.monto_fijo.trim() || null,
      porcentaje_salario: form.porcentaje_salario.trim() || null,
      es_obligatorio: form.es_obligatorio,
      activo: form.activo,
    });
  };

  const handleEliminar = (b: Beneficio) => {
    if (window.confirm(`¿Eliminar el beneficio "${b.nombre_beneficio}"?`)) {
      eliminar.mutate(b.id_beneficio);
    }
  };

  const columns: Column<Beneficio>[] = [
    { key: 'nombre_beneficio', header: 'Nombre', render: (b) => b.nombre_beneficio },
    { key: 'tipo_beneficio', header: 'Tipo', render: (b) => tipoBeneficioLabel(b.tipo_beneficio) },
    { key: 'monto_fijo', header: 'Monto fijo', render: (b) => b.monto_fijo ?? '—' },
    {
      key: 'porcentaje_salario',
      header: '% salario',
      render: (b) => (b.porcentaje_salario ? `${b.porcentaje_salario}%` : '—'),
    },
    {
      key: 'es_obligatorio',
      header: 'Obligatorio',
      render: (b) => <StatusChip value={b.es_obligatorio} />,
    },
    { key: 'activo', header: 'Estado', render: (b) => <StatusChip value={b.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (b) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(b)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(b)}
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
          Nuevo beneficio
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={beneficios}
        getRowKey={(b) => b.id_beneficio}
        loading={isLoading}
        emptyMessage="Sin beneficios. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar beneficio' : 'Nuevo beneficio'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre del beneficio"
              value={form.nombre_beneficio}
              onChange={(e) => setForm((f) => ({ ...f, nombre_beneficio: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Tipo de beneficio"
              value={form.tipo_beneficio}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_beneficio: e.target.value as TipoBeneficio }))
              }
              fullWidth
            >
              {TIPOS_BENEFICIO.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
              multiline
              minRows={2}
              fullWidth
            />
            <TextField
              label="Monto fijo"
              value={form.monto_fijo}
              onChange={(e) => setForm((f) => ({ ...f, monto_fijo: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Porcentaje del salario"
              value={form.porcentaje_salario}
              onChange={(e) => setForm((f) => ({ ...f, porcentaje_salario: e.target.value }))}
              fullWidth
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.es_obligatorio}
                  onChange={(e) => setForm((f) => ({ ...f, es_obligatorio: e.target.checked }))}
                />
              }
              label="Obligatorio"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Activo"
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

// ── Pestaña: Asignaciones (BeneficioEmpleado) ─────────────────────────────────

interface AsignacionForm {
  id_empleado: string;
  id_beneficio: string;
  fecha_inicio: string;
  fecha_fin: string;
  monto_personalizado: string;
  porcentaje_personalizado: string;
  estado: string;
  observaciones: string;
}

const asignacionVacia = (): AsignacionForm => ({
  id_empleado: '',
  id_beneficio: '',
  fecha_inicio: hoy(),
  fecha_fin: '',
  monto_personalizado: '',
  porcentaje_personalizado: '',
  estado: 'ACTIVO',
  observaciones: '',
});

const AsignacionesTab: React.FC<{ empresaId: string; empleados: Empleado[] }> = ({
  empleados,
}) => {
  const queryClient = useQueryClient();
  const [filtroEmpleado, setFiltroEmpleado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<BeneficioEmpleado | null>(null);
  const [form, setForm] = useState<AsignacionForm>(asignacionVacia());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: asignaciones = [], isLoading } = useQuery({
    queryKey: beneficiosLicenciasKeys.asignaciones(filtroEmpleado || null),
    queryFn: () =>
      beneficiosEmpleadoService.getAll(filtroEmpleado ? { empleado: filtroEmpleado } : undefined),
  });

  const { data: beneficios = [] } = useQuery({
    queryKey: beneficiosLicenciasKeys.beneficios(),
    queryFn: () => beneficiosService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: beneficiosLicenciasKeys.asignacionesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(asignacionVacia());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (a: BeneficioEmpleado) => {
    setEditando(a);
    setForm({
      id_empleado: String(a.id_empleado),
      id_beneficio: a.id_beneficio,
      fecha_inicio: a.fecha_inicio,
      fecha_fin: a.fecha_fin ?? '',
      monto_personalizado: a.monto_personalizado ?? '',
      porcentaje_personalizado: a.porcentaje_personalizado ?? '',
      estado: a.estado,
      observaciones: a.observaciones ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: BeneficioEmpleadoPayload) =>
      editando
        ? beneficiosEmpleadoService.update(editando.id_beneficio_empleado, payload)
        : beneficiosEmpleadoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la asignación.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => beneficiosEmpleadoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la asignación.')),
  });

  const handleGuardar = () => {
    if (!form.id_empleado || !form.id_beneficio || !form.fecha_inicio) {
      setErrorMsg('Seleccione empleado, beneficio y fecha de inicio.');
      return;
    }
    guardar.mutate({
      id_empleado: Number(form.id_empleado),
      id_beneficio: form.id_beneficio,
      fecha_inicio: form.fecha_inicio,
      fecha_fin: form.fecha_fin || null,
      monto_personalizado: form.monto_personalizado.trim() || null,
      porcentaje_personalizado: form.porcentaje_personalizado.trim() || null,
      estado: form.estado,
      observaciones: form.observaciones.trim() || null,
    });
  };

  const handleEliminar = (a: BeneficioEmpleado) => {
    if (window.confirm('¿Eliminar esta asignación de beneficio?')) {
      eliminar.mutate(a.id_beneficio_empleado);
    }
  };

  const nombreBeneficio = (id: string) =>
    beneficios.find((b) => b.id_beneficio === id)?.nombre_beneficio ?? id;

  const columns: Column<BeneficioEmpleado>[] = [
    {
      key: 'id_empleado',
      header: 'Empleado',
      render: (a) => nombreEmpleado(empleados, a.id_empleado),
    },
    { key: 'id_beneficio', header: 'Beneficio', render: (a) => nombreBeneficio(a.id_beneficio) },
    { key: 'fecha_inicio', header: 'Desde', render: (a) => a.fecha_inicio },
    { key: 'fecha_fin', header: 'Hasta', render: (a) => a.fecha_fin ?? '—' },
    {
      key: 'estado',
      header: 'Estado',
      render: (a) => <StatusChip value={a.estado} colorMap={ESTADO_ASIGNACION_COLOR} />,
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
        getRowKey={(a) => a.id_beneficio_empleado}
        loading={isLoading}
        emptyMessage="Sin asignaciones de beneficios."
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
              label="Beneficio"
              value={form.id_beneficio}
              onChange={(e) => setForm((f) => ({ ...f, id_beneficio: e.target.value }))}
              required
              fullWidth
            >
              {beneficios.map((b) => (
                <MenuItem key={b.id_beneficio} value={b.id_beneficio}>
                  {b.nombre_beneficio}
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
            <TextField
              label="Monto personalizado"
              value={form.monto_personalizado}
              onChange={(e) => setForm((f) => ({ ...f, monto_personalizado: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Porcentaje personalizado"
              value={form.porcentaje_personalizado}
              onChange={(e) =>
                setForm((f) => ({ ...f, porcentaje_personalizado: e.target.value }))
              }
              fullWidth
            />
            <TextField
              select
              label="Estado"
              value={form.estado}
              onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value }))}
              fullWidth
            >
              {ESTADOS_ASIGNACION.map((s) => (
                <MenuItem key={s.value} value={s.value}>
                  {s.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Observaciones"
              value={form.observaciones}
              onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
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
    </>
  );
};

// ── Pestaña: Tipos de Licencia ────────────────────────────────────────────────

interface TipoLicenciaForm {
  nombre_tipo: string;
  descripcion: string;
  es_remunerada: boolean;
  dias_maximos: string;
  requiere_aprobacion: boolean;
  activo: boolean;
}

const TIPO_LICENCIA_VACIO: TipoLicenciaForm = {
  nombre_tipo: '',
  descripcion: '',
  es_remunerada: true,
  dias_maximos: '',
  requiere_aprobacion: true,
  activo: true,
};

const TiposLicenciaTab: React.FC<{ empresaId: string }> = ({ empresaId }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<TipoLicencia | null>(null);
  const [form, setForm] = useState<TipoLicenciaForm>(TIPO_LICENCIA_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: tipos = [], isLoading } = useQuery({
    queryKey: beneficiosLicenciasKeys.tipos(),
    queryFn: () => tiposLicenciaService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: beneficiosLicenciasKeys.tiposAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(TIPO_LICENCIA_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (t: TipoLicencia) => {
    setEditando(t);
    setForm({
      nombre_tipo: t.nombre_tipo,
      descripcion: t.descripcion ?? '',
      es_remunerada: t.es_remunerada,
      dias_maximos: t.dias_maximos_por_año !== null ? String(t.dias_maximos_por_año) : '',
      requiere_aprobacion: t.requiere_aprobacion,
      activo: t.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: TipoLicenciaPayload) =>
      editando
        ? tiposLicenciaService.update(editando.id_tipo_licencia, payload)
        : tiposLicenciaService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo guardar el tipo de licencia.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => tiposLicenciaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el tipo de licencia.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_tipo.trim()) {
      setErrorMsg('Indique el nombre del tipo de licencia.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      nombre_tipo: form.nombre_tipo.trim(),
      descripcion: form.descripcion.trim() || null,
      es_remunerada: form.es_remunerada,
      dias_maximos_por_año: form.dias_maximos.trim() ? Number(form.dias_maximos) : null,
      requiere_aprobacion: form.requiere_aprobacion,
      activo: form.activo,
    });
  };

  const handleEliminar = (t: TipoLicencia) => {
    if (window.confirm(`¿Eliminar el tipo de licencia "${t.nombre_tipo}"?`)) {
      eliminar.mutate(t.id_tipo_licencia);
    }
  };

  const columns: Column<TipoLicencia>[] = [
    { key: 'nombre_tipo', header: 'Nombre', render: (t) => t.nombre_tipo },
    {
      key: 'es_remunerada',
      header: 'Remunerada',
      render: (t) => <StatusChip value={t.es_remunerada} />,
    },
    {
      key: 'dias_maximos',
      header: 'Días máx./año',
      render: (t) => (t.dias_maximos_por_año !== null ? String(t.dias_maximos_por_año) : '—'),
    },
    {
      key: 'requiere_aprobacion',
      header: 'Requiere aprobación',
      render: (t) => <StatusChip value={t.requiere_aprobacion} />,
    },
    { key: 'activo', header: 'Estado', render: (t) => <StatusChip value={t.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (t) => (
        <Stack direction="row" spacing={1}>
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
    <>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nuevo tipo de licencia
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={tipos}
        getRowKey={(t) => t.id_tipo_licencia}
        loading={isLoading}
        emptyMessage="Sin tipos de licencia. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar tipo de licencia' : 'Nuevo tipo de licencia'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre del tipo"
              value={form.nombre_tipo}
              onChange={(e) => setForm((f) => ({ ...f, nombre_tipo: e.target.value }))}
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
              label="Días máximos por año"
              value={form.dias_maximos}
              onChange={(e) => setForm((f) => ({ ...f, dias_maximos: e.target.value }))}
              fullWidth
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.es_remunerada}
                  onChange={(e) => setForm((f) => ({ ...f, es_remunerada: e.target.checked }))}
                />
              }
              label="Remunerada"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.requiere_aprobacion}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, requiere_aprobacion: e.target.checked }))
                  }
                />
              }
              label="Requiere aprobación"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Activo"
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

// ── Pestaña: Licencias (LicenciaEmpleado) ─────────────────────────────────────

interface LicenciaForm {
  id_empleado: string;
  id_tipo_licencia: string;
  fecha_inicio: string;
  fecha_fin: string;
  dias_solicitados: string;
  motivo: string;
}

const licenciaVacia = (): LicenciaForm => ({
  id_empleado: '',
  id_tipo_licencia: '',
  fecha_inicio: hoy(),
  fecha_fin: hoy(),
  dias_solicitados: '',
  motivo: '',
});

const FILTRO_ESTADOS: { value: string; label: string }[] = [
  { value: '', label: 'Todos' },
  ...ESTADOS_LICENCIA.map((e) => ({ value: e.value, label: e.label })),
];

const LicenciasTab: React.FC<{ empleados: Empleado[] }> = ({ empleados }) => {
  const queryClient = useQueryClient();
  const [filtroEmpleado, setFiltroEmpleado] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<LicenciaForm>(licenciaVacia());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: licencias = [], isLoading } = useQuery({
    queryKey: beneficiosLicenciasKeys.licencias(filtroEmpleado || null, filtroEstado || null),
    queryFn: () =>
      licenciasEmpleadoService.getAll({
        empleado: filtroEmpleado || undefined,
        estado: filtroEstado || undefined,
      }),
  });

  const { data: tipos = [] } = useQuery({
    queryKey: beneficiosLicenciasKeys.tipos(),
    queryFn: () => tiposLicenciaService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: beneficiosLicenciasKeys.licenciasAll() });

  const abrirCrear = () => {
    setForm(licenciaVacia());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const crear = useMutation({
    mutationFn: (payload: LicenciaEmpleadoPayload) => licenciasEmpleadoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar la licencia.')),
  });

  const cambiarEstado = useMutation({
    mutationFn: ({ id, estado }: { id: string; estado: EstadoLicencia }) =>
      licenciasEmpleadoService.cambiarEstado(id, { estado }),
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo actualizar el estado de la licencia.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => licenciasEmpleadoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la licencia.')),
  });

  const handleCrear = () => {
    if (!form.id_empleado || !form.id_tipo_licencia || !form.fecha_inicio || !form.fecha_fin) {
      setErrorMsg('Seleccione empleado, tipo de licencia y fechas.');
      return;
    }
    if (!form.dias_solicitados.trim() || !form.motivo.trim()) {
      setErrorMsg('Indique los días solicitados y el motivo.');
      return;
    }
    crear.mutate({
      id_empleado: Number(form.id_empleado),
      id_tipo_licencia: form.id_tipo_licencia,
      fecha_inicio: form.fecha_inicio,
      fecha_fin: form.fecha_fin,
      dias_solicitados: Number(form.dias_solicitados),
      motivo: form.motivo.trim(),
      estado: 'PENDIENTE',
    });
  };

  const handleCambiarEstado = (l: LicenciaEmpleado, estado: EstadoLicencia, verbo: string) => {
    if (window.confirm(`¿${verbo} esta licencia?`)) {
      cambiarEstado.mutate({ id: l.id_licencia, estado });
    }
  };

  const handleEliminar = (l: LicenciaEmpleado) => {
    if (window.confirm('¿Eliminar esta licencia?')) {
      eliminar.mutate(l.id_licencia);
    }
  };

  const nombreTipo = (id: string) =>
    tipos.find((t) => t.id_tipo_licencia === id)?.nombre_tipo ?? id;

  const columns: Column<LicenciaEmpleado>[] = [
    {
      key: 'id_empleado',
      header: 'Empleado',
      render: (l) => nombreEmpleado(empleados, l.id_empleado),
    },
    { key: 'id_tipo_licencia', header: 'Tipo', render: (l) => nombreTipo(l.id_tipo_licencia) },
    { key: 'fecha_inicio', header: 'Desde', render: (l) => l.fecha_inicio },
    { key: 'fecha_fin', header: 'Hasta', render: (l) => l.fecha_fin },
    { key: 'dias_solicitados', header: 'Días', render: (l) => String(l.dias_solicitados) },
    {
      key: 'estado',
      header: 'Estado',
      render: (l) => <StatusChip value={l.estado} colorMap={ESTADO_LICENCIA_COLOR} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (l) => {
        const pendiente = l.estado === 'PENDIENTE';
        return (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              color="success"
              disabled={!pendiente || cambiarEstado.isPending}
              onClick={() => handleCambiarEstado(l, 'APROBADA', 'Aprobar')}
            >
              Aprobar
            </Button>
            <Button
              size="small"
              color="warning"
              disabled={!pendiente || cambiarEstado.isPending}
              onClick={() => handleCambiarEstado(l, 'RECHAZADA', 'Rechazar')}
            >
              Rechazar
            </Button>
            <Button
              size="small"
              color="error"
              disabled={eliminar.isPending}
              onClick={() => handleEliminar(l)}
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
        <Stack direction="row" spacing={2} flexWrap="wrap">
          <TextField
            select
            label="Filtrar por empleado"
            value={filtroEmpleado}
            onChange={(e) => setFiltroEmpleado(e.target.value)}
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
          <TextField
            select
            label="Estado"
            value={filtroEstado}
            onChange={(e) => setFiltroEstado(e.target.value)}
            size="small"
            sx={{ minWidth: 200 }}
          >
            {FILTRO_ESTADOS.map((s) => (
              <MenuItem key={s.value || 'todos'} value={s.value}>
                {s.label}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva licencia
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={licencias}
        getRowKey={(l) => l.id_licencia}
        loading={isLoading}
        emptyMessage="Sin licencias registradas."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nueva licencia</DialogTitle>
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
              label="Tipo de licencia"
              value={form.id_tipo_licencia}
              onChange={(e) => setForm((f) => ({ ...f, id_tipo_licencia: e.target.value }))}
              required
              fullWidth
            >
              {tipos.map((t) => (
                <MenuItem key={t.id_tipo_licencia} value={t.id_tipo_licencia}>
                  {t.nombre_tipo}
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
              label="Fecha de fin"
              type="date"
              value={form.fecha_fin}
              onChange={(e) => setForm((f) => ({ ...f, fecha_fin: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Días solicitados"
              value={form.dias_solicitados}
              onChange={(e) => setForm((f) => ({ ...f, dias_solicitados: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Motivo"
              value={form.motivo}
              onChange={(e) => setForm((f) => ({ ...f, motivo: e.target.value }))}
              multiline
              minRows={2}
              required
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleCrear} disabled={crear.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default BeneficiosLicenciasPage;
