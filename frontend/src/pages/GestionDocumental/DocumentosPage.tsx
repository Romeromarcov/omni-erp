import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import UploadFileOutlined from '@mui/icons-material/UploadFileOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  carpetasService,
  documentosService,
  vinculosDocumentoService,
  permisosDocumentoService,
  type Carpeta,
  type CarpetaPayload,
  type Documento,
  type VinculoDocumento,
  type VinculoDocumentoPayload,
  type PermisoDocumento,
  type PermisoDocumentoPayload,
} from '../../services/gestionDocumentalService';
import { gestionDocumentalKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

// ── Carpetas ──────────────────────────────────────────────────────────────────

interface CarpetaForm {
  nombre_carpeta: string;
  id_carpeta_padre: string;
  es_publica: boolean;
}

const CARPETA_VACIA: CarpetaForm = {
  nombre_carpeta: '',
  id_carpeta_padre: '',
  es_publica: false,
};

const DocumentosPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [carpetaActiva, setCarpetaActiva] = useState<string>('');
  const [busqueda, setBusqueda] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Diálogos
  const [carpetaDialogOpen, setCarpetaDialogOpen] = useState(false);
  const [carpetaEditando, setCarpetaEditando] = useState<Carpeta | null>(null);
  const [carpetaForm, setCarpetaForm] = useState<CarpetaForm>(CARPETA_VACIA);
  const [subirDialogOpen, setSubirDialogOpen] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [descripcion, setDescripcion] = useState('');
  const [detalle, setDetalle] = useState<Documento | null>(null);

  const { data: carpetas = [] } = useQuery({
    queryKey: gestionDocumentalKeys.carpetas(empresaId),
    queryFn: () => carpetasService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: documentos = [], isLoading } = useQuery({
    queryKey: gestionDocumentalKeys.documentos(empresaId, carpetaActiva || null, busqueda || null),
    queryFn: () =>
      documentosService.getAll({
        empresa: empresaId || undefined,
        carpeta: carpetaActiva || undefined,
        search: busqueda.trim() || undefined,
      }),
  });

  const invalidarCarpetas = () =>
    queryClient.invalidateQueries({ queryKey: gestionDocumentalKeys.all() });
  const invalidarDocumentos = () =>
    queryClient.invalidateQueries({ queryKey: gestionDocumentalKeys.all() });

  // ── Carpetas: crear/editar/eliminar ──
  const abrirCrearCarpeta = () => {
    setCarpetaEditando(null);
    setCarpetaForm({ ...CARPETA_VACIA, id_carpeta_padre: carpetaActiva });
    setErrorMsg('');
    setCarpetaDialogOpen(true);
  };

  const abrirEditarCarpeta = (c: Carpeta) => {
    setCarpetaEditando(c);
    setCarpetaForm({
      nombre_carpeta: c.nombre_carpeta,
      id_carpeta_padre: c.id_carpeta_padre ?? '',
      es_publica: c.es_publica ?? false,
    });
    setErrorMsg('');
    setCarpetaDialogOpen(true);
  };

  const guardarCarpeta = useMutation({
    mutationFn: (payload: CarpetaPayload) =>
      carpetaEditando
        ? carpetasService.update(carpetaEditando.id_carpeta, payload)
        : carpetasService.create(payload),
    onSuccess: () => {
      setCarpetaDialogOpen(false);
      invalidarCarpetas();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la carpeta.')),
  });

  const eliminarCarpeta = useMutation({
    mutationFn: (id: string) => carpetasService.remove(id),
    onSuccess: () => {
      if (carpetaActiva) setCarpetaActiva('');
      invalidarCarpetas();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la carpeta.')),
  });

  const handleGuardarCarpeta = () => {
    if (!carpetaForm.nombre_carpeta.trim()) {
      setErrorMsg('Indique el nombre de la carpeta.');
      return;
    }
    guardarCarpeta.mutate({
      id_empresa: empresaId,
      nombre_carpeta: carpetaForm.nombre_carpeta.trim(),
      id_carpeta_padre: carpetaForm.id_carpeta_padre || null,
      es_publica: carpetaForm.es_publica,
      activo: true,
      id_usuario_creacion: carpetaEditando?.id_usuario_creacion ?? '',
    });
  };

  const handleEliminarCarpeta = (c: Carpeta) => {
    if (window.confirm(`¿Eliminar la carpeta "${c.nombre_carpeta}"?`)) {
      eliminarCarpeta.mutate(c.id_carpeta);
    }
  };

  // ── Documentos: subir/descargar/eliminar ──
  const abrirSubir = () => {
    setArchivo(null);
    setDescripcion('');
    setErrorMsg('');
    setSubirDialogOpen(true);
  };

  const subir = useMutation({
    mutationFn: () => {
      if (!archivo) throw new Error('Seleccione un archivo.');
      return documentosService.subir({
        empresaId,
        archivo,
        carpetaId: carpetaActiva || null,
        descripcion: descripcion.trim() || undefined,
      });
    },
    onSuccess: () => {
      setSubirDialogOpen(false);
      invalidarDocumentos();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo subir el documento.')),
  });

  const handleSubir = () => {
    if (!archivo) {
      setErrorMsg('Seleccione un archivo.');
      return;
    }
    subir.mutate();
  };

  const descargar = useMutation({
    mutationFn: (id: string) => documentosService.descargar(id),
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo descargar el documento.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => documentosService.eliminarArchivo(id),
    onSuccess: invalidarDocumentos,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el documento.')),
  });

  const handleEliminar = (d: Documento) => {
    if (window.confirm(`¿Eliminar el documento "${d.nombre_archivo}"?`)) {
      eliminar.mutate(d.id_documento);
    }
  };

  const columns: Column<Documento>[] = [
    { key: 'nombre_archivo', header: 'Archivo', render: (d) => d.nombre_archivo },
    { key: 'tipo_contenido', header: 'Tipo', render: (d) => d.tipo_contenido || '—' },
    {
      key: 'tamano_bytes',
      header: 'Tamaño',
      render: (d) => `${(Number(d.tamano_bytes || 0) / 1024).toFixed(1)} KB`,
    },
    { key: 'descripcion', header: 'Descripción', render: (d) => d.descripcion || '—' },
    { key: 'activo', header: 'Activo', render: (d) => <StatusChip value={d.activo ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (d) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(d)}>
            Vínculos / Permisos
          </Button>
          <Button
            size="small"
            disabled={descargar.isPending}
            onClick={() => descargar.mutate(d.id_documento)}
          >
            Descargar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(d)}
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
        title="Documentos"
        subtitle="Gestión documental: carpetas, archivos adjuntos, vínculos y permisos."
        actions={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<AddOutlined />} onClick={abrirCrearCarpeta}>
              Nueva carpeta
            </Button>
            <Button variant="contained" startIcon={<UploadFileOutlined />} onClick={abrirSubir}>
              Subir documento
            </Button>
          </Stack>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        {/* Árbol/lista de carpetas */}
        <Box sx={{ minWidth: { md: 260 } }}>
          <Typography variant="subtitle2" gutterBottom>
            Carpetas
          </Typography>
          <Stack spacing={0.5}>
            <Button
              size="small"
              variant={carpetaActiva === '' ? 'contained' : 'text'}
              onClick={() => setCarpetaActiva('')}
              sx={{ justifyContent: 'flex-start' }}
            >
              Todas
            </Button>
            {carpetas.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Sin carpetas.
              </Typography>
            ) : (
              carpetas.map((c) => (
                <Stack
                  key={c.id_carpeta}
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                >
                  <Button
                    size="small"
                    variant={carpetaActiva === c.id_carpeta ? 'contained' : 'text'}
                    onClick={() => setCarpetaActiva(c.id_carpeta)}
                    sx={{ justifyContent: 'flex-start', flexGrow: 1 }}
                  >
                    {c.nombre_carpeta}
                    {c.es_publica ? ' · pública' : ''}
                  </Button>
                  <IconButton
                    size="small"
                    aria-label={`Editar carpeta ${c.nombre_carpeta}`}
                    onClick={() => abrirEditarCarpeta(c)}
                  >
                    <AddOutlined fontSize="inherit" />
                  </IconButton>
                  <IconButton
                    size="small"
                    aria-label={`Eliminar carpeta ${c.nombre_carpeta}`}
                    disabled={eliminarCarpeta.isPending}
                    onClick={() => handleEliminarCarpeta(c)}
                  >
                    <CloseOutlined fontSize="inherit" />
                  </IconButton>
                </Stack>
              ))
            )}
          </Stack>
        </Box>

        {/* Lista de documentos */}
        <Box sx={{ flexGrow: 1 }}>
          <TextField
            label="Buscar"
            placeholder="Nombre del archivo…"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            size="small"
            sx={{ mb: 2, maxWidth: 360 }}
            fullWidth
          />
          <DataTable
            columns={columns}
            rows={documentos}
            getRowKey={(d) => d.id_documento}
            loading={isLoading}
            emptyMessage="Sin documentos. Sube el primero."
          />
        </Box>
      </Stack>

      {/* Diálogo: crear/editar carpeta */}
      <Dialog
        open={carpetaDialogOpen}
        onClose={() => setCarpetaDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{carpetaEditando ? 'Editar carpeta' : 'Nueva carpeta'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre de la carpeta"
              value={carpetaForm.nombre_carpeta}
              onChange={(e) =>
                setCarpetaForm((f) => ({ ...f, nombre_carpeta: e.target.value }))
              }
              required
              fullWidth
            />
            <TextField
              select
              label="Carpeta padre"
              value={carpetaForm.id_carpeta_padre}
              onChange={(e) =>
                setCarpetaForm((f) => ({ ...f, id_carpeta_padre: e.target.value }))
              }
              fullWidth
            >
              <MenuItem value="">(Raíz)</MenuItem>
              {carpetas
                .filter((c) => c.id_carpeta !== carpetaEditando?.id_carpeta)
                .map((c) => (
                  <MenuItem key={c.id_carpeta} value={c.id_carpeta}>
                    {c.nombre_carpeta}
                  </MenuItem>
                ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={carpetaForm.es_publica}
                  onChange={(e) =>
                    setCarpetaForm((f) => ({ ...f, es_publica: e.target.checked }))
                  }
                />
              }
              label="Carpeta pública"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCarpetaDialogOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleGuardarCarpeta}
            disabled={guardarCarpeta.isPending}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Diálogo: subir documento */}
      <Dialog open={subirDialogOpen} onClose={() => setSubirDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Subir documento</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Button variant="outlined" component="label" startIcon={<UploadFileOutlined />}>
              {archivo ? archivo.name : 'Seleccionar archivo'}
              <input
                type="file"
                hidden
                aria-label="Archivo"
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              />
            </Button>
            <TextField
              label="Descripción"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
            <Typography variant="body2" color="text.secondary">
              {carpetaActiva
                ? 'Se subirá a la carpeta seleccionada.'
                : 'Se subirá sin carpeta (raíz).'}
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSubirDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleSubir} disabled={subir.isPending}>
            Subir
          </Button>
        </DialogActions>
      </Dialog>

      {/* Drawer: vínculos y permisos del documento */}
      <Drawer
        anchor="right"
        open={Boolean(detalle)}
        onClose={() => setDetalle(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 520 }, p: 3 } } }}
      >
        {detalle && <DetalleDocumento documento={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle del documento (vínculos + permisos) ───────────────────────────────

interface DetalleDocumentoProps {
  documento: Documento;
  onClose: () => void;
}

const DetalleDocumento: React.FC<DetalleDocumentoProps> = ({ documento, onClose }) => {
  const documentoId = documento.id_documento;
  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{documento.nombre_archivo}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {documento.tipo_contenido} · versión {documento.version ?? 1}
      </Typography>

      <Divider />

      <VinculosDocumento documentoId={documentoId} />

      <Divider />

      <PermisosDocumento documentoId={documentoId} />
    </Stack>
  );
};

// ── Vínculos (CRUD inline) ────────────────────────────────────────────────────

interface VinculoForm {
  id_entidad_origen: string;
  nombre_modelo_origen: string;
  tipo_vinculo: string;
}

const VINCULO_VACIO: VinculoForm = {
  id_entidad_origen: '',
  nombre_modelo_origen: '',
  tipo_vinculo: '',
};

const VinculosDocumento: React.FC<{ documentoId: string }> = ({ documentoId }) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<VinculoForm>(VINCULO_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: vinculos = [] } = useQuery({
    queryKey: gestionDocumentalKeys.vinculos(documentoId),
    queryFn: () => vinculosDocumentoService.getAll({ documento: documentoId }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gestionDocumentalKeys.vinculos(documentoId) });

  const reset = () => {
    setForm(VINCULO_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: VinculoDocumentoPayload) =>
      editId
        ? vinculosDocumentoService.update(editId, payload)
        : vinculosDocumentoService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el vínculo.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => vinculosDocumentoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el vínculo.')),
  });

  const editar = (v: VinculoDocumento) => {
    setEditId(v.id_vinculo);
    setForm({
      id_entidad_origen: v.id_entidad_origen,
      nombre_modelo_origen: v.nombre_modelo_origen,
      tipo_vinculo: v.tipo_vinculo ?? '',
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_entidad_origen.trim() || !form.nombre_modelo_origen.trim()) {
      setError('Complete la entidad y el modelo de origen.');
      return;
    }
    guardar.mutate({
      id_documento: documentoId,
      id_entidad_origen: form.id_entidad_origen.trim(),
      nombre_modelo_origen: form.nombre_modelo_origen.trim(),
      tipo_vinculo: form.tipo_vinculo.trim() || null,
    });
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Vínculos
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Stack spacing={1} sx={{ mb: 2 }}>
        {vinculos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin vínculos.
          </Typography>
        ) : (
          vinculos.map((v) => (
            <Stack
              key={v.id_vinculo}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {v.nombre_modelo_origen} · {v.id_entidad_origen}
                {v.tipo_vinculo ? ` · ${v.tipo_vinculo}` : ''}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(v)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(v.id_vinculo)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>
      <Stack spacing={1}>
        <TextField
          label="Modelo de origen"
          placeholder="p. ej. gastos.Gasto"
          value={form.nombre_modelo_origen}
          onChange={(e) => setForm((f) => ({ ...f, nombre_modelo_origen: e.target.value }))}
          size="small"
          fullWidth
        />
        <TextField
          label="ID de la entidad"
          value={form.id_entidad_origen}
          onChange={(e) => setForm((f) => ({ ...f, id_entidad_origen: e.target.value }))}
          size="small"
          fullWidth
        />
        <TextField
          label="Tipo de vínculo"
          value={form.tipo_vinculo}
          onChange={(e) => setForm((f) => ({ ...f, tipo_vinculo: e.target.value }))}
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar vínculo' : 'Agregar vínculo'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Box>
  );
};

// ── Permisos (CRUD inline) ────────────────────────────────────────────────────

interface PermisoForm {
  id_usuario: string;
  id_rol: string;
  puede_ver: boolean;
  puede_editar: boolean;
  puede_eliminar: boolean;
}

const PERMISO_VACIO: PermisoForm = {
  id_usuario: '',
  id_rol: '',
  puede_ver: true,
  puede_editar: false,
  puede_eliminar: false,
};

const PermisosDocumento: React.FC<{ documentoId: string }> = ({ documentoId }) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PermisoForm>(PERMISO_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: permisos = [] } = useQuery({
    queryKey: gestionDocumentalKeys.permisos(documentoId),
    queryFn: () => permisosDocumentoService.getAll({ documento: documentoId }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gestionDocumentalKeys.permisos(documentoId) });

  const reset = () => {
    setForm(PERMISO_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: PermisoDocumentoPayload) =>
      editId
        ? permisosDocumentoService.update(editId, payload)
        : permisosDocumentoService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el permiso.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => permisosDocumentoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el permiso.')),
  });

  const editar = (p: PermisoDocumento) => {
    setEditId(p.id_permiso_documento);
    setForm({
      id_usuario: p.id_usuario ?? '',
      id_rol: p.id_rol ?? '',
      puede_ver: p.puede_ver ?? true,
      puede_editar: p.puede_editar ?? false,
      puede_eliminar: p.puede_eliminar ?? false,
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_usuario.trim() && !form.id_rol.trim()) {
      setError('Indique un usuario o un rol.');
      return;
    }
    guardar.mutate({
      id_documento: documentoId,
      id_usuario: form.id_usuario.trim() || null,
      id_rol: form.id_rol.trim() || null,
      puede_ver: form.puede_ver,
      puede_editar: form.puede_editar,
      puede_eliminar: form.puede_eliminar,
    });
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Permisos
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Stack spacing={1} sx={{ mb: 2 }}>
        {permisos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin permisos.
          </Typography>
        ) : (
          permisos.map((p) => (
            <Stack
              key={p.id_permiso_documento}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {p.id_usuario ? `Usuario ${p.id_usuario}` : `Rol ${p.id_rol}`} ·{' '}
                {[p.puede_ver && 'ver', p.puede_editar && 'editar', p.puede_eliminar && 'eliminar']
                  .filter(Boolean)
                  .join(', ') || 'sin permisos'}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(p)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(p.id_permiso_documento)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1}>
          <TextField
            label="ID Usuario"
            value={form.id_usuario}
            onChange={(e) => setForm((f) => ({ ...f, id_usuario: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="ID Rol"
            value={form.id_rol}
            onChange={(e) => setForm((f) => ({ ...f, id_rol: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
        <Stack direction="row" spacing={1}>
          <FormControlLabel
            control={
              <Checkbox
                checked={form.puede_ver}
                onChange={(e) => setForm((f) => ({ ...f, puede_ver: e.target.checked }))}
              />
            }
            label="Ver"
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={form.puede_editar}
                onChange={(e) => setForm((f) => ({ ...f, puede_editar: e.target.checked }))}
              />
            }
            label="Editar"
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={form.puede_eliminar}
                onChange={(e) => setForm((f) => ({ ...f, puede_eliminar: e.target.checked }))}
              />
            }
            label="Eliminar"
          />
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar permiso' : 'Agregar permiso'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Box>
  );
};

export default DocumentosPage;
