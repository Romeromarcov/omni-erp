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
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  productoInventarioService,
  categoriasProductoService,
  unidadesMedidaService,
  type Producto,
  type ProductoPayload,
  type MetodoValoracion,
} from '../../services/inventarioService';
import { fetchMonedas } from '../../services/monedas';
import { inventarioKeys, finanzasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS_PRODUCTO: { value: string; label: string }[] = [
  { value: 'PRODUCTO_FISICO', label: 'Producto Físico' },
  { value: 'SERVICIO', label: 'Servicio' },
  { value: 'KIT', label: 'Kit' },
  { value: 'COMBO', label: 'Combo' },
];

const METODOS_VALORACION: { value: MetodoValoracion; label: string }[] = [
  { value: 'PROMEDIO', label: 'Costo Promedio' },
  { value: 'FIFO', label: 'FIFO' },
];

interface FormState {
  nombre_producto: string;
  sku: string;
  id_categoria: string;
  id_unidad_medida_base: string;
  tipo_producto: string;
  maneja_lotes: boolean;
  maneja_seriales: boolean;
  costo_promedio: string;
  precio_venta_sugerido: string;
  punto_reorden: string;
  metodo_valoracion: MetodoValoracion;
  id_moneda_precio: string;
}

const FORM_VACIO: FormState = {
  nombre_producto: '',
  sku: '',
  id_categoria: '',
  id_unidad_medida_base: '',
  tipo_producto: 'PRODUCTO_FISICO',
  maneja_lotes: false,
  maneja_seriales: false,
  costo_promedio: '0',
  precio_venta_sugerido: '0',
  punto_reorden: '',
  metodo_valoracion: 'PROMEDIO',
  id_moneda_precio: '',
};

const ProductosPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<Producto | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: productos = [], isLoading } = useQuery({
    queryKey: inventarioKeys.productosInventario(),
    queryFn: () => productoInventarioService.getAll(),
  });
  const { data: categorias = [] } = useQuery({
    queryKey: inventarioKeys.categoriasProducto(),
    queryFn: () => categoriasProductoService.getAll(),
  });
  const { data: unidades = [] } = useQuery({
    queryKey: inventarioKeys.unidadesMedida(),
    queryFn: () => unidadesMedidaService.getAll(),
  });
  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: () => fetchMonedas(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: inventarioKeys.productosInventario() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (p: Producto) => {
    setEditando(p);
    setForm({
      nombre_producto: p.nombre_producto,
      sku: p.sku ?? '',
      id_categoria: p.id_categoria,
      id_unidad_medida_base: p.id_unidad_medida_base,
      tipo_producto: p.tipo_producto,
      maneja_lotes: p.maneja_lotes,
      maneja_seriales: p.maneja_seriales,
      costo_promedio: p.costo_promedio,
      precio_venta_sugerido: p.precio_venta_sugerido,
      punto_reorden: p.punto_reorden ?? '',
      metodo_valoracion: p.metodo_valoracion,
      id_moneda_precio: p.id_moneda_precio,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ProductoPayload) =>
      editando
        ? productoInventarioService.update(editando.id_producto, payload)
        : productoInventarioService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el producto.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => productoInventarioService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el producto.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_producto.trim() || !form.id_categoria || !form.id_unidad_medida_base || !form.id_moneda_precio) {
      setErrorMsg('Complete nombre, categoría, unidad de medida y moneda.');
      return;
    }
    const payload: ProductoPayload = {
      id_empresa: empresaId,
      nombre_producto: form.nombre_producto.trim(),
      sku: form.sku.trim() || null,
      id_categoria: form.id_categoria,
      id_unidad_medida_base: form.id_unidad_medida_base,
      tipo_producto: form.tipo_producto,
      maneja_lotes: form.maneja_lotes,
      maneja_seriales: form.maneja_seriales,
      costo_promedio: form.costo_promedio || '0',
      precio_venta_sugerido: form.precio_venta_sugerido || '0',
      punto_reorden: form.punto_reorden.trim() || null,
      metodo_valoracion: form.metodo_valoracion,
      id_moneda_precio: form.id_moneda_precio,
    };
    guardar.mutate(payload);
  };

  const columns: Column<Producto>[] = [
    { key: 'nombre', header: 'Nombre', render: (p) => p.nombre_producto },
    { key: 'sku', header: 'SKU', render: (p) => p.sku || '—' },
    { key: 'categoria', header: 'Categoría', render: (p) => p.nombre_categoria || '—' },
    { key: 'tipo', header: 'Tipo', render: (p) => p.tipo_producto },
    { key: 'metodo', header: 'Valoración', render: (p) => p.metodo_valoracion },
    { key: 'precio', header: 'Precio venta', align: 'right', render: (p) => p.precio_venta_sugerido },
    { key: 'activo', header: 'Activo', render: (p) => <StatusChip value={p.activo} /> },
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
            onClick={() => eliminar.mutate(p.id_producto)}
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
        title="Productos"
        subtitle="Catálogo de productos: costos, precios, valoración y manejo de lotes/seriales."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo producto
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={productos}
        getRowKey={(p) => p.id_producto}
        loading={isLoading}
        emptyMessage="Sin productos. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar producto' : 'Nuevo producto'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre"
              value={form.nombre_producto}
              onChange={(e) => setForm((f) => ({ ...f, nombre_producto: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="SKU"
              value={form.sku}
              onChange={(e) => setForm((f) => ({ ...f, sku: e.target.value }))}
              fullWidth
            />
            <TextField
              select
              label="Categoría"
              value={form.id_categoria}
              onChange={(e) => setForm((f) => ({ ...f, id_categoria: e.target.value }))}
              required
              fullWidth
            >
              {categorias.map((c) => (
                <MenuItem key={c.id_categoria_producto} value={c.id_categoria_producto}>
                  {c.nombre_categoria}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Unidad de medida"
              value={form.id_unidad_medida_base}
              onChange={(e) => setForm((f) => ({ ...f, id_unidad_medida_base: e.target.value }))}
              required
              fullWidth
            >
              {unidades.map((u) => (
                <MenuItem key={u.id_unidad_medida} value={u.id_unidad_medida}>
                  {u.nombre} ({u.abreviatura})
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Tipo de producto"
              value={form.tipo_producto}
              onChange={(e) => setForm((f) => ({ ...f, tipo_producto: e.target.value }))}
              fullWidth
            >
              {TIPOS_PRODUCTO.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Método de valoración"
              value={form.metodo_valoracion}
              onChange={(e) =>
                setForm((f) => ({ ...f, metodo_valoracion: e.target.value as MetodoValoracion }))
              }
              fullWidth
            >
              {METODOS_VALORACION.map((m) => (
                <MenuItem key={m.value} value={m.value}>
                  {m.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Moneda del precio"
              value={form.id_moneda_precio}
              onChange={(e) => setForm((f) => ({ ...f, id_moneda_precio: e.target.value }))}
              required
              fullWidth
            >
              {monedas.map((m) => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>
                  {m.codigo_iso} — {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Costo promedio"
              value={form.costo_promedio}
              onChange={(e) => setForm((f) => ({ ...f, costo_promedio: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
            <TextField
              label="Precio de venta sugerido"
              value={form.precio_venta_sugerido}
              onChange={(e) => setForm((f) => ({ ...f, precio_venta_sugerido: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
            <TextField
              label="Punto de reorden"
              value={form.punto_reorden}
              onChange={(e) => setForm((f) => ({ ...f, punto_reorden: e.target.value }))}
              inputMode="decimal"
              helperText="Stock mínimo para alertas. Vacío = sin alerta."
              fullWidth
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.maneja_lotes}
                  onChange={(e) => setForm((f) => ({ ...f, maneja_lotes: e.target.checked }))}
                />
              }
              label="Maneja lotes"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.maneja_seriales}
                  onChange={(e) => setForm((f) => ({ ...f, maneja_seriales: e.target.checked }))}
                />
              }
              label="Maneja seriales"
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
    </PageContainer>
  );
};

export default ProductosPage;
