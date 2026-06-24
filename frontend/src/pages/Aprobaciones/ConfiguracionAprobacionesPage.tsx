import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  tiposAprobacionService,
  flujosAprobacionService,
  type TipoAprobacion,
  type TipoAprobacionPayload,
  type FlujoAprobacion,
  type FlujoAprobacionPayload,
} from '../../services/aprobacionesService';
import { fetchUsuarios, type Usuario } from '../../services/users';
import { fetchRoles, type Rol } from '../../services/roles';
import { aprobacionesKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

// ─────────────────────────────────────────────────────────────────────────────
// Tipos de aprobación
// ─────────────────────────────────────────────────────────────────────────────

interface TipoForm {
  codigo_tipo: string;
  nombre_tipo: string;
  descripcion: string;
  modulo_origen: string;
  activo: boolean;
}

const TIPO_VACIO: TipoForm = {
  codigo_tipo: '',
  nombre_tipo: '',
  descripcion: '',
  modulo_origen: '',
  activo: true,
};

const TiposAprobacionSeccion: React.FC<{ empresaId: string }> = ({ empresaId }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<TipoAprobacion | null>(null);
  const [form, setForm] = useState<TipoForm>(TIPO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: aprobacionesKeys.tipos(empresaId),
    queryFn: () => tiposAprobacionService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: aprobacionesKeys.tiposAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(TIPO_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (t: TipoAprobacion) => {
    setEditando(t);
    setForm({
      codigo_tipo: t.codigo_tipo,
      nombre_tipo: t.nombre_tipo,
      descripcion: t.descripcion ?? '',
      modulo_origen: t.modulo_origen,
      activo: t.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: TipoAprobacionPayload) =>
      editando
        ? tiposAprobacionService.update(editando.id_tipo_aprobacion, payload)
        : tiposAprobacionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el tipo.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => tiposAprobacionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el tipo.')),
  });

  const handleGuardar = () => {
    if (!form.codigo_tipo.trim() || !form.nombre_tipo.trim() || !form.modulo_origen.trim()) {
      setErrorMsg('Complete código, nombre y módulo de origen.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      codigo_tipo: form.codigo_tipo.trim(),
      nombre_tipo: form.nombre_tipo.trim(),
      descripcion: form.descripcion.trim() || null,
      modulo_origen: form.modulo_origen.trim(),
      activo: form.activo,
    });
  };

  const handleEliminar = (t: TipoAprobacion) => {
    if (window.confirm(`¿Eliminar el tipo "${t.nombre_tipo}"?`)) {
      eliminar.mutate(t.id_tipo_aprobacion);
    }
  };

  const columns: Column<TipoAprobacion>[] = [
    { key: 'codigo_tipo', header: 'Código', render: (t) => t.codigo_tipo },
    { key: 'nombre_tipo', header: 'Nombre', render: (t) => t.nombre_tipo },
    { key: 'modulo_origen', header: 'Módulo', render: (t) => t.modulo_origen },
    { key: 'activo', header: 'Activo', render: (t) => <StatusChip value={t.activo ?? true} /> },
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
          Nuevo tipo
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={filas}
        getRowKey={(t) => t.id_tipo_aprobacion}
        loading={isLoading}
        emptyMessage="Sin tipos de aprobación. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar tipo de aprobación' : 'Nuevo tipo de aprobación'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Código"
              value={form.codigo_tipo}
              onChange={(e) => setForm((f) => ({ ...f, codigo_tipo: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Nombre"
              value={form.nombre_tipo}
              onChange={(e) => setForm((f) => ({ ...f, nombre_tipo: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Módulo de origen"
              value={form.modulo_origen}
              onChange={(e) => setForm((f) => ({ ...f, modulo_origen: e.target.value }))}
              required
              helperText="P. ej. compras, gastos, nomina."
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
            <FormControlLabel
              control={
                <Checkbox
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

// ─────────────────────────────────────────────────────────────────────────────
// Flujos de aprobación (etapas)
// ─────────────────────────────────────────────────────────────────────────────

interface FlujoForm {
  id_tipo_aprobacion: string;
  orden_etapa: string;
  nombre_etapa: string;
  rol_aprobador: string;
  id_usuario_aprobador: string;
  monto_minimo: string;
  monto_maximo: string;
  activo: boolean;
}

const FLUJO_VACIO: FlujoForm = {
  id_tipo_aprobacion: '',
  orden_etapa: '1',
  nombre_etapa: '',
  rol_aprobador: '',
  id_usuario_aprobador: '',
  monto_minimo: '',
  monto_maximo: '',
  activo: true,
};

interface FlujosSeccionProps {
  tipos: TipoAprobacion[];
  usuarios: Usuario[];
  roles: Rol[];
}

const FlujosAprobacionSeccion: React.FC<FlujosSeccionProps> = ({ tipos, usuarios, roles }) => {
  const queryClient = useQueryClient();
  const [filtroTipo, setFiltroTipo] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<FlujoAprobacion | null>(null);
  const [form, setForm] = useState<FlujoForm>(FLUJO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: aprobacionesKeys.flujos(filtroTipo || null),
    queryFn: () => flujosAprobacionService.getAll({ tipo: filtroTipo || undefined }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: aprobacionesKeys.flujosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...FLUJO_VACIO, id_tipo_aprobacion: filtroTipo });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (fl: FlujoAprobacion) => {
    setEditando(fl);
    setForm({
      id_tipo_aprobacion: fl.id_tipo_aprobacion,
      orden_etapa: String(fl.orden_etapa),
      nombre_etapa: fl.nombre_etapa,
      rol_aprobador: fl.rol_aprobador ?? '',
      id_usuario_aprobador: fl.id_usuario_aprobador ?? '',
      monto_minimo: fl.monto_minimo ?? '',
      monto_maximo: fl.monto_maximo ?? '',
      activo: fl.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: FlujoAprobacionPayload) =>
      editando
        ? flujosAprobacionService.update(editando.id_flujo_aprobacion, payload)
        : flujosAprobacionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la etapa.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => flujosAprobacionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la etapa.')),
  });

  const handleGuardar = () => {
    if (!form.id_tipo_aprobacion) {
      setErrorMsg('Seleccione el tipo de aprobación.');
      return;
    }
    if (!form.nombre_etapa.trim()) {
      setErrorMsg('Indique el nombre de la etapa.');
      return;
    }
    const orden = Number(form.orden_etapa);
    if (!Number.isFinite(orden) || orden < 0) {
      setErrorMsg('El orden de etapa debe ser un número válido.');
      return;
    }
    guardar.mutate({
      id_tipo_aprobacion: form.id_tipo_aprobacion,
      orden_etapa: orden,
      nombre_etapa: form.nombre_etapa.trim(),
      rol_aprobador: form.rol_aprobador || null,
      id_usuario_aprobador: form.id_usuario_aprobador || null,
      monto_minimo: form.monto_minimo.trim() || null,
      monto_maximo: form.monto_maximo.trim() || null,
      activo: form.activo,
    });
  };

  const handleEliminar = (fl: FlujoAprobacion) => {
    if (window.confirm(`¿Eliminar la etapa "${fl.nombre_etapa}"?`)) {
      eliminar.mutate(fl.id_flujo_aprobacion);
    }
  };

  const tipoLabel = (id: string) =>
    tipos.find((t) => t.id_tipo_aprobacion === id)?.nombre_tipo ?? id;
  const rolLabel = (id: string | null | undefined) =>
    id ? roles.find((r) => r.id_rol === id)?.nombre_rol ?? id : '—';
  const usuarioLabel = (id: string | null | undefined) =>
    id ? usuarios.find((u) => u.id === id)?.username ?? id : '—';

  const columns: Column<FlujoAprobacion>[] = [
    { key: 'tipo', header: 'Tipo', render: (fl) => tipoLabel(fl.id_tipo_aprobacion) },
    { key: 'orden_etapa', header: 'Orden', render: (fl) => fl.orden_etapa },
    { key: 'nombre_etapa', header: 'Etapa', render: (fl) => fl.nombre_etapa },
    { key: 'rol_aprobador', header: 'Rol', render: (fl) => rolLabel(fl.rol_aprobador) },
    {
      key: 'id_usuario_aprobador',
      header: 'Usuario',
      render: (fl) => usuarioLabel(fl.id_usuario_aprobador),
    },
    {
      key: 'rango',
      header: 'Monto (min–max)',
      render: (fl) => `${fl.monto_minimo ?? '—'} – ${fl.monto_maximo ?? '—'}`,
    },
    { key: 'activo', header: 'Activo', render: (fl) => <StatusChip value={fl.activo ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (fl) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(fl)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(fl)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <Stack direction="row" spacing={2} justifyContent="space-between" sx={{ mb: 2 }}>
        <TextField
          select
          label="Tipo de aprobación"
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          size="small"
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {tipos.map((t) => (
            <MenuItem key={t.id_tipo_aprobacion} value={t.id_tipo_aprobacion}>
              {t.nombre_tipo}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva etapa
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={filas}
        getRowKey={(fl) => fl.id_flujo_aprobacion}
        loading={isLoading}
        emptyMessage="Sin etapas de flujo. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar etapa' : 'Nueva etapa'}</DialogTitle>
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
              label="Orden de etapa"
              type="number"
              value={form.orden_etapa}
              onChange={(e) => setForm((f) => ({ ...f, orden_etapa: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Nombre de la etapa"
              value={form.nombre_etapa}
              onChange={(e) => setForm((f) => ({ ...f, nombre_etapa: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Rol aprobador"
              value={form.rol_aprobador}
              onChange={(e) => setForm((f) => ({ ...f, rol_aprobador: e.target.value }))}
              helperText="Opcional."
              fullWidth
            >
              <MenuItem value="">— Ninguno —</MenuItem>
              {roles.map((r) => (
                <MenuItem key={r.id_rol} value={r.id_rol}>
                  {r.nombre_rol}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Usuario aprobador"
              value={form.id_usuario_aprobador}
              onChange={(e) => setForm((f) => ({ ...f, id_usuario_aprobador: e.target.value }))}
              helperText="Opcional."
              fullWidth
            >
              <MenuItem value="">— Ninguno —</MenuItem>
              {usuarios.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.username}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Monto mínimo"
                value={form.monto_minimo}
                onChange={(e) => setForm((f) => ({ ...f, monto_minimo: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Monto máximo"
                value={form.monto_maximo}
                onChange={(e) => setForm((f) => ({ ...f, monto_maximo: e.target.value }))}
                fullWidth
              />
            </Stack>
            <FormControlLabel
              control={
                <Checkbox
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

// ─────────────────────────────────────────────────────────────────────────────
// Página contenedora con tabs
// ─────────────────────────────────────────────────────────────────────────────

const ConfiguracionAprobacionesPage: React.FC = () => {
  const empresaId = getEmpresaId() || '';
  const [tab, setTab] = useState(0);

  const { data: tipos = [] } = useQuery({
    queryKey: aprobacionesKeys.tipos(empresaId),
    queryFn: () => tiposAprobacionService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: usuarios = [] } = useQuery({
    queryKey: ['core', 'usuarios', empresaId],
    queryFn: () => fetchUsuarios(empresaId || undefined),
  });

  const { data: roles = [] } = useQuery({
    queryKey: ['core', 'roles'],
    queryFn: fetchRoles,
  });

  return (
    <PageContainer>
      <PageHeader
        title="Configuración de Aprobaciones"
        subtitle="Define los tipos de aprobación y las etapas (flujos) con sus aprobadores y rangos de monto."
      />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Tipos de aprobación" />
        <Tab label="Flujos (etapas)" />
      </Tabs>

      {tab === 0 && <TiposAprobacionSeccion empresaId={empresaId} />}
      {tab === 1 && <FlujosAprobacionSeccion tipos={tipos} usuarios={usuarios} roles={roles} />}
    </PageContainer>
  );
};

export default ConfiguracionAprobacionesPage;
