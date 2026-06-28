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
  configuracionIntegracionService,
  mapeoCampoService,
  logsIntegracionService,
  ESTADO_INTEGRACION_COLOR,
  type ConfiguracionIntegracion,
  type ConfiguracionIntegracionPayload,
  type MapeoCampo,
  type MapeoCampoPayload,
  type LogIntegracion,
} from '../../services/integracionB2bService';
import { integracionB2bKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

// ─────────────────────────────────────────────────────────────────────────────
// Configuraciones de integración (CRUD)
// ─────────────────────────────────────────────────────────────────────────────

interface ConfiguracionForm {
  nombre_integracion: string;
  tipo_integracion: string;
  url_endpoint: string;
  credenciales_json: string;
  formato_datos: string;
  activo: boolean;
}

const CONFIGURACION_VACIA: ConfiguracionForm = {
  nombre_integracion: '',
  tipo_integracion: '',
  url_endpoint: '',
  credenciales_json: '{}',
  formato_datos: 'JSON',
  activo: true,
};

interface ConfiguracionesSeccionProps {
  empresaId: string;
}

const ConfiguracionesSeccion: React.FC<ConfiguracionesSeccionProps> = ({ empresaId }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ConfiguracionIntegracion | null>(null);
  const [form, setForm] = useState<ConfiguracionForm>(CONFIGURACION_VACIA);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: integracionB2bKeys.configuraciones(empresaId),
    queryFn: () =>
      configuracionIntegracionService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: integracionB2bKeys.configuracionesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(CONFIGURACION_VACIA);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: ConfiguracionIntegracion) => {
    setEditando(c);
    setForm({
      nombre_integracion: c.nombre_integracion,
      tipo_integracion: c.tipo_integracion,
      url_endpoint: c.url_endpoint ?? '',
      credenciales_json: JSON.stringify(c.credenciales_json ?? {}, null, 2),
      formato_datos: c.formato_datos,
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ConfiguracionIntegracionPayload) =>
      editando
        ? configuracionIntegracionService.update(editando.id_configuracion, payload)
        : configuracionIntegracionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo guardar la configuración.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => configuracionIntegracionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la configuración.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_integracion.trim()) {
      setErrorMsg('Indique el nombre de la integración.');
      return;
    }
    if (!form.tipo_integracion.trim()) {
      setErrorMsg('Indique el tipo de integración.');
      return;
    }
    if (!form.formato_datos.trim()) {
      setErrorMsg('Indique el formato de datos.');
      return;
    }
    let credenciales: unknown;
    try {
      credenciales = JSON.parse(form.credenciales_json || '{}');
    } catch {
      setErrorMsg('Las credenciales JSON no son válidas.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      nombre_integracion: form.nombre_integracion.trim(),
      tipo_integracion: form.tipo_integracion.trim(),
      url_endpoint: form.url_endpoint.trim() || null,
      credenciales_json: credenciales,
      formato_datos: form.formato_datos.trim(),
      activo: form.activo,
    });
  };

  const handleEliminar = (c: ConfiguracionIntegracion) => {
    if (window.confirm('¿Eliminar esta configuración de integración?')) {
      eliminar.mutate(c.id_configuracion);
    }
  };

  const columns: Column<ConfiguracionIntegracion>[] = [
    {
      key: 'nombre_integracion',
      header: 'Nombre',
      render: (c) => c.nombre_integracion,
    },
    { key: 'tipo_integracion', header: 'Tipo', render: (c) => c.tipo_integracion },
    {
      key: 'url_endpoint',
      header: 'Endpoint',
      render: (c) => c.url_endpoint || '—',
    },
    { key: 'formato_datos', header: 'Formato', render: (c) => c.formato_datos },
    {
      key: 'activo',
      header: 'Activo',
      render: (c) => <StatusChip value={c.activo ?? true} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(c)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(c)}
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
          Nueva configuración
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
        getRowKey={(c) => c.id_configuracion}
        loading={isLoading}
        emptyMessage="Sin configuraciones de integración. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>
          {editando ? 'Editar configuración' : 'Nueva configuración'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre de la integración"
              value={form.nombre_integracion}
              onChange={(e) =>
                setForm((f) => ({ ...f, nombre_integracion: e.target.value }))
              }
              required
              fullWidth
            />
            <TextField
              label="Tipo de integración"
              value={form.tipo_integracion}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_integracion: e.target.value }))
              }
              helperText="Ej.: REST, SOAP, EDI, Webhook."
              required
              fullWidth
            />
            <TextField
              label="URL del endpoint"
              value={form.url_endpoint}
              onChange={(e) => setForm((f) => ({ ...f, url_endpoint: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Formato de datos"
              value={form.formato_datos}
              onChange={(e) => setForm((f) => ({ ...f, formato_datos: e.target.value }))}
              helperText="Ej.: JSON, XML, CSV."
              fullWidth
            />
            <TextField
              label="Credenciales JSON"
              value={form.credenciales_json}
              onChange={(e) =>
                setForm((f) => ({ ...f, credenciales_json: e.target.value }))
              }
              multiline
              minRows={3}
              helperText="Credenciales o parámetros de conexión (objeto JSON)."
              fullWidth
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Activa"
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
// Mapeo de campos (CRUD, filtrado por configuración)
// ─────────────────────────────────────────────────────────────────────────────

interface MapeoForm {
  nombre_campo_interno: string;
  nombre_campo_externo: string;
  activo: boolean;
}

const MAPEO_VACIO: MapeoForm = {
  nombre_campo_interno: '',
  nombre_campo_externo: '',
  activo: true,
};

interface MapeoSeccionProps {
  configuraciones: ConfiguracionIntegracion[];
}

const MapeoSeccion: React.FC<MapeoSeccionProps> = ({ configuraciones }) => {
  const queryClient = useQueryClient();
  const [configuracionId, setConfiguracionId] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<MapeoCampo | null>(null);
  const [form, setForm] = useState<MapeoForm>(MAPEO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: integracionB2bKeys.mapeos(configuracionId || null),
    queryFn: () =>
      mapeoCampoService.getAll({ configuracion: configuracionId || undefined }),
    enabled: !!configuracionId,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: integracionB2bKeys.mapeosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(MAPEO_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (m: MapeoCampo) => {
    setEditando(m);
    setForm({
      nombre_campo_interno: m.nombre_campo_interno,
      nombre_campo_externo: m.nombre_campo_externo,
      activo: m.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: MapeoCampoPayload) =>
      editando
        ? mapeoCampoService.update(editando.id_mapeo_campo, payload)
        : mapeoCampoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el mapeo.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => mapeoCampoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el mapeo.')),
  });

  const handleGuardar = () => {
    if (!configuracionId) {
      setErrorMsg('Seleccione una configuración.');
      return;
    }
    if (!form.nombre_campo_interno.trim()) {
      setErrorMsg('Indique el campo interno.');
      return;
    }
    if (!form.nombre_campo_externo.trim()) {
      setErrorMsg('Indique el campo externo.');
      return;
    }
    guardar.mutate({
      id_configuracion_integracion: configuracionId,
      nombre_campo_interno: form.nombre_campo_interno.trim(),
      nombre_campo_externo: form.nombre_campo_externo.trim(),
      activo: form.activo,
    });
  };

  const handleEliminar = (m: MapeoCampo) => {
    if (window.confirm('¿Eliminar este mapeo de campo?')) {
      eliminar.mutate(m.id_mapeo_campo);
    }
  };

  const columns: Column<MapeoCampo>[] = [
    {
      key: 'nombre_campo_interno',
      header: 'Campo interno',
      render: (m) => m.nombre_campo_interno,
    },
    {
      key: 'nombre_campo_externo',
      header: 'Campo externo',
      render: (m) => m.nombre_campo_externo,
    },
    {
      key: 'activo',
      header: 'Activo',
      render: (m) => <StatusChip value={m.activo ?? true} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (m) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(m)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(m)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 2 }}
      >
        <TextField
          select
          label="Configuración"
          value={configuracionId}
          onChange={(e) => setConfiguracionId(e.target.value)}
          sx={{ minWidth: 320 }}
        >
          <MenuItem value="">— Seleccione una configuración —</MenuItem>
          {configuraciones.map((c) => (
            <MenuItem key={c.id_configuracion} value={c.id_configuracion}>
              {c.nombre_integracion}
            </MenuItem>
          ))}
        </TextField>
        <Button
          variant="contained"
          startIcon={<AddOutlined />}
          disabled={!configuracionId}
          onClick={abrirCrear}
        >
          Nuevo mapeo
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      {!configuracionId ? (
        <Alert severity="info">
          Seleccione una configuración para ver y editar su mapeo de campos.
        </Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={filas}
          getRowKey={(m) => m.id_mapeo_campo}
          loading={isLoading}
          emptyMessage="Esta configuración no tiene mapeos de campo."
        />
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar mapeo' : 'Nuevo mapeo'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Campo interno"
              value={form.nombre_campo_interno}
              onChange={(e) =>
                setForm((f) => ({ ...f, nombre_campo_interno: e.target.value }))
              }
              helperText="Nombre del campo en Omni."
              required
              fullWidth
            />
            <TextField
              label="Campo externo"
              value={form.nombre_campo_externo}
              onChange={(e) =>
                setForm((f) => ({ ...f, nombre_campo_externo: e.target.value }))
              }
              helperText="Nombre del campo en el sistema externo."
              required
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
// Logs de integración (solo lectura, filtrados por configuración)
// ─────────────────────────────────────────────────────────────────────────────

interface LogsSeccionProps {
  configuraciones: ConfiguracionIntegracion[];
}

const LogsSeccion: React.FC<LogsSeccionProps> = ({ configuraciones }) => {
  const [configuracionId, setConfiguracionId] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: integracionB2bKeys.logs(configuracionId || null),
    queryFn: () =>
      logsIntegracionService.getAll({ configuracion: configuracionId || undefined }),
    enabled: !!configuracionId,
  });

  const columns: Column<LogIntegracion>[] = [
    {
      key: 'fecha_hora',
      header: 'Fecha',
      render: (l) => (l.fecha_hora ?? '').slice(0, 19).replace('T', ' ') || '—',
    },
    {
      key: 'tipo_transaccion',
      header: 'Transacción',
      render: (l) => l.tipo_transaccion,
    },
    {
      key: 'estado_integracion',
      header: 'Estado',
      render: (l) => (
        <StatusChip value={l.estado_integracion} colorMap={ESTADO_INTEGRACION_COLOR} />
      ),
    },
    {
      key: 'duracion_ms',
      header: 'Duración (ms)',
      render: (l) => (l.duracion_ms ?? '—').toString(),
    },
    {
      key: 'mensaje_error',
      header: 'Mensaje',
      render: (l) => l.mensaje_error || '—',
    },
  ];

  return (
    <>
      <Stack direction="row" sx={{ mb: 2 }}>
        <TextField
          select
          label="Configuración"
          value={configuracionId}
          onChange={(e) => setConfiguracionId(e.target.value)}
          sx={{ minWidth: 320 }}
        >
          <MenuItem value="">— Seleccione una configuración —</MenuItem>
          {configuraciones.map((c) => (
            <MenuItem key={c.id_configuracion} value={c.id_configuracion}>
              {c.nombre_integracion}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      {!configuracionId ? (
        <Alert severity="info">
          Seleccione una configuración para ver su bitácora de integración.
        </Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={filas}
          getRowKey={(l) => l.id_log_integracion}
          loading={isLoading}
          emptyMessage="Esta configuración no registró transacciones."
        />
      )}
    </>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Página contenedora con tabs
// ─────────────────────────────────────────────────────────────────────────────

const IntegracionB2bPage: React.FC = () => {
  const empresaId = getEmpresaId() || '';
  const [tab, setTab] = useState(0);

  const { data: configuraciones = [] } = useQuery({
    queryKey: integracionB2bKeys.configuraciones(empresaId),
    queryFn: () =>
      configuracionIntegracionService.getAll({ empresa: empresaId || undefined }),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Integración B2B"
        subtitle="Configuración de integraciones con sistemas externos, mapeo de campos y bitácora de transacciones."
      />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Configuraciones" />
        <Tab label="Mapeo de campos" />
        <Tab label="Logs" />
      </Tabs>

      {tab === 0 && <ConfiguracionesSeccion empresaId={empresaId} />}
      {tab === 1 && <MapeoSeccion configuraciones={configuraciones} />}
      {tab === 2 && <LogsSeccion configuraciones={configuraciones} />}
    </PageContainer>
  );
};

export default IntegracionB2bPage;
