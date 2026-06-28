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
  plantillasMigracionService,
  procesosMigracionService,
  detallesErrorMigracionService,
  ESTADO_PROCESO_OPCIONES,
  ESTADO_PROCESO_COLOR,
  type PlantillaMigracion,
  type PlantillaMigracionPayload,
  type ProcesoMigracion,
  type ProcesoMigracionPayload,
  type DetalleErrorMigracion,
  type EstadoProceso,
} from '../../services/migracionDatosService';
import { migracionDatosKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const estadoProcesoLabel = (v: string): string =>
  ESTADO_PROCESO_OPCIONES.find((o) => o.value === v)?.label ?? v;

const plantillaLabel = (plantillas: PlantillaMigracion[], id: string): string =>
  plantillas.find((p) => p.id_plantilla_migracion === id)?.nombre_plantilla ?? id;

// ─────────────────────────────────────────────────────────────────────────────
// Plantillas de migración (catálogo global; escritura solo superusuario)
// ─────────────────────────────────────────────────────────────────────────────

interface PlantillaForm {
  nombre_plantilla: string;
  modulo_destino: string;
  modelo_destino: string;
  formato_archivo: string;
  estructura_json: string;
  activo: boolean;
}

const PLANTILLA_VACIA: PlantillaForm = {
  nombre_plantilla: '',
  modulo_destino: '',
  modelo_destino: '',
  formato_archivo: 'CSV',
  estructura_json: '{}',
  activo: true,
};

const PlantillasSeccion: React.FC = () => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<PlantillaMigracion | null>(null);
  const [form, setForm] = useState<PlantillaForm>(PLANTILLA_VACIA);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: migracionDatosKeys.plantillas(),
    queryFn: () => plantillasMigracionService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: migracionDatosKeys.plantillasAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(PLANTILLA_VACIA);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (p: PlantillaMigracion) => {
    setEditando(p);
    setForm({
      nombre_plantilla: p.nombre_plantilla,
      modulo_destino: p.modulo_destino,
      modelo_destino: p.modelo_destino,
      formato_archivo: p.formato_archivo,
      estructura_json: JSON.stringify(p.estructura_json ?? {}, null, 2),
      activo: p.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: PlantillaMigracionPayload) =>
      editando
        ? plantillasMigracionService.update(editando.id_plantilla_migracion, payload)
        : plantillasMigracionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) =>
      // El backend responde 403 a usuarios no superusuario: mensajeDeError lo
      // muestra sin romper (no se cierra el diálogo).
      setErrorMsg(mensajeDeError(e, 'No se pudo guardar la plantilla.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => plantillasMigracionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la plantilla.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_plantilla.trim()) {
      setErrorMsg('Indique el nombre de la plantilla.');
      return;
    }
    if (!form.modulo_destino.trim()) {
      setErrorMsg('Indique el módulo destino.');
      return;
    }
    if (!form.modelo_destino.trim()) {
      setErrorMsg('Indique el modelo destino.');
      return;
    }
    let estructura: unknown;
    try {
      estructura = JSON.parse(form.estructura_json || '{}');
    } catch {
      setErrorMsg('La estructura JSON no es válida.');
      return;
    }
    guardar.mutate({
      nombre_plantilla: form.nombre_plantilla.trim(),
      modulo_destino: form.modulo_destino.trim(),
      modelo_destino: form.modelo_destino.trim(),
      formato_archivo: form.formato_archivo.trim(),
      estructura_json: estructura,
      activo: form.activo,
    });
  };

  const handleEliminar = (p: PlantillaMigracion) => {
    if (window.confirm('¿Eliminar esta plantilla de migración?')) {
      eliminar.mutate(p.id_plantilla_migracion);
    }
  };

  const columns: Column<PlantillaMigracion>[] = [
    { key: 'nombre_plantilla', header: 'Nombre', render: (p) => p.nombre_plantilla },
    { key: 'modulo_destino', header: 'Módulo destino', render: (p) => p.modulo_destino },
    { key: 'modelo_destino', header: 'Modelo destino', render: (p) => p.modelo_destino },
    { key: 'formato_archivo', header: 'Formato', render: (p) => p.formato_archivo },
    { key: 'activo', header: 'Activo', render: (p) => <StatusChip value={p.activo ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(p)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(p)}
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
          Nueva plantilla
        </Button>
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        Las plantillas son un catálogo global. Solo un superusuario puede crearlas,
        editarlas o eliminarlas; el resto de usuarios puede consultarlas.
      </Alert>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={filas}
        getRowKey={(p) => p.id_plantilla_migracion}
        loading={isLoading}
        emptyMessage="Sin plantillas de migración."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar plantilla' : 'Nueva plantilla'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre de la plantilla"
              value={form.nombre_plantilla}
              onChange={(e) => setForm((f) => ({ ...f, nombre_plantilla: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Módulo destino"
              value={form.modulo_destino}
              onChange={(e) => setForm((f) => ({ ...f, modulo_destino: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Modelo destino"
              value={form.modelo_destino}
              onChange={(e) => setForm((f) => ({ ...f, modelo_destino: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Formato de archivo"
              value={form.formato_archivo}
              onChange={(e) => setForm((f) => ({ ...f, formato_archivo: e.target.value }))}
              helperText="Ej.: CSV, XLSX, JSON."
              fullWidth
            />
            <TextField
              label="Estructura JSON"
              value={form.estructura_json}
              onChange={(e) => setForm((f) => ({ ...f, estructura_json: e.target.value }))}
              multiline
              minRows={3}
              helperText="Mapeo de columnas del archivo a campos del modelo."
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
// Procesos de migración
// ─────────────────────────────────────────────────────────────────────────────

interface ProcesoForm {
  id_plantilla_migracion: string;
  id_usuario_ejecutor: string;
  estado_proceso: EstadoProceso;
  ruta_archivo_cargado: string;
}

const PROCESO_VACIO: ProcesoForm = {
  id_plantilla_migracion: '',
  id_usuario_ejecutor: '',
  estado_proceso: 'PENDIENTE',
  ruta_archivo_cargado: '',
};

interface ProcesosSeccionProps {
  empresaId: string;
  plantillas: PlantillaMigracion[];
}

const ProcesosSeccion: React.FC<ProcesosSeccionProps> = ({ empresaId, plantillas }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<ProcesoForm>(PROCESO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: migracionDatosKeys.procesos(empresaId),
    queryFn: () => procesosMigracionService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: migracionDatosKeys.procesosAll() });

  const abrirCrear = () => {
    setForm(PROCESO_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ProcesoMigracionPayload) =>
      procesosMigracionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo crear el proceso.')),
  });

  const handleGuardar = () => {
    if (!form.id_plantilla_migracion) {
      setErrorMsg('Seleccione la plantilla.');
      return;
    }
    if (!form.id_usuario_ejecutor.trim()) {
      setErrorMsg('Indique el usuario ejecutor.');
      return;
    }
    if (!form.ruta_archivo_cargado.trim()) {
      setErrorMsg('Indique la ruta del archivo cargado.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_plantilla_migracion: form.id_plantilla_migracion,
      id_usuario_ejecutor: form.id_usuario_ejecutor.trim(),
      estado_proceso: form.estado_proceso,
      total_registros_procesados: 0,
      total_registros_exitosos: 0,
      total_registros_fallidos: 0,
      ruta_archivo_cargado: form.ruta_archivo_cargado.trim(),
      ruta_archivo_errores: null,
    });
  };

  const columns: Column<ProcesoMigracion>[] = [
    {
      key: 'plantilla',
      header: 'Plantilla',
      render: (p) => plantillaLabel(plantillas, p.id_plantilla_migracion),
    },
    {
      key: 'estado_proceso',
      header: 'Estado',
      render: (p) => (
        <StatusChip
          value={p.estado_proceso}
          label={estadoProcesoLabel(p.estado_proceso)}
          colorMap={ESTADO_PROCESO_COLOR}
        />
      ),
    },
    {
      key: 'procesados',
      header: 'Procesados',
      render: (p) => p.total_registros_procesados ?? 0,
    },
    {
      key: 'exitosos',
      header: 'Exitosos',
      render: (p) => p.total_registros_exitosos ?? 0,
    },
    {
      key: 'fallidos',
      header: 'Fallidos',
      render: (p) => p.total_registros_fallidos ?? 0,
    },
    {
      key: 'fecha_inicio',
      header: 'Inicio',
      render: (p) => (p.fecha_inicio ?? '').slice(0, 10) || '—',
    },
  ];

  return (
    <>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nuevo proceso
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
        getRowKey={(p) => p.id_proceso_migracion}
        loading={isLoading}
        emptyMessage="Sin procesos de migración. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nuevo proceso de migración</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Plantilla"
              value={form.id_plantilla_migracion}
              onChange={(e) =>
                setForm((f) => ({ ...f, id_plantilla_migracion: e.target.value }))
              }
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {plantillas.map((p) => (
                <MenuItem key={p.id_plantilla_migracion} value={p.id_plantilla_migracion}>
                  {p.nombre_plantilla}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Usuario ejecutor"
              value={form.id_usuario_ejecutor}
              onChange={(e) =>
                setForm((f) => ({ ...f, id_usuario_ejecutor: e.target.value }))
              }
              helperText="Identificador del usuario que ejecuta la migración."
              required
              fullWidth
            />
            <TextField
              select
              label="Estado"
              value={form.estado_proceso}
              onChange={(e) =>
                setForm((f) => ({ ...f, estado_proceso: e.target.value as EstadoProceso }))
              }
              fullWidth
            >
              {ESTADO_PROCESO_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Ruta del archivo cargado"
              value={form.ruta_archivo_cargado}
              onChange={(e) =>
                setForm((f) => ({ ...f, ruta_archivo_cargado: e.target.value }))
              }
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

// ─────────────────────────────────────────────────────────────────────────────
// Errores de migración (solo lectura, filtrados por proceso)
// ─────────────────────────────────────────────────────────────────────────────

interface ErroresSeccionProps {
  procesos: ProcesoMigracion[];
  plantillas: PlantillaMigracion[];
}

const ErroresSeccion: React.FC<ErroresSeccionProps> = ({ procesos, plantillas }) => {
  const [procesoId, setProcesoId] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: migracionDatosKeys.errores(procesoId || null),
    queryFn: () => detallesErrorMigracionService.getAll({ proceso: procesoId || undefined }),
    enabled: !!procesoId,
  });

  const procesoLabel = (p: ProcesoMigracion): string =>
    `${plantillaLabel(plantillas, p.id_plantilla_migracion)} — ${estadoProcesoLabel(
      p.estado_proceso,
    )}`;

  const columns: Column<DetalleErrorMigracion>[] = [
    {
      key: 'numero_fila_archivo',
      header: 'Fila',
      render: (d) => (d.numero_fila_archivo ?? '—').toString(),
    },
    { key: 'campo_error', header: 'Campo', render: (d) => d.campo_error || '—' },
    { key: 'mensaje_error', header: 'Mensaje', render: (d) => d.mensaje_error },
    {
      key: 'fecha_registro_error',
      header: 'Fecha',
      render: (d) => (d.fecha_registro_error ?? '').slice(0, 10) || '—',
    },
  ];

  return (
    <>
      <Stack direction="row" sx={{ mb: 2 }}>
        <TextField
          select
          label="Proceso"
          value={procesoId}
          onChange={(e) => setProcesoId(e.target.value)}
          sx={{ minWidth: 320 }}
        >
          <MenuItem value="">— Seleccione un proceso —</MenuItem>
          {procesos.map((p) => (
            <MenuItem key={p.id_proceso_migracion} value={p.id_proceso_migracion}>
              {procesoLabel(p)}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      {!procesoId ? (
        <Alert severity="info">
          Seleccione un proceso para ver sus errores de migración.
        </Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={filas}
          getRowKey={(d) => d.id_detalle_error}
          loading={isLoading}
          emptyMessage="Este proceso no registró errores."
        />
      )}
    </>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Página contenedora con tabs
// ─────────────────────────────────────────────────────────────────────────────

const MigracionDatosPage: React.FC = () => {
  const empresaId = getEmpresaId() || '';
  const [tab, setTab] = useState(0);

  const { data: plantillas = [] } = useQuery({
    queryKey: migracionDatosKeys.plantillas(),
    queryFn: () => plantillasMigracionService.getAll(),
  });

  const { data: procesos = [] } = useQuery({
    queryKey: migracionDatosKeys.procesos(empresaId),
    queryFn: () => procesosMigracionService.getAll({ empresa: empresaId || undefined }),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Migración de Datos"
        subtitle="Plantillas de importación y procesos de migración con su detalle de errores."
      />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Plantillas" />
        <Tab label="Procesos" />
        <Tab label="Errores" />
      </Tabs>

      {tab === 0 && <PlantillasSeccion />}
      {tab === 1 && <ProcesosSeccion empresaId={empresaId} plantillas={plantillas} />}
      {tab === 2 && <ErroresSeccion procesos={procesos} plantillas={plantillas} />}
    </PageContainer>
  );
};

export default MigracionDatosPage;
