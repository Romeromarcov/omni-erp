import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Checkbox,
  Chip,
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
import PlayArrowOutlined from '@mui/icons-material/PlayArrowOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  variantesProductoService,
  conversionesUnidadService,
  stockConsignacionClienteService,
  stockConsignacionProveedorService,
  reglasReabastecimientoService,
  lotesProductoService,
  type VarianteProducto,
  type VarianteProductoPayload,
  type ConversionUnidad,
  type ConversionUnidadPayload,
  type StockConsignacionCliente,
  type StockConsignacionClientePayload,
  type StockConsignacionProveedor,
  type StockConsignacionProveedorPayload,
  type EstadoConsignacion,
  type ReglaReabastecimiento,
  type ReglaReabastecimientoPayload,
  type EvaluacionReabastecimientoItem,
  type RutaReabastecimiento,
  type LoteProducto,
} from '../../services/inventarioMaestrosService';
import { almacenesService, type Almacen } from '../../services/almacenesService';
import {
  productoInventarioService,
  unidadesMedidaService,
  type Producto,
} from '../../services/inventarioService';
import { clientesService } from '../../services/clientesService';
import { proveedoresService } from '../../services/proveedoresService';
import { fetchMonedas } from '../../services/monedas';
import { inventarioMaestrosKeys, finanzasKeys, almacenesKeys } from '../../lib/queryKeys';
import { D } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const ESTADOS: EstadoConsignacion[] = ['ACTIVA', 'VENCIDA', 'CERRADA', 'CANCELADA'];

// Catálogos compartidos por las pestañas.
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

const InventarioMaestrosPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  return (
    <PageContainer>
      <PageHeader
        title="Datos Maestros de Inventario"
        subtitle="Variantes de producto, conversiones entre unidades de medida y saldos de mercancía en consignación (a clientes y de proveedores)."
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable" scrollButtons="auto">
        <Tab label="Variantes" />
        <Tab label="Conversiones UM" />
        <Tab label="Consignación Cliente" />
        <Tab label="Consignación Proveedor" />
        <Tab label="Reabastecimiento" />
        <Tab label="Lotes" />
      </Tabs>
      {tab === 0 && <VariantesTab />}
      {tab === 1 && <ConversionesTab />}
      {tab === 2 && <ConsignacionClienteTab />}
      {tab === 3 && <ConsignacionProveedorTab />}
      {tab === 4 && <ReabastecimientoTab />}
      {tab === 5 && <LotesTab />}
    </PageContainer>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Variantes de Producto
// ─────────────────────────────────────────────────────────────────────────────

interface VarianteForm {
  id_producto: string;
  codigo_variante: string;
  sku: string;
  atributos_json: string;
}

const VARIANTE_VACIO: VarianteForm = { id_producto: '', codigo_variante: '', sku: '', atributos_json: '{}' };

const VariantesTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [filtroProducto, setFiltroProducto] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<VarianteProducto | null>(null);
  const [form, setForm] = useState<VarianteForm>(VARIANTE_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: variantes = [], isLoading } = useQuery({
    queryKey: inventarioMaestrosKeys.variantes(filtroProducto || null),
    queryFn: () => variantesProductoService.getAll(filtroProducto ? { producto: filtroProducto } : undefined),
  });
  const { data: productos = [] } = useProductos();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: inventarioMaestrosKeys.variantesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...VARIANTE_VACIO, id_producto: filtroProducto });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (v: VarianteProducto) => {
    setEditando(v);
    setForm({
      id_producto: v.id_producto,
      codigo_variante: v.codigo_variante ?? '',
      sku: v.sku ?? '',
      atributos_json: JSON.stringify(v.atributos_json ?? {}),
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: VarianteProductoPayload) =>
      editando
        ? variantesProductoService.update(editando.id_variante, payload)
        : variantesProductoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la variante.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => variantesProductoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la variante.')),
  });

  const handleGuardar = () => {
    if (!form.id_producto) {
      setErrorMsg('Seleccione el producto base.');
      return;
    }
    let atributos: Record<string, unknown>;
    try {
      atributos = form.atributos_json.trim() ? JSON.parse(form.atributos_json) : {};
    } catch {
      setErrorMsg('Los atributos deben ser un JSON válido (p. ej. {"talla":"M"}).');
      return;
    }
    guardar.mutate({
      id_producto: form.id_producto,
      codigo_variante: form.codigo_variante.trim() || null,
      sku: form.sku.trim() || null,
      atributos_json: atributos,
    });
  };

  const handleEliminar = (v: VarianteProducto) => {
    if (window.confirm(`¿Eliminar la variante "${v.codigo_variante || v.sku || v.id_variante}"?`)) {
      eliminar.mutate(v.id_variante);
    }
  };

  const columns: Column<VarianteProducto>[] = [
    { key: 'producto', header: 'Producto base', render: (v) => nombreProducto(productos, v.id_producto) },
    { key: 'codigo', header: 'Código', render: (v) => v.codigo_variante || '—' },
    { key: 'sku', header: 'SKU', render: (v) => v.sku || '—' },
    {
      key: 'atributos',
      header: 'Atributos',
      render: (v) => {
        const txt = JSON.stringify(v.atributos_json ?? {});
        return txt === '{}' ? '—' : txt;
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (v) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(v)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(v)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
        <TextField
          select
          label="Filtrar por producto"
          value={filtroProducto}
          onChange={(e) => setFiltroProducto(e.target.value)}
          size="small"
          sx={{ minWidth: 280 }}
        >
          <MenuItem value="">Todos los productos</MenuItem>
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva variante
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={variantes}
        getRowKey={(v) => v.id_variante}
        loading={isLoading}
        emptyMessage="Sin variantes. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar variante' : 'Nueva variante'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Producto base"
              value={form.id_producto}
              onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
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
            <Stack direction="row" spacing={1}>
              <TextField
                label="Código variante"
                value={form.codigo_variante}
                onChange={(e) => setForm((f) => ({ ...f, codigo_variante: e.target.value }))}
                fullWidth
              />
              <TextField
                label="SKU"
                value={form.sku}
                onChange={(e) => setForm((f) => ({ ...f, sku: e.target.value }))}
                fullWidth
              />
            </Stack>
            <TextField
              label="Atributos (JSON)"
              value={form.atributos_json}
              onChange={(e) => setForm((f) => ({ ...f, atributos_json: e.target.value }))}
              helperText='Objeto JSON, p. ej. {"talla":"M","color":"azul"}.'
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
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Conversiones de Unidad de Medida
// ─────────────────────────────────────────────────────────────────────────────

interface ConversionForm {
  id_producto: string;
  id_unidad_origen: string;
  id_unidad_destino: string;
  factor_conversion: string;
}

const CONVERSION_VACIO: ConversionForm = {
  id_producto: '',
  id_unidad_origen: '',
  id_unidad_destino: '',
  factor_conversion: '1',
};

const ConversionesTab: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroProducto, setFiltroProducto] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ConversionUnidad | null>(null);
  const [form, setForm] = useState<ConversionForm>(CONVERSION_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: conversiones = [], isLoading } = useQuery({
    queryKey: inventarioMaestrosKeys.conversiones(filtroProducto || null),
    queryFn: () =>
      conversionesUnidadService.getAll(filtroProducto ? { producto: filtroProducto } : undefined),
  });
  const { data: productos = [] } = useProductos();
  const { data: unidades = [] } = useQuery({
    queryKey: ['inv-unidades-medida'],
    queryFn: () => unidadesMedidaService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: inventarioMaestrosKeys.conversionesAll() });

  const nombreUnidad = (id: string) => {
    const u = unidades.find((un) => un.id_unidad_medida === id);
    return u ? `${u.nombre} (${u.abreviatura})` : id;
  };

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...CONVERSION_VACIO, id_producto: filtroProducto });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: ConversionUnidad) => {
    setEditando(c);
    setForm({
      id_producto: c.id_producto,
      id_unidad_origen: c.id_unidad_origen,
      id_unidad_destino: c.id_unidad_destino,
      factor_conversion: c.factor_conversion,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ConversionUnidadPayload) =>
      editando
        ? conversionesUnidadService.update(editando.id_conversion, payload)
        : conversionesUnidadService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la conversión.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => conversionesUnidadService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la conversión.')),
  });

  const handleGuardar = () => {
    if (!form.id_producto || !form.id_unidad_origen || !form.id_unidad_destino || !form.factor_conversion.trim()) {
      setErrorMsg('Complete el producto, ambas unidades y el factor.');
      return;
    }
    if (form.id_unidad_origen === form.id_unidad_destino) {
      setErrorMsg('La unidad de origen y la de destino deben ser distintas.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_producto: form.id_producto,
      id_unidad_origen: form.id_unidad_origen,
      id_unidad_destino: form.id_unidad_destino,
      factor_conversion: form.factor_conversion.trim(),
    });
  };

  const handleEliminar = (c: ConversionUnidad) => {
    if (window.confirm('¿Eliminar esta conversión de unidad?')) {
      eliminar.mutate(c.id_conversion);
    }
  };

  const columns: Column<ConversionUnidad>[] = [
    { key: 'producto', header: 'Producto', render: (c) => nombreProducto(productos, c.id_producto) },
    { key: 'origen', header: 'Unidad origen', render: (c) => nombreUnidad(c.id_unidad_origen) },
    { key: 'destino', header: 'Unidad destino', render: (c) => nombreUnidad(c.id_unidad_destino) },
    { key: 'factor', header: 'Factor', render: (c) => c.factor_conversion },
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
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
        <TextField
          select
          label="Filtrar por producto"
          value={filtroProducto}
          onChange={(e) => setFiltroProducto(e.target.value)}
          size="small"
          sx={{ minWidth: 280 }}
        >
          <MenuItem value="">Todos los productos</MenuItem>
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva conversión
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={conversiones}
        getRowKey={(c) => c.id_conversion}
        loading={isLoading}
        emptyMessage="Sin conversiones. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar conversión' : 'Nueva conversión'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Producto"
              value={form.id_producto}
              onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
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
            <Stack direction="row" spacing={1}>
              <TextField
                select
                label="Unidad origen"
                value={form.id_unidad_origen}
                onChange={(e) => setForm((f) => ({ ...f, id_unidad_origen: e.target.value }))}
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
                label="Unidad destino"
                value={form.id_unidad_destino}
                onChange={(e) => setForm((f) => ({ ...f, id_unidad_destino: e.target.value }))}
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
              label="Factor de conversión"
              value={form.factor_conversion}
              onChange={(e) => setForm((f) => ({ ...f, factor_conversion: e.target.value }))}
              inputMode="decimal"
              helperText="Cuántas unidades destino equivalen a 1 unidad origen."
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
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Consignación a Cliente
// ─────────────────────────────────────────────────────────────────────────────

interface ConsignacionClienteForm {
  id_cliente: string;
  id_producto: string;
  cantidad_consignada: string;
  cantidad_vendida: string;
  cantidad_devuelta: string;
  fecha_consignacion: string;
  fecha_vencimiento: string;
  precio_unitario_consignacion: string;
  id_moneda: string;
  estado: EstadoConsignacion;
}

const CONS_CLIENTE_VACIO: ConsignacionClienteForm = {
  id_cliente: '',
  id_producto: '',
  cantidad_consignada: '0',
  cantidad_vendida: '0',
  cantidad_devuelta: '0',
  fecha_consignacion: '',
  fecha_vencimiento: '',
  precio_unitario_consignacion: '0',
  id_moneda: '',
  estado: 'ACTIVA',
};

const ConsignacionClienteTab: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroCliente, setFiltroCliente] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<StockConsignacionCliente | null>(null);
  const [form, setForm] = useState<ConsignacionClienteForm>(CONS_CLIENTE_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: items = [], isLoading } = useQuery({
    queryKey: inventarioMaestrosKeys.consignacionCliente(filtroCliente || null, filtroEstado || null),
    queryFn: () =>
      stockConsignacionClienteService.getAll({
        cliente: filtroCliente || undefined,
        estado: filtroEstado || undefined,
      }),
  });
  const { data: productos = [] } = useProductos();
  const { data: clientes = [] } = useQuery({
    queryKey: ['crm', 'clientes', empresaId],
    queryFn: () => clientesService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });
  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.listFull(),
    queryFn: fetchMonedas,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: inventarioMaestrosKeys.consignacionClienteAll() });

  const nombreCliente = (id: string) =>
    clientes.find((c) => c.id_cliente === id)?.razon_social ?? id;

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...CONS_CLIENTE_VACIO, id_cliente: filtroCliente });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (s: StockConsignacionCliente) => {
    setEditando(s);
    setForm({
      id_cliente: s.id_cliente,
      id_producto: s.id_producto,
      cantidad_consignada: s.cantidad_consignada,
      cantidad_vendida: s.cantidad_vendida,
      cantidad_devuelta: s.cantidad_devuelta,
      fecha_consignacion: s.fecha_consignacion ?? '',
      fecha_vencimiento: s.fecha_vencimiento ?? '',
      precio_unitario_consignacion: s.precio_unitario_consignacion,
      id_moneda: s.id_moneda,
      estado: s.estado,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: StockConsignacionClientePayload) =>
      editando
        ? stockConsignacionClienteService.update(editando.id_stock_consignacion, payload)
        : stockConsignacionClienteService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la consignación.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => stockConsignacionClienteService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la consignación.')),
  });

  const handleGuardar = () => {
    if (!form.id_cliente || !form.id_producto || !form.id_moneda || !form.fecha_consignacion) {
      setErrorMsg('Complete cliente, producto, moneda y fecha de consignación.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_cliente: form.id_cliente,
      id_producto: form.id_producto,
      id_variante: null,
      cantidad_consignada: form.cantidad_consignada.trim() || '0',
      cantidad_vendida: form.cantidad_vendida.trim() || '0',
      cantidad_devuelta: form.cantidad_devuelta.trim() || '0',
      fecha_consignacion: form.fecha_consignacion,
      fecha_vencimiento: form.fecha_vencimiento || null,
      precio_unitario_consignacion: form.precio_unitario_consignacion.trim() || '0',
      id_moneda: form.id_moneda,
      estado: form.estado,
    });
  };

  const handleEliminar = (s: StockConsignacionCliente) => {
    if (window.confirm('¿Eliminar este saldo en consignación?')) {
      eliminar.mutate(s.id_stock_consignacion);
    }
  };

  const columns: Column<StockConsignacionCliente>[] = [
    { key: 'cliente', header: 'Cliente', render: (s) => nombreCliente(s.id_cliente) },
    { key: 'producto', header: 'Producto', render: (s) => nombreProducto(productos, s.id_producto) },
    { key: 'consignada', header: 'Consignada', render: (s) => s.cantidad_consignada },
    { key: 'vendida', header: 'Vendida', render: (s) => s.cantidad_vendida },
    { key: 'estado', header: 'Estado', render: (s) => <StatusChip value={s.estado} label={s.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (s) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(s)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(s)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} flexWrap="wrap">
        <Stack direction="row" spacing={1}>
          <TextField
            select
            label="Filtrar por cliente"
            value={filtroCliente}
            onChange={(e) => setFiltroCliente(e.target.value)}
            size="small"
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">Todos los clientes</MenuItem>
            {clientes.map((c) => (
              <MenuItem key={c.id_cliente} value={c.id_cliente}>
                {c.razon_social}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Estado"
            value={filtroEstado}
            onChange={(e) => setFiltroEstado(e.target.value)}
            size="small"
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">Todos</MenuItem>
            {ESTADOS.map((es) => (
              <MenuItem key={es} value={es}>
                {es}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva consignación
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(s) => s.id_stock_consignacion}
        loading={isLoading}
        emptyMessage="Sin consignaciones a clientes."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar consignación a cliente' : 'Nueva consignación a cliente'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Cliente"
              value={form.id_cliente}
              onChange={(e) => setForm((f) => ({ ...f, id_cliente: e.target.value }))}
              required
              fullWidth
            >
              {clientes.map((c) => (
                <MenuItem key={c.id_cliente} value={c.id_cliente}>
                  {c.razon_social}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Producto"
              value={form.id_producto}
              onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
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
            <Stack direction="row" spacing={1}>
              <TextField
                label="Cantidad consignada"
                value={form.cantidad_consignada}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_consignada: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Cantidad vendida"
                value={form.cantidad_vendida}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_vendida: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Cantidad devuelta"
                value={form.cantidad_devuelta}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_devuelta: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha consignación"
                type="date"
                value={form.fecha_consignacion}
                onChange={(e) => setForm((f) => ({ ...f, fecha_consignacion: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Fecha vencimiento"
                type="date"
                value={form.fecha_vencimiento}
                onChange={(e) => setForm((f) => ({ ...f, fecha_vencimiento: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Precio unitario"
                value={form.precio_unitario_consignacion}
                onChange={(e) => setForm((f) => ({ ...f, precio_unitario_consignacion: e.target.value }))}
                inputMode="decimal"
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
            </Stack>
            <TextField
              select
              label="Estado"
              value={form.estado}
              onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value as EstadoConsignacion }))}
              fullWidth
            >
              {ESTADOS.map((es) => (
                <MenuItem key={es} value={es}>
                  {es}
                </MenuItem>
              ))}
            </TextField>
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

// ─────────────────────────────────────────────────────────────────────────────
// Consignación de Proveedor
// ─────────────────────────────────────────────────────────────────────────────

interface ConsignacionProveedorForm {
  id_proveedor: string;
  id_producto: string;
  cantidad_recibida: string;
  cantidad_consumida: string;
  cantidad_devuelta: string;
  fecha_recepcion: string;
  fecha_vencimiento: string;
  costo_unitario_consignacion: string;
  id_moneda: string;
  estado: EstadoConsignacion;
}

const CONS_PROV_VACIO: ConsignacionProveedorForm = {
  id_proveedor: '',
  id_producto: '',
  cantidad_recibida: '0',
  cantidad_consumida: '0',
  cantidad_devuelta: '0',
  fecha_recepcion: '',
  fecha_vencimiento: '',
  costo_unitario_consignacion: '0',
  id_moneda: '',
  estado: 'ACTIVA',
};

const ConsignacionProveedorTab: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroProveedor, setFiltroProveedor] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<StockConsignacionProveedor | null>(null);
  const [form, setForm] = useState<ConsignacionProveedorForm>(CONS_PROV_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: items = [], isLoading } = useQuery({
    queryKey: inventarioMaestrosKeys.consignacionProveedor(filtroProveedor || null, filtroEstado || null),
    queryFn: () =>
      stockConsignacionProveedorService.getAll({
        proveedor: filtroProveedor || undefined,
        estado: filtroEstado || undefined,
      }),
  });
  const { data: productos = [] } = useProductos();
  const { data: proveedores = [] } = useQuery({
    queryKey: ['proveedores', 'maestro', empresaId],
    queryFn: () => proveedoresService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });
  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.listFull(),
    queryFn: fetchMonedas,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: inventarioMaestrosKeys.consignacionProveedorAll() });

  const nombreProveedor = (id: string) =>
    proveedores.find((p) => p.id_proveedor === id)?.razon_social ?? id;

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...CONS_PROV_VACIO, id_proveedor: filtroProveedor });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (s: StockConsignacionProveedor) => {
    setEditando(s);
    setForm({
      id_proveedor: s.id_proveedor,
      id_producto: s.id_producto,
      cantidad_recibida: s.cantidad_recibida,
      cantidad_consumida: s.cantidad_consumida,
      cantidad_devuelta: s.cantidad_devuelta,
      fecha_recepcion: s.fecha_recepcion ?? '',
      fecha_vencimiento: s.fecha_vencimiento ?? '',
      costo_unitario_consignacion: s.costo_unitario_consignacion,
      id_moneda: s.id_moneda,
      estado: s.estado,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: StockConsignacionProveedorPayload) =>
      editando
        ? stockConsignacionProveedorService.update(editando.id_stock_consignacion, payload)
        : stockConsignacionProveedorService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la consignación.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => stockConsignacionProveedorService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la consignación.')),
  });

  const handleGuardar = () => {
    if (!form.id_proveedor || !form.id_producto || !form.id_moneda || !form.fecha_recepcion) {
      setErrorMsg('Complete proveedor, producto, moneda y fecha de recepción.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_proveedor: form.id_proveedor,
      id_producto: form.id_producto,
      id_variante: null,
      cantidad_recibida: form.cantidad_recibida.trim() || '0',
      cantidad_consumida: form.cantidad_consumida.trim() || '0',
      cantidad_devuelta: form.cantidad_devuelta.trim() || '0',
      fecha_recepcion: form.fecha_recepcion,
      fecha_vencimiento: form.fecha_vencimiento || null,
      costo_unitario_consignacion: form.costo_unitario_consignacion.trim() || '0',
      id_moneda: form.id_moneda,
      estado: form.estado,
    });
  };

  const handleEliminar = (s: StockConsignacionProveedor) => {
    if (window.confirm('¿Eliminar este saldo en consignación?')) {
      eliminar.mutate(s.id_stock_consignacion);
    }
  };

  const columns: Column<StockConsignacionProveedor>[] = [
    { key: 'proveedor', header: 'Proveedor', render: (s) => nombreProveedor(s.id_proveedor) },
    { key: 'producto', header: 'Producto', render: (s) => nombreProducto(productos, s.id_producto) },
    { key: 'recibida', header: 'Recibida', render: (s) => s.cantidad_recibida },
    { key: 'consumida', header: 'Consumida', render: (s) => s.cantidad_consumida },
    { key: 'estado', header: 'Estado', render: (s) => <StatusChip value={s.estado} label={s.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (s) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(s)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(s)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} flexWrap="wrap">
        <Stack direction="row" spacing={1}>
          <TextField
            select
            label="Filtrar por proveedor"
            value={filtroProveedor}
            onChange={(e) => setFiltroProveedor(e.target.value)}
            size="small"
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">Todos los proveedores</MenuItem>
            {proveedores.map((p) => (
              <MenuItem key={p.id_proveedor} value={p.id_proveedor}>
                {p.razon_social}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Estado"
            value={filtroEstado}
            onChange={(e) => setFiltroEstado(e.target.value)}
            size="small"
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">Todos</MenuItem>
            {ESTADOS.map((es) => (
              <MenuItem key={es} value={es}>
                {es}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva consignación
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(s) => s.id_stock_consignacion}
        loading={isLoading}
        emptyMessage="Sin consignaciones de proveedores."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>
          {editando ? 'Editar consignación de proveedor' : 'Nueva consignación de proveedor'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Proveedor"
              value={form.id_proveedor}
              onChange={(e) => setForm((f) => ({ ...f, id_proveedor: e.target.value }))}
              required
              fullWidth
            >
              {proveedores.map((p) => (
                <MenuItem key={p.id_proveedor} value={p.id_proveedor}>
                  {p.razon_social}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Producto"
              value={form.id_producto}
              onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
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
            <Stack direction="row" spacing={1}>
              <TextField
                label="Cantidad recibida"
                value={form.cantidad_recibida}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_recibida: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Cantidad consumida"
                value={form.cantidad_consumida}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_consumida: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Cantidad devuelta"
                value={form.cantidad_devuelta}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_devuelta: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha recepción"
                type="date"
                value={form.fecha_recepcion}
                onChange={(e) => setForm((f) => ({ ...f, fecha_recepcion: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Fecha vencimiento"
                type="date"
                value={form.fecha_vencimiento}
                onChange={(e) => setForm((f) => ({ ...f, fecha_vencimiento: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Costo unitario"
                value={form.costo_unitario_consignacion}
                onChange={(e) => setForm((f) => ({ ...f, costo_unitario_consignacion: e.target.value }))}
                inputMode="decimal"
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
            </Stack>
            <TextField
              select
              label="Estado"
              value={form.estado}
              onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value as EstadoConsignacion }))}
              fullWidth
            >
              {ESTADOS.map((es) => (
                <MenuItem key={es} value={es}>
                  {es}
                </MenuItem>
              ))}
            </TextField>
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

// ─────────────────────────────────────────────────────────────────────────────
// Reglas de Reabastecimiento
// ─────────────────────────────────────────────────────────────────────────────

const RUTAS_REABASTECIMIENTO: { value: RutaReabastecimiento; label: string }[] = [
  { value: 'COMPRA', label: 'Compra' },
  { value: 'MANUFACTURA', label: 'Manufactura' },
  { value: 'TRANSFERENCIA', label: 'Transferencia' },
];

interface ReglaForm {
  id_producto: string;
  id_almacen: string;
  stock_minimo: string;
  stock_maximo: string;
  cantidad_multiplo: string;
  ruta: RutaReabastecimiento;
  id_proveedor_preferido: string;
  id_almacen_origen: string;
  activo: boolean;
}

const REGLA_VACIA: ReglaForm = {
  id_producto: '',
  id_almacen: '',
  stock_minimo: '0',
  stock_maximo: '10',
  cantidad_multiplo: '1',
  ruta: 'COMPRA',
  id_proveedor_preferido: '',
  id_almacen_origen: '',
  activo: true,
};

const ReabastecimientoTab: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroAlmacen, setFiltroAlmacen] = useState('');
  const [filtroProducto, setFiltroProducto] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ReglaReabastecimiento | null>(null);
  const [form, setForm] = useState<ReglaForm>(REGLA_VACIA);
  const [evaluaciones, setEvaluaciones] = useState<EvaluacionReabastecimientoItem[]>([]);
  const [errorMsg, setErrorMsg] = useState('');
  const [okMsg, setOkMsg] = useState('');

  const { data: reglas = [], isLoading } = useQuery({
    queryKey: inventarioMaestrosKeys.reglas(filtroAlmacen || null, filtroProducto || null),
    queryFn: () =>
      reglasReabastecimientoService.getAll({
        almacen: filtroAlmacen || undefined,
        producto: filtroProducto || undefined,
      }),
  });
  const { data: productos = [] } = useProductos();
  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });
  const { data: proveedores = [] } = useQuery({
    queryKey: ['proveedores', 'maestro', empresaId],
    queryFn: () => proveedoresService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: inventarioMaestrosKeys.reglasAll() });

  const nombreAlmacen = (id: string) =>
    almacenes.find((a: Almacen) => a.id_almacen === id)?.nombre_almacen ?? id;

  const evalPorRegla = new Map<string, EvaluacionReabastecimientoItem>();
  for (const item of evaluaciones) {
    evalPorRegla.set(item.id_regla, item);
  }

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...REGLA_VACIA, id_almacen: filtroAlmacen, id_producto: filtroProducto });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (r: ReglaReabastecimiento) => {
    setEditando(r);
    setForm({
      id_producto: r.id_producto,
      id_almacen: r.id_almacen,
      stock_minimo: r.stock_minimo,
      stock_maximo: r.stock_maximo,
      cantidad_multiplo: r.cantidad_multiplo,
      ruta: r.ruta,
      id_proveedor_preferido: r.id_proveedor_preferido ?? '',
      id_almacen_origen: r.id_almacen_origen ?? '',
      activo: r.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ReglaReabastecimientoPayload) =>
      editando
        ? reglasReabastecimientoService.update(editando.id_regla, payload)
        : reglasReabastecimientoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la regla.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => reglasReabastecimientoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la regla.')),
  });

  const evaluarMut = useMutation({
    mutationFn: () =>
      reglasReabastecimientoService.evaluar({
        almacen: filtroAlmacen || undefined,
        incluir_ok: true,
      }),
    onSuccess: (items) => {
      setEvaluaciones(items);
      const requieren = items.filter((i) => i.requiere_reabastecimiento).length;
      setOkMsg(`Evaluación completada: ${items.length} regla(s) analizada(s), ${requieren} requieren reabastecimiento.`);
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo evaluar el reabastecimiento.')),
  });

  const generarBorradorMut = useMutation({
    mutationFn: (idRegla: string) => reglasReabastecimientoService.generarBorrador(idRegla),
    onSuccess: (res) => {
      setOkMsg(`Borrador ${res.tipo_documento} ${res.numero} creado (${res.estado}) por ${res.cantidad}.`);
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo generar el borrador.')),
  });

  const handleGuardar = () => {
    if (!form.id_producto || !form.id_almacen) {
      setErrorMsg('Seleccione producto y almacén.');
      return;
    }
    const minD = D(form.stock_minimo);
    const maxD = D(form.stock_maximo);
    const multD = D(form.cantidad_multiplo);
    if (minD.lt(0) || maxD.lt(minD) || multD.lte(0)) {
      setErrorMsg('Verifique que mínimo >= 0, máximo >= mínimo y múltiplo > 0.');
      return;
    }
    if (form.ruta === 'TRANSFERENCIA') {
      if (!form.id_almacen_origen) {
        setErrorMsg('La ruta Transferencia requiere almacén origen.');
        return;
      }
      if (form.id_almacen_origen === form.id_almacen) {
        setErrorMsg('El almacén origen y destino deben ser distintos.');
        return;
      }
    }
    guardar.mutate({
      id_producto: form.id_producto,
      id_almacen: form.id_almacen,
      stock_minimo: form.stock_minimo.trim(),
      stock_maximo: form.stock_maximo.trim(),
      cantidad_multiplo: form.cantidad_multiplo.trim(),
      ruta: form.ruta,
      id_proveedor_preferido: form.ruta === 'COMPRA' ? form.id_proveedor_preferido || null : null,
      id_almacen_origen: form.ruta === 'TRANSFERENCIA' ? form.id_almacen_origen || null : null,
      activo: form.activo,
    });
  };

  const columns: Column<ReglaReabastecimiento>[] = [
    { key: 'producto', header: 'Producto', render: (r) => r.producto_nombre ?? nombreProducto(productos, r.id_producto) },
    { key: 'almacen', header: 'Almacén', render: (r) => r.almacen_nombre ?? nombreAlmacen(r.id_almacen) },
    { key: 'ruta', header: 'Ruta', render: (r) => <Chip label={r.ruta} size="small" /> },
    { key: 'min', header: 'Mínimo', align: 'right', render: (r) => r.stock_minimo },
    { key: 'max', header: 'Máximo', align: 'right', render: (r) => r.stock_maximo },
    { key: 'mult', header: 'Múltiplo', align: 'right', render: (r) => r.cantidad_multiplo },
    {
      key: 'evaluacion',
      header: 'Evaluación',
      render: (r) => {
        const ev = evalPorRegla.get(r.id_regla);
        if (!ev) return '—';
        if (!ev.requiere_reabastecimiento) {
          return <Chip label={`OK (Proy: ${ev.stock_proyectado})`} color="success" size="small" />;
        }
        return (
          <Stack direction="row" spacing={0.5} flexWrap="wrap">
            <Chip label={`Déficit: ${ev.deficit}`} color="warning" size="small" />
            <Chip label={`Sugerida: ${ev.cantidad_sugerida}`} color="error" size="small" />
          </Stack>
        );
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => {
        const ev = evalPorRegla.get(r.id_regla);
        const puedeGenerar = Boolean(r.activo && (!ev || ev.requiere_reabastecimiento));
        return (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="outlined"
              disabled={!puedeGenerar || generarBorradorMut.isPending}
              onClick={() => generarBorradorMut.mutate(r.id_regla)}
            >
              Generar borrador
            </Button>
            <Button size="small" onClick={() => abrirEditar(r)}>
              Editar
            </Button>
            <Button
              size="small"
              color="error"
              disabled={eliminar.isPending}
              onClick={() => eliminar.mutate(r.id_regla)}
            >
              Eliminar
            </Button>
          </Stack>
        );
      },
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} flexWrap="wrap">
        <Stack direction="row" spacing={1}>
          <TextField
            select
            label="Almacén"
            value={filtroAlmacen}
            onChange={(e) => setFiltroAlmacen(e.target.value)}
            size="small"
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="">Todos los almacenes</MenuItem>
            {almacenes.map((a) => (
              <MenuItem key={a.id_almacen} value={a.id_almacen}>
                {a.nombre_almacen}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Producto"
            value={filtroProducto}
            onChange={(e) => setFiltroProducto(e.target.value)}
            size="small"
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">Todos los productos</MenuItem>
            {productos.map((p) => (
              <MenuItem key={p.id_producto} value={p.id_producto}>
                {p.nombre_producto}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            startIcon={<PlayArrowOutlined />}
            disabled={evaluarMut.isPending}
            onClick={() => evaluarMut.mutate()}
          >
            Evaluar reabastecimiento
          </Button>
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nueva regla
          </Button>
        </Stack>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      {okMsg && (
        <Alert severity="success" onClose={() => setOkMsg('')}>
          {okMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={reglas}
        getRowKey={(r) => r.id_regla}
        loading={isLoading}
        emptyMessage="Sin reglas de reabastecimiento. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar regla de reabastecimiento' : 'Nueva regla de reabastecimiento'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Producto"
              value={form.id_producto}
              onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
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
              select
              label="Almacén"
              value={form.id_almacen}
              onChange={(e) => setForm((f) => ({ ...f, id_almacen: e.target.value }))}
              required
              fullWidth
            >
              {almacenes.map((a) => (
                <MenuItem key={a.id_almacen} value={a.id_almacen}>
                  {a.nombre_almacen}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Ruta"
              value={form.ruta}
              onChange={(e) => setForm((f) => ({ ...f, ruta: e.target.value as RutaReabastecimiento }))}
              fullWidth
            >
              {RUTAS_REABASTECIMIENTO.map((rt) => (
                <MenuItem key={rt.value} value={rt.value}>
                  {rt.label}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Stock mínimo"
                value={form.stock_minimo}
                onChange={(e) => setForm((f) => ({ ...f, stock_minimo: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Stock máximo"
                value={form.stock_maximo}
                onChange={(e) => setForm((f) => ({ ...f, stock_maximo: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Múltiplo"
                value={form.cantidad_multiplo}
                onChange={(e) => setForm((f) => ({ ...f, cantidad_multiplo: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            </Stack>
            {form.ruta === 'COMPRA' && (
              <TextField
                select
                label="Proveedor preferido"
                value={form.id_proveedor_preferido}
                onChange={(e) => setForm((f) => ({ ...f, id_proveedor_preferido: e.target.value }))}
                fullWidth
              >
                <MenuItem value="">Sin proveedor preferido</MenuItem>
                {proveedores.map((p) => (
                  <MenuItem key={p.id_proveedor} value={p.id_proveedor}>
                    {p.razon_social}
                  </MenuItem>
                ))}
              </TextField>
            )}
            {form.ruta === 'TRANSFERENCIA' && (
              <TextField
                select
                label="Almacén origen"
                value={form.id_almacen_origen}
                onChange={(e) => setForm((f) => ({ ...f, id_almacen_origen: e.target.value }))}
                required
                fullWidth
              >
                {almacenes
                  .filter((a) => a.id_almacen !== form.id_almacen)
                  .map((a) => (
                    <MenuItem key={a.id_almacen} value={a.id_almacen}>
                      {a.nombre_almacen}
                    </MenuItem>
                  ))}
              </TextField>
            )}
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Regla activa"
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

// ─────────────────────────────────────────────────────────────────────────────
// Lotes de Producto (opt-in)
// ─────────────────────────────────────────────────────────────────────────────

function fechaIsoLocal(offsetDias = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDias);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function estadoVencimientoLote(
  fechaVencimiento: string | null,
  hoyIso: string,
  limite30Iso: string,
): { label: string; color: 'default' | 'error' | 'warning' | 'success' } {
  if (!fechaVencimiento) return { label: 'Sin vencimiento', color: 'default' };
  if (fechaVencimiento < hoyIso) return { label: 'Vencido', color: 'error' };
  if (fechaVencimiento <= limite30Iso) return { label: 'Por vencer', color: 'warning' };
  return { label: 'Vigente', color: 'success' };
}

const LotesTab: React.FC = () => {
  const [filtroProducto, setFiltroProducto] = useState('');
  const [filtroAlmacen, setFiltroAlmacen] = useState('');
  const [porVencer30, setPorVencer30] = useState(false);
  const [soloConStock, setSoloConStock] = useState(true);

  const hoyIso = fechaIsoLocal(0);
  const limite30Iso = fechaIsoLocal(30);

  const { data: lotes = [], isLoading } = useQuery({
    queryKey: inventarioMaestrosKeys.lotes({
      almacen: filtroAlmacen || null,
      producto: filtroProducto || null,
      por_vencer_dias: porVencer30 ? 30 : null,
      solo_con_stock: soloConStock,
    }),
    queryFn: () =>
      lotesProductoService.getAll({
        almacen: filtroAlmacen || undefined,
        producto: filtroProducto || undefined,
        por_vencer_dias: porVencer30 ? 30 : undefined,
        solo_con_stock: soloConStock,
      }),
  });
  const { data: productos = [] } = useProductos();
  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });

  const columns: Column<LoteProducto>[] = [
    { key: 'producto', header: 'Producto', render: (l) => l.producto_nombre ?? nombreProducto(productos, l.id_producto) },
    {
      key: 'almacen',
      header: 'Almacén',
      render: (l) => l.almacen_nombre ?? almacenes.find((a) => a.id_almacen === l.id_almacen)?.nombre_almacen ?? l.id_almacen,
    },
    { key: 'numero_lote', header: 'N° Lote', render: (l) => l.numero_lote },
    { key: 'fabricacion', header: 'Fabricación', render: (l) => l.fecha_fabricacion || '—' },
    { key: 'vencimiento', header: 'Vencimiento', render: (l) => l.fecha_vencimiento || '—' },
    { key: 'disponible', header: 'Disponible', align: 'right', render: (l) => l.cantidad_disponible },
    { key: 'reservada', header: 'Reservada', align: 'right', render: (l) => l.cantidad_reservada },
    {
      key: 'libre',
      header: 'Libre',
      align: 'right',
      render: (l) => l.cantidad_libre ?? D(l.cantidad_disponible).minus(D(l.cantidad_reservada)).toFixed(4),
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (l) => {
        const est = estadoVencimientoLote(l.fecha_vencimiento, hoyIso, limite30Iso);
        return <Chip label={est.label} color={est.color} size="small" />;
      },
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
        <TextField
          select
          label="Producto"
          value={filtroProducto}
          onChange={(e) => setFiltroProducto(e.target.value)}
          size="small"
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos los productos</MenuItem>
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Almacén"
          value={filtroAlmacen}
          onChange={(e) => setFiltroAlmacen(e.target.value)}
          size="small"
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Todos los almacenes</MenuItem>
          {almacenes.map((a) => (
            <MenuItem key={a.id_almacen} value={a.id_almacen}>
              {a.nombre_almacen}
            </MenuItem>
          ))}
        </TextField>
        <FormControlLabel
          control={<Checkbox checked={porVencer30} onChange={(e) => setPorVencer30(e.target.checked)} />}
          label="Por vencer <= 30d"
        />
        <FormControlLabel
          control={<Checkbox checked={soloConStock} onChange={(e) => setSoloConStock(e.target.checked)} />}
          label="Solo con stock"
        />
      </Stack>

      <DataTable
        columns={columns}
        rows={lotes}
        getRowKey={(l) => l.id_lote}
        loading={isLoading}
        emptyMessage="Sin lotes registrados para los filtros seleccionados."
      />
    </Stack>
  );
};

export default InventarioMaestrosPage;
