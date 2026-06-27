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
  Divider,
  Drawer,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  listasMaterialesService,
  listasMaterialesDetalleService,
  rutasProduccionService,
  rutasProduccionDetalleService,
  centrosTrabajoService,
  operacionesProduccionService,
  type ListaMateriales,
  type ListaMaterialesPayload,
  type ListaMaterialesDetalle,
  type ListaMaterialesDetallePayload,
  type RutaProduccion,
  type RutaProduccionPayload,
  type RutaProduccionDetalle,
  type RutaProduccionDetallePayload,
  type CentroTrabajo,
  type CentroTrabajoPayload,
} from '../../services/manufacturaMaestrosService';
import { productoInventarioService, unidadesMedidaService, type Producto } from '../../services/inventarioService';
import { manufacturaMaestrosKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPO_CENTRO_OPCIONES = ['MAQUINA', 'MANUAL', 'ENSAMBLE', 'CONTROL_CALIDAD', 'EMPAQUE'];

// Catálogo de productos compartido por los drawers de BOM.
function useProductos() {
  const empresaId = getEmpresaId() || '';
  return useQuery({
    queryKey: ['productos', empresaId],
    queryFn: () => productoInventarioService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });
}

const nombreProducto = (productos: Producto[], id: string): string => {
  const p = productos.find((prod) => prod.id_producto === id);
  return p ? `${p.nombre_producto}${p.sku ? ` (${p.sku})` : ''}` : id;
};

const DatosMaestrosPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  return (
    <PageContainer>
      <PageHeader
        title="Datos Maestros de Manufactura"
        subtitle="Listas de materiales (BOM) y sus componentes, rutas de producción con sus pasos y centros de trabajo: la base que selecciona la Orden de Producción."
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Listas de Materiales" />
        <Tab label="Rutas de Producción" />
        <Tab label="Centros de Trabajo" />
      </Tabs>
      {tab === 0 && <ListasMaterialesTab />}
      {tab === 1 && <RutasProduccionTab />}
      {tab === 2 && <CentrosTrabajoTab />}
    </PageContainer>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Listas de Materiales (BOM)
// ─────────────────────────────────────────────────────────────────────────────

interface BomForm {
  producto_final: string;
  nombre: string;
  descripcion: string;
  referencia_externa: string;
}

const BOM_VACIO: BomForm = { producto_final: '', nombre: '', descripcion: '', referencia_externa: '' };

const ListasMaterialesTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ListaMateriales | null>(null);
  const [form, setForm] = useState<BomForm>(BOM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<ListaMateriales | null>(null);

  const { data: boms = [], isLoading } = useQuery({
    queryKey: manufacturaMaestrosKeys.bomsAll(),
    queryFn: () => listasMaterialesService.getAll(),
  });
  const { data: productos = [] } = useProductos();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: manufacturaMaestrosKeys.bomsAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(BOM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (b: ListaMateriales) => {
    setEditando(b);
    setForm({
      producto_final: b.producto_final,
      nombre: b.nombre,
      descripcion: b.descripcion ?? '',
      referencia_externa: b.referencia_externa ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ListaMaterialesPayload) =>
      editando ? listasMaterialesService.update(editando.id, payload) : listasMaterialesService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la lista de materiales.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => listasMaterialesService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la lista de materiales.')),
  });

  const handleGuardar = () => {
    if (!form.nombre.trim() || !form.producto_final) {
      setErrorMsg('Complete el nombre y el producto a fabricar.');
      return;
    }
    guardar.mutate({
      producto_final: form.producto_final,
      nombre: form.nombre.trim(),
      descripcion: form.descripcion.trim(),
      referencia_externa: form.referencia_externa.trim(),
    });
  };

  const handleEliminar = (b: ListaMateriales) => {
    if (window.confirm(`¿Eliminar la lista de materiales "${b.nombre}"?`)) {
      eliminar.mutate(b.id);
    }
  };

  const columns: Column<ListaMateriales>[] = [
    { key: 'nombre', header: 'Nombre', render: (b) => b.nombre },
    { key: 'producto', header: 'Producto a fabricar', render: (b) => nombreProducto(productos, b.producto_final) },
    { key: 'referencia', header: 'Referencia', render: (b) => b.referencia_externa || '—' },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (b) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(b)}>
            Componentes
          </Button>
          <Button size="small" onClick={() => abrirEditar(b)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(b)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="flex-end">
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva lista de materiales
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={boms}
        getRowKey={(b) => b.id}
        loading={isLoading}
        emptyMessage="Sin listas de materiales. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar lista de materiales' : 'Nueva lista de materiales'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre"
              value={form.nombre}
              onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Producto a fabricar"
              value={form.producto_final}
              onChange={(e) => setForm((f) => ({ ...f, producto_final: e.target.value }))}
              required
              fullWidth
            >
              {productos.map((p) => (
                <MenuItem key={p.id_producto} value={p.id_producto}>
                  {p.nombre_producto}
                  {p.sku ? ` (${p.sku})` : ''}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Referencia externa"
              value={form.referencia_externa}
              onChange={(e) => setForm((f) => ({ ...f, referencia_externa: e.target.value }))}
              helperText="Versión o código de la receta (opcional)."
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
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 640 }, p: 3 } } }}
      >
        {detalle && <ComponentesDrawer bom={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </Stack>
  );
};

interface ComponenteForm {
  id_producto: string;
  cantidad_requerida: string;
  id_unidad_medida: string;
  es_opcional: boolean;
  observaciones: string;
}

const COMP_VACIO: ComponenteForm = {
  id_producto: '',
  cantidad_requerida: '1',
  id_unidad_medida: '',
  es_opcional: false,
  observaciones: '',
};

const ComponentesDrawer: React.FC<{ bom: ListaMateriales; onClose: () => void }> = ({ bom, onClose }) => {
  const queryClient = useQueryClient();
  const bomId = bom.id;
  const [form, setForm] = useState<ComponenteForm>(COMP_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: componentes = [] } = useQuery({
    queryKey: manufacturaMaestrosKeys.componentes(bomId),
    queryFn: () => listasMaterialesDetalleService.getAll({ lista: bomId }),
  });
  const { data: productos = [] } = useProductos();
  const { data: unidades = [] } = useQuery({
    queryKey: ['inv-unidades-medida'],
    queryFn: () => unidadesMedidaService.getAll(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: manufacturaMaestrosKeys.componentes(bomId) });

  const reset = () => {
    setForm(COMP_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: ListaMaterialesDetallePayload) =>
      editId
        ? listasMaterialesDetalleService.update(editId, payload)
        : listasMaterialesDetalleService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el componente.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => listasMaterialesDetalleService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el componente.')),
  });

  const editar = (d: ListaMaterialesDetalle) => {
    setEditId(d.id_detalle_lista);
    setForm({
      id_producto: d.id_producto,
      cantidad_requerida: d.cantidad_requerida,
      id_unidad_medida: d.id_unidad_medida,
      es_opcional: d.es_opcional,
      observaciones: d.observaciones ?? '',
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_producto || !form.cantidad_requerida.trim() || !form.id_unidad_medida) {
      setError('Seleccione un producto, la cantidad y la unidad de medida.');
      return;
    }
    guardar.mutate({
      id_lista_materiales: bomId,
      id_producto: form.id_producto,
      cantidad_requerida: form.cantidad_requerida.trim(),
      id_unidad_medida: form.id_unidad_medida,
      es_opcional: form.es_opcional,
      observaciones: form.observaciones.trim(),
    });
  };

  const nombreUnidad = (id: string) => {
    const u = unidades.find((un) => un.id_unidad_medida === id);
    return u ? u.abreviatura : '';
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{bom.nombre}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Componentes del BOM
      </Typography>
      <Divider />

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack spacing={1}>
        {componentes.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin componentes cargados.
          </Typography>
        ) : (
          componentes.map((d) => (
            <Stack key={d.id_detalle_lista} direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">
                {nombreProducto(productos, d.id_producto)} · {d.cantidad_requerida} {nombreUnidad(d.id_unidad_medida)}
                {d.es_opcional ? ' · opcional' : ''}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_detalle_lista)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>

      <Divider />

      <Stack spacing={1}>
        <TextField
          select
          label="Componente"
          value={form.id_producto}
          onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
          size="small"
          fullWidth
        >
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Cantidad requerida"
            value={form.cantidad_requerida}
            onChange={(e) => setForm((f) => ({ ...f, cantidad_requerida: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
          <TextField
            select
            label="Unidad"
            value={form.id_unidad_medida}
            onChange={(e) => setForm((f) => ({ ...f, id_unidad_medida: e.target.value }))}
            size="small"
            fullWidth
          >
            {unidades.map((u) => (
              <MenuItem key={u.id_unidad_medida} value={u.id_unidad_medida}>
                {u.nombre} ({u.abreviatura})
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <TextField
          label="Observaciones"
          value={form.observaciones}
          onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
          size="small"
          fullWidth
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={form.es_opcional}
              onChange={(e) => setForm((f) => ({ ...f, es_opcional: e.target.checked }))}
            />
          }
          label="Componente opcional"
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar componente' : 'Agregar componente'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Rutas de Producción
// ─────────────────────────────────────────────────────────────────────────────

interface RutaForm {
  nombre: string;
  descripcion: string;
  referencia_externa: string;
}

const RUTA_VACIO: RutaForm = { nombre: '', descripcion: '', referencia_externa: '' };

const RutasProduccionTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<RutaProduccion | null>(null);
  const [form, setForm] = useState<RutaForm>(RUTA_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<RutaProduccion | null>(null);

  const { data: rutas = [], isLoading } = useQuery({
    queryKey: manufacturaMaestrosKeys.rutasAll(),
    queryFn: () => rutasProduccionService.getAll(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: manufacturaMaestrosKeys.rutasAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(RUTA_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (r: RutaProduccion) => {
    setEditando(r);
    setForm({
      nombre: r.nombre,
      descripcion: r.descripcion ?? '',
      referencia_externa: r.referencia_externa ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: RutaProduccionPayload) =>
      editando ? rutasProduccionService.update(editando.id, payload) : rutasProduccionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la ruta de producción.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => rutasProduccionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la ruta de producción.')),
  });

  const handleGuardar = () => {
    if (!form.nombre.trim()) {
      setErrorMsg('Complete el nombre de la ruta.');
      return;
    }
    guardar.mutate({
      nombre: form.nombre.trim(),
      descripcion: form.descripcion.trim(),
      referencia_externa: form.referencia_externa.trim(),
    });
  };

  const handleEliminar = (r: RutaProduccion) => {
    if (window.confirm(`¿Eliminar la ruta "${r.nombre}"?`)) {
      eliminar.mutate(r.id);
    }
  };

  const columns: Column<RutaProduccion>[] = [
    { key: 'nombre', header: 'Nombre', render: (r) => r.nombre },
    { key: 'referencia', header: 'Referencia', render: (r) => r.referencia_externa || '—' },
    { key: 'descripcion', header: 'Descripción', render: (r) => r.descripcion || '—' },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(r)}>
            Pasos
          </Button>
          <Button size="small" onClick={() => abrirEditar(r)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(r)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="flex-end">
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva ruta de producción
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={rutas}
        getRowKey={(r) => r.id}
        loading={isLoading}
        emptyMessage="Sin rutas de producción. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar ruta de producción' : 'Nueva ruta de producción'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre"
              value={form.nombre}
              onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Referencia externa"
              value={form.referencia_externa}
              onChange={(e) => setForm((f) => ({ ...f, referencia_externa: e.target.value }))}
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
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 640 }, p: 3 } } }}
      >
        {detalle && <PasosDrawer ruta={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </Stack>
  );
};

interface PasoForm {
  numero_secuencia: string;
  id_operacion: string;
  id_centro_trabajo: string;
  tiempo_preparacion_minutos: string;
  tiempo_operacion_minutos: string;
  observaciones: string;
}

const PASO_VACIO: PasoForm = {
  numero_secuencia: '1',
  id_operacion: '',
  id_centro_trabajo: '',
  tiempo_preparacion_minutos: '0',
  tiempo_operacion_minutos: '0',
  observaciones: '',
};

const PasosDrawer: React.FC<{ ruta: RutaProduccion; onClose: () => void }> = ({ ruta, onClose }) => {
  const queryClient = useQueryClient();
  const rutaId = ruta.id;
  const [form, setForm] = useState<PasoForm>(PASO_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: pasos = [] } = useQuery({
    queryKey: manufacturaMaestrosKeys.pasos(rutaId),
    queryFn: () => rutasProduccionDetalleService.getAll({ ruta: rutaId }),
  });
  const { data: operaciones = [] } = useQuery({
    queryKey: manufacturaMaestrosKeys.operacionesAll(),
    queryFn: () => operacionesProduccionService.getAll(),
  });
  const { data: centros = [] } = useQuery({
    queryKey: manufacturaMaestrosKeys.centrosAll(),
    queryFn: () => centrosTrabajoService.getAll(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: manufacturaMaestrosKeys.pasos(rutaId) });

  const reset = () => {
    setForm(PASO_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: RutaProduccionDetallePayload) =>
      editId
        ? rutasProduccionDetalleService.update(editId, payload)
        : rutasProduccionDetalleService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el paso.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => rutasProduccionDetalleService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el paso.')),
  });

  const editar = (d: RutaProduccionDetalle) => {
    setEditId(d.id_detalle_ruta);
    setForm({
      numero_secuencia: String(d.numero_secuencia),
      id_operacion: d.id_operacion,
      id_centro_trabajo: d.id_centro_trabajo,
      tiempo_preparacion_minutos: d.tiempo_preparacion_minutos,
      tiempo_operacion_minutos: d.tiempo_operacion_minutos,
      observaciones: d.observaciones ?? '',
    });
    setError('');
  };

  const handleGuardar = () => {
    const secuencia = Number(form.numero_secuencia);
    if (!form.id_operacion || !form.id_centro_trabajo || !Number.isInteger(secuencia) || secuencia <= 0) {
      setError('Indique una secuencia válida, la operación y el centro de trabajo.');
      return;
    }
    guardar.mutate({
      id_ruta_produccion: rutaId,
      id_operacion: form.id_operacion,
      id_centro_trabajo: form.id_centro_trabajo,
      numero_secuencia: secuencia,
      tiempo_preparacion_minutos: form.tiempo_preparacion_minutos.trim() || '0',
      tiempo_operacion_minutos: form.tiempo_operacion_minutos.trim() || '0',
      observaciones: form.observaciones.trim(),
    });
  };

  const nombreOperacion = (id: string) =>
    operaciones.find((o) => o.id_operacion === id)?.nombre_operacion ?? id;
  const nombreCentro = (id: string) =>
    centros.find((c) => c.id_centro_trabajo === id)?.nombre_centro ?? id;

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{ruta.nombre}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Pasos de la ruta (secuencia → operación → centro)
      </Typography>
      <Divider />

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack spacing={1}>
        {pasos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin pasos cargados.
          </Typography>
        ) : (
          pasos.map((d) => (
            <Stack key={d.id_detalle_ruta} direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">
                {d.numero_secuencia}. {nombreOperacion(d.id_operacion)} · {nombreCentro(d.id_centro_trabajo)} ·{' '}
                {d.tiempo_operacion_minutos} min
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_detalle_ruta)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>

      <Divider />

      <Stack spacing={1}>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Secuencia"
            value={form.numero_secuencia}
            onChange={(e) => setForm((f) => ({ ...f, numero_secuencia: e.target.value }))}
            inputMode="numeric"
            size="small"
            sx={{ maxWidth: 120 }}
          />
          <TextField
            select
            label="Operación"
            value={form.id_operacion}
            onChange={(e) => setForm((f) => ({ ...f, id_operacion: e.target.value }))}
            size="small"
            fullWidth
          >
            {operaciones.map((o) => (
              <MenuItem key={o.id_operacion} value={o.id_operacion}>
                {o.nombre_operacion}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <TextField
          select
          label="Centro de trabajo"
          value={form.id_centro_trabajo}
          onChange={(e) => setForm((f) => ({ ...f, id_centro_trabajo: e.target.value }))}
          size="small"
          fullWidth
        >
          {centros.map((c) => (
            <MenuItem key={c.id_centro_trabajo} value={c.id_centro_trabajo}>
              {c.codigo_centro} — {c.nombre_centro}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Preparación (min)"
            value={form.tiempo_preparacion_minutos}
            onChange={(e) => setForm((f) => ({ ...f, tiempo_preparacion_minutos: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
          <TextField
            label="Operación (min)"
            value={form.tiempo_operacion_minutos}
            onChange={(e) => setForm((f) => ({ ...f, tiempo_operacion_minutos: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
        </Stack>
        <TextField
          label="Observaciones"
          value={form.observaciones}
          onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar paso' : 'Agregar paso'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Centros de Trabajo
// ─────────────────────────────────────────────────────────────────────────────

interface CentroForm {
  codigo_centro: string;
  nombre_centro: string;
  descripcion: string;
  tipo_centro: string;
  capacidad_horas_dia: string;
  costo_hora: string;
  activo: boolean;
}

const CENTRO_VACIO: CentroForm = {
  codigo_centro: '',
  nombre_centro: '',
  descripcion: '',
  tipo_centro: 'MAQUINA',
  capacidad_horas_dia: '8',
  costo_hora: '0',
  activo: true,
};

const CentrosTrabajoTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CentroTrabajo | null>(null);
  const [form, setForm] = useState<CentroForm>(CENTRO_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: centros = [], isLoading } = useQuery({
    queryKey: manufacturaMaestrosKeys.centrosAll(),
    queryFn: () => centrosTrabajoService.getAll(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: manufacturaMaestrosKeys.centrosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(CENTRO_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CentroTrabajo) => {
    setEditando(c);
    setForm({
      codigo_centro: c.codigo_centro,
      nombre_centro: c.nombre_centro,
      descripcion: c.descripcion ?? '',
      tipo_centro: c.tipo_centro,
      capacidad_horas_dia: c.capacidad_horas_dia,
      costo_hora: c.costo_hora,
      activo: c.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CentroTrabajoPayload) =>
      editando ? centrosTrabajoService.update(editando.id_centro_trabajo, payload) : centrosTrabajoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el centro de trabajo.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => centrosTrabajoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el centro de trabajo.')),
  });

  const handleGuardar = () => {
    if (!form.codigo_centro.trim() || !form.nombre_centro.trim()) {
      setErrorMsg('Complete el código y el nombre del centro.');
      return;
    }
    guardar.mutate({
      codigo_centro: form.codigo_centro.trim(),
      nombre_centro: form.nombre_centro.trim(),
      descripcion: form.descripcion.trim(),
      tipo_centro: form.tipo_centro,
      capacidad_horas_dia: form.capacidad_horas_dia.trim() || '0',
      costo_hora: form.costo_hora.trim() || '0',
      activo: form.activo,
    });
  };

  const handleEliminar = (c: CentroTrabajo) => {
    if (window.confirm(`¿Eliminar el centro de trabajo "${c.nombre_centro}"?`)) {
      eliminar.mutate(c.id_centro_trabajo);
    }
  };

  const columns: Column<CentroTrabajo>[] = [
    { key: 'codigo', header: 'Código', render: (c) => c.codigo_centro },
    { key: 'nombre', header: 'Nombre', render: (c) => c.nombre_centro },
    { key: 'tipo', header: 'Tipo', render: (c) => c.tipo_centro },
    { key: 'costo', header: 'Costo/hora', render: (c) => c.costo_hora },
    { key: 'activo', header: 'Activo', render: (c) => <StatusChip value={c.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(c)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(c)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="flex-end">
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nuevo centro de trabajo
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={centros}
        getRowKey={(c) => c.id_centro_trabajo}
        loading={isLoading}
        emptyMessage="Sin centros de trabajo. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar centro de trabajo' : 'Nuevo centro de trabajo'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Código"
                value={form.codigo_centro}
                onChange={(e) => setForm((f) => ({ ...f, codigo_centro: e.target.value }))}
                required
                fullWidth
              />
              <TextField
                select
                label="Tipo"
                value={form.tipo_centro}
                onChange={(e) => setForm((f) => ({ ...f, tipo_centro: e.target.value }))}
                fullWidth
              >
                {TIPO_CENTRO_OPCIONES.map((t) => (
                  <MenuItem key={t} value={t}>
                    {t}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              label="Nombre"
              value={form.nombre_centro}
              onChange={(e) => setForm((f) => ({ ...f, nombre_centro: e.target.value }))}
              required
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Capacidad (h/día)"
                value={form.capacidad_horas_dia}
                onChange={(e) => setForm((f) => ({ ...f, capacidad_horas_dia: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Costo/hora"
                value={form.costo_hora}
                onChange={(e) => setForm((f) => ({ ...f, costo_hora: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            </Stack>
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
    </Stack>
  );
};

export default DatosMaestrosPage;
