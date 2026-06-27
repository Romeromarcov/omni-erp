import React, { useRef, useState } from 'react';
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
  listasPrecioService,
  detallesPrecioService,
  type ListaPrecio,
  type ListaPrecioPayload,
  type DetallePrecio,
  type DetallePrecioPayload,
  type ImportarMasivoResultado,
} from '../../services/listasPrecioService';
import { productoInventarioService, type Producto } from '../../services/inventarioService';
import { fetchMonedas } from '../../services/monedas';
import { listasPrecioKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

interface FormState {
  nombre: string;
  codigo: string;
  id_moneda: string;
  es_referencia: boolean;
  activo: boolean;
}

const FORM_VACIO: FormState = {
  nombre: '',
  codigo: '',
  id_moneda: '',
  es_referencia: false,
  activo: true,
};

const ListasPrecioPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [busqueda, setBusqueda] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ListaPrecio | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalleLista, setDetalleLista] = useState<ListaPrecio | null>(null);

  const { data: listas = [], isLoading } = useQuery({
    queryKey: listasPrecioKeys.list(busqueda),
    queryFn: () => listasPrecioService.getAll({ search: busqueda.trim() || undefined }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: ['finanzas', 'monedas', 'list-full'],
    queryFn: fetchMonedas,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: listasPrecioKeys.all() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (l: ListaPrecio) => {
    setEditando(l);
    setForm({
      nombre: l.nombre,
      codigo: l.codigo,
      id_moneda: l.id_moneda,
      es_referencia: l.es_referencia,
      activo: l.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ListaPrecioPayload) =>
      editando
        ? listasPrecioService.update(editando.id_lista, payload)
        : listasPrecioService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la lista de precios.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => listasPrecioService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la lista de precios.')),
  });

  const handleGuardar = () => {
    if (!form.nombre.trim() || !form.codigo.trim() || !form.id_moneda) {
      setErrorMsg('Complete el nombre, el código y la moneda.');
      return;
    }
    const payload: ListaPrecioPayload = {
      nombre: form.nombre.trim(),
      codigo: form.codigo.trim(),
      id_moneda: form.id_moneda,
      es_referencia: form.es_referencia,
      activo: form.activo,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (l: ListaPrecio) => {
    if (window.confirm(`¿Eliminar la lista de precios "${l.nombre}"?`)) {
      eliminar.mutate(l.id_lista);
    }
  };

  const columns: Column<ListaPrecio>[] = [
    { key: 'codigo', header: 'Código', render: (l) => l.codigo },
    { key: 'nombre', header: 'Nombre', render: (l) => l.nombre },
    {
      key: 'referencia',
      header: 'Referencia',
      render: (l) => (l.es_referencia ? <StatusChip value="Lista 1" label="Lista 1" /> : '—'),
    },
    { key: 'activo', header: 'Activa', render: (l) => <StatusChip value={l.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (l) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalleLista(l)}>
            Precios
          </Button>
          <Button size="small" onClick={() => abrirEditar(l)}>
            Editar
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
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Listas de Precio"
        subtitle="Listas de precio de ventas: cabecera por moneda y precios por producto con vigencias."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nueva lista
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <TextField
        label="Buscar"
        placeholder="Nombre o código…"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        size="small"
        sx={{ mb: 2, maxWidth: 360 }}
        fullWidth
      />

      <DataTable
        columns={columns}
        rows={listas}
        getRowKey={(l) => l.id_lista}
        loading={isLoading}
        emptyMessage="Sin listas de precio. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar lista de precios' : 'Nueva lista de precios'}</DialogTitle>
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
              label="Código"
              value={form.codigo}
              onChange={(e) => setForm((f) => ({ ...f, codigo: e.target.value }))}
              required
              helperText="Código corto, p. ej. LISTA1, MAYOREO."
              fullWidth
            />
            <TextField
              select
              label="Moneda"
              value={form.id_moneda}
              onChange={(e) => setForm((f) => ({ ...f, id_moneda: e.target.value }))}
              required
              fullWidth
            >
              {monedas.map((m) => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>
                  {m.codigo_iso} — {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.es_referencia}
                  onChange={(e) => setForm((f) => ({ ...f, es_referencia: e.target.checked }))}
                />
              }
              label="Lista de referencia (Lista 1)"
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

      <Drawer
        anchor="right"
        open={Boolean(detalleLista)}
        onClose={() => setDetalleLista(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 640 }, p: 3 } } }}
      >
        {detalleLista && (
          <DetalleListaPrecio
            lista={detalleLista}
            empresaId={empresaId}
            onClose={() => setDetalleLista(null)}
          />
        )}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle de la lista: precios por producto (CRUD inline) + importar CSV ─────

interface DetalleListaPrecioProps {
  lista: ListaPrecio;
  empresaId: string;
  onClose: () => void;
}

interface DetalleForm {
  id_producto: string;
  precio: string;
  precio_minimo: string;
  vigente_desde: string;
  vigente_hasta: string;
  activo: boolean;
}

const DETALLE_VACIO: DetalleForm = {
  id_producto: '',
  precio: '0',
  precio_minimo: '0',
  vigente_desde: '',
  vigente_hasta: '',
  activo: true,
};

const DetalleListaPrecio: React.FC<DetalleListaPrecioProps> = ({ lista, empresaId, onClose }) => {
  const queryClient = useQueryClient();
  const listaId = lista.id_lista;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<DetalleForm>(DETALLE_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [importResultado, setImportResultado] = useState<ImportarMasivoResultado | null>(null);

  const { data: detalles = [] } = useQuery({
    queryKey: listasPrecioKeys.detalles(listaId),
    queryFn: () => detallesPrecioService.getAll({ lista: listaId }),
  });

  const { data: productos = [] } = useQuery({
    queryKey: ['productos', empresaId],
    queryFn: () => productoInventarioService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });

  const nombreProducto = (id: string) => {
    const p = productos.find((prod: Producto) => prod.id_producto === id);
    return p ? `${p.nombre_producto}${p.sku ? ` (${p.sku})` : ''}` : id;
  };

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: listasPrecioKeys.detalles(listaId) });

  const reset = () => {
    setForm(DETALLE_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: DetallePrecioPayload) =>
      editId
        ? detallesPrecioService.update(editId, payload)
        : detallesPrecioService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el precio.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => detallesPrecioService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el precio.')),
  });

  const importar = useMutation({
    mutationFn: (file: File) => listasPrecioService.importarMasivo(listaId, file),
    onSuccess: (res) => {
      setImportResultado(res);
      setError('');
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo importar el archivo CSV.')),
  });

  const editar = (d: DetallePrecio) => {
    setEditId(d.id_detalle);
    setForm({
      id_producto: d.id_producto,
      precio: d.precio,
      precio_minimo: d.precio_minimo,
      vigente_desde: d.vigente_desde ?? '',
      vigente_hasta: d.vigente_hasta ?? '',
      activo: d.activo,
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_producto || !form.precio.trim()) {
      setError('Seleccione un producto e indique el precio.');
      return;
    }
    guardar.mutate({
      id_lista: listaId,
      id_producto: form.id_producto,
      precio: form.precio.trim(),
      precio_minimo: form.precio_minimo.trim() || '0',
      vigente_desde: form.vigente_desde || null,
      vigente_hasta: form.vigente_hasta || null,
      activo: form.activo,
    });
  };

  const handleArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportResultado(null);
      importar.mutate(file);
    }
    // Permite re-seleccionar el mismo archivo dos veces seguidas.
    e.target.value = '';
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{lista.nombre}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {lista.codigo}
        {lista.es_referencia ? ' · Lista 1 (referencia)' : ''}
      </Typography>

      <Divider />

      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">Precios por producto</Typography>
        <Button
          size="small"
          startIcon={<UploadFileOutlined />}
          onClick={() => fileInputRef.current?.click()}
          disabled={importar.isPending}
        >
          Importar CSV
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          aria-label="Importar CSV"
          style={{ display: 'none' }}
          onChange={handleArchivo}
        />
      </Stack>

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {importResultado && (
        <Alert
          severity={importResultado.total_errores > 0 ? 'warning' : 'success'}
          onClose={() => setImportResultado(null)}
        >
          Importación: {importResultado.creados} creados, {importResultado.actualizados}{' '}
          actualizados, {importResultado.total_errores} con error.
          {importResultado.errores.slice(0, 5).map((er) => (
            <Box key={er.fila} component="div" sx={{ fontSize: 12 }}>
              Fila {er.fila}: {er.error}
            </Box>
          ))}
        </Alert>
      )}

      <Stack spacing={1}>
        {detalles.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin precios cargados.
          </Typography>
        ) : (
          detalles.map((d) => (
            <Stack
              key={d.id_detalle}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {nombreProducto(d.id_producto)} · {d.precio}
                {Number(d.precio_minimo) > 0 ? ` · mín. ${d.precio_minimo}` : ''}
                {d.activo ? '' : ' · Inactivo'}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_detalle)}
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
          label="Producto"
          value={form.id_producto}
          onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
          size="small"
          fullWidth
        >
          {productos.map((p: Producto) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Precio"
            value={form.precio}
            onChange={(e) => setForm((f) => ({ ...f, precio: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
          <TextField
            label="Precio mínimo"
            value={form.precio_minimo}
            onChange={(e) => setForm((f) => ({ ...f, precio_minimo: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
        </Stack>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Vigente desde"
            type="date"
            value={form.vigente_desde}
            onChange={(e) => setForm((f) => ({ ...f, vigente_desde: e.target.value }))}
            size="small"
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="Vigente hasta"
            type="date"
            value={form.vigente_hasta}
            onChange={(e) => setForm((f) => ({ ...f, vigente_hasta: e.target.value }))}
            size="small"
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
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
        <Stack direction="row" spacing={1}>
          <Button
            variant="contained"
            size="small"
            onClick={handleGuardar}
            disabled={guardar.isPending}
          >
            {editId ? 'Actualizar precio' : 'Agregar precio'}
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

export default ListasPrecioPage;
