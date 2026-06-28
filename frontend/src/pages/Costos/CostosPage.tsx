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
  costosProduccionService,
  costosEstandarProductoService,
  analisisVariacionService,
  type CostoProduccion,
  type CostoProduccionPayload,
  type CostoEstandarProducto,
  type CostoEstandarProductoPayload,
  type AnalisisVariacionCosto,
  type AnalisisVariacionCostoPayload,
  type TipoCosto,
  type TipoVariacion,
} from '../../services/costosService';
import { fetchProductos, type Producto } from '../../services/productosService';
import { fetchMonedas, type Moneda } from '../../services/monedas';
import { manufacturaService, type OrdenProduccion } from '../../services/manufacturaService';
import { costosKeys, productosKeys, finanzasKeys, manufacturaKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError, toList } from '../../utils/api';

// ── Choices compartidos ──────────────────────────────────────────────────────

const TIPO_COSTO_OPCIONES: { value: TipoCosto; label: string }[] = [
  { value: 'MATERIAL_DIRECTO', label: 'Material Directo' },
  { value: 'MANO_OBRA_DIRECTA', label: 'Mano de Obra Directa' },
  { value: 'COSTOS_INDIRECTOS', label: 'Costos Indirectos' },
  { value: 'OVERHEAD', label: 'Overhead' },
];

const TIPO_VARIACION_OPCIONES: { value: TipoVariacion; label: string }[] = [
  { value: 'FAVORABLE', label: 'Favorable' },
  { value: 'DESFAVORABLE', label: 'Desfavorable' },
  { value: 'NEUTRO', label: 'Neutro' },
];

// Color del chip por resultado del análisis (FAVORABLE=verde, DESFAVORABLE=rojo).
const VARIACION_COLOR = {
  favorable: 'success' as const,
  desfavorable: 'error' as const,
  neutro: 'default' as const,
};

const tipoCostoLabel = (v: string): string =>
  TIPO_COSTO_OPCIONES.find((o) => o.value === v)?.label ?? v;

// ─────────────────────────────────────────────────────────────────────────────
// Costo de producción (costo real)
// ─────────────────────────────────────────────────────────────────────────────

interface ProduccionForm {
  id_orden_produccion: string;
  tipo_costo: TipoCosto;
  costo_unitario: string;
  cantidad: string;
  costo_total: string;
  id_moneda: string;
  fecha_calculo: string;
  observaciones: string;
  activo: boolean;
}

const PRODUCCION_VACIO: ProduccionForm = {
  id_orden_produccion: '',
  tipo_costo: 'MATERIAL_DIRECTO',
  costo_unitario: '',
  cantidad: '',
  costo_total: '',
  id_moneda: '',
  fecha_calculo: '',
  observaciones: '',
  activo: true,
};

interface SubseccionProps {
  empresaId: string;
  ordenes: OrdenProduccion[];
  productos: Producto[];
  monedas: Moneda[];
}

const CostosProduccionSeccion: React.FC<SubseccionProps> = ({ empresaId, ordenes, monedas }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CostoProduccion | null>(null);
  const [form, setForm] = useState<ProduccionForm>(PRODUCCION_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: costosKeys.produccion(empresaId),
    queryFn: () => costosProduccionService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: costosKeys.produccionAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...PRODUCCION_VACIO, id_moneda: monedas[0]?.id_moneda ?? '' });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CostoProduccion) => {
    setEditando(c);
    setForm({
      id_orden_produccion: c.id_orden_produccion,
      tipo_costo: c.tipo_costo,
      costo_unitario: c.costo_unitario,
      cantidad: c.cantidad,
      costo_total: c.costo_total,
      id_moneda: c.id_moneda,
      fecha_calculo: (c.fecha_calculo ?? '').slice(0, 10),
      observaciones: c.observaciones ?? '',
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CostoProduccionPayload) =>
      editando
        ? costosProduccionService.update(editando.id_costo_produccion, payload)
        : costosProduccionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el costo.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => costosProduccionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el costo.')),
  });

  const handleGuardar = () => {
    if (!form.id_orden_produccion) {
      setErrorMsg('Seleccione la orden de producción.');
      return;
    }
    if (!form.costo_total.trim()) {
      setErrorMsg('Indique el costo total.');
      return;
    }
    if (!form.id_moneda) {
      setErrorMsg('Seleccione la moneda.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_orden_produccion: form.id_orden_produccion,
      tipo_costo: form.tipo_costo,
      costo_unitario: form.costo_unitario || '0',
      cantidad: form.cantidad || '0',
      costo_total: form.costo_total,
      id_moneda: form.id_moneda,
      fecha_calculo: form.fecha_calculo,
      observaciones: form.observaciones.trim() || null,
      activo: form.activo,
    });
  };

  const handleEliminar = (c: CostoProduccion) => {
    if (window.confirm('¿Eliminar este costo de producción?')) {
      eliminar.mutate(c.id_costo_produccion);
    }
  };

  const ordenLabel = (id: string) => {
    const o = ordenes.find((x) => x.id === id);
    return o ? `${o.referencia_externa || o.id}` : id;
  };

  const columns: Column<CostoProduccion>[] = [
    { key: 'orden', header: 'Orden de producción', render: (c) => ordenLabel(c.id_orden_produccion) },
    { key: 'tipo_costo', header: 'Tipo de costo', render: (c) => tipoCostoLabel(c.tipo_costo) },
    { key: 'costo_unitario', header: 'Costo unitario', render: (c) => c.costo_unitario },
    { key: 'cantidad', header: 'Cantidad', render: (c) => c.cantidad },
    { key: 'costo_total', header: 'Costo total', render: (c) => c.costo_total },
    { key: 'activo', header: 'Activo', render: (c) => <StatusChip value={c.activo ?? true} /> },
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
          Nuevo costo real
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
        getRowKey={(c) => c.id_costo_produccion}
        loading={isLoading}
        emptyMessage="Sin costos de producción. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar costo real' : 'Nuevo costo real'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Orden de producción"
              value={form.id_orden_produccion}
              onChange={(e) => setForm((f) => ({ ...f, id_orden_produccion: e.target.value }))}
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {ordenes.map((o) => (
                <MenuItem key={o.id} value={o.id}>
                  {o.referencia_externa || o.id}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Tipo de costo"
              value={form.tipo_costo}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_costo: e.target.value as TipoCosto }))
              }
              fullWidth
            >
              {TIPO_COSTO_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Costo unitario"
              value={form.costo_unitario}
              onChange={(e) => setForm((f) => ({ ...f, costo_unitario: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Cantidad"
              value={form.cantidad}
              onChange={(e) => setForm((f) => ({ ...f, cantidad: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Costo total"
              value={form.costo_total}
              onChange={(e) => setForm((f) => ({ ...f, costo_total: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Moneda"
              value={form.id_moneda}
              onChange={(e) => setForm((f) => ({ ...f, id_moneda: e.target.value }))}
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {monedas.map((m) => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>
                  {m.codigo_iso} — {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha de cálculo"
              type="date"
              value={form.fecha_calculo}
              onChange={(e) => setForm((f) => ({ ...f, fecha_calculo: e.target.value }))}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              label="Observaciones"
              value={form.observaciones}
              onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
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
// Costo estándar de producto
// ─────────────────────────────────────────────────────────────────────────────

interface EstandarForm {
  id_producto: string;
  tipo_costo: TipoCosto;
  costo_unitario_estandar: string;
  id_moneda: string;
  fecha_vigencia_desde: string;
  fecha_vigencia_hasta: string;
  activo: boolean;
}

const ESTANDAR_VACIO: EstandarForm = {
  id_producto: '',
  tipo_costo: 'MATERIAL_DIRECTO',
  costo_unitario_estandar: '',
  id_moneda: '',
  fecha_vigencia_desde: '',
  fecha_vigencia_hasta: '',
  activo: true,
};

const CostosEstandarSeccion: React.FC<SubseccionProps> = ({ empresaId, productos, monedas }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CostoEstandarProducto | null>(null);
  const [form, setForm] = useState<EstandarForm>(ESTANDAR_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: costosKeys.estandar(empresaId),
    queryFn: () => costosEstandarProductoService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: costosKeys.estandarAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...ESTANDAR_VACIO, id_moneda: monedas[0]?.id_moneda ?? '' });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CostoEstandarProducto) => {
    setEditando(c);
    setForm({
      id_producto: c.id_producto,
      tipo_costo: c.tipo_costo,
      costo_unitario_estandar: c.costo_unitario_estandar,
      id_moneda: c.id_moneda,
      fecha_vigencia_desde: (c.fecha_vigencia_desde ?? '').slice(0, 10),
      fecha_vigencia_hasta: (c.fecha_vigencia_hasta ?? '').slice(0, 10),
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CostoEstandarProductoPayload) =>
      editando
        ? costosEstandarProductoService.update(editando.id_costo_estandar, payload)
        : costosEstandarProductoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo guardar el costo estándar.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => costosEstandarProductoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el costo estándar.')),
  });

  const handleGuardar = () => {
    if (!form.id_producto) {
      setErrorMsg('Seleccione el producto.');
      return;
    }
    if (!form.costo_unitario_estandar.trim()) {
      setErrorMsg('Indique el costo unitario estándar.');
      return;
    }
    if (!form.fecha_vigencia_desde) {
      setErrorMsg('Indique la fecha de vigencia desde.');
      return;
    }
    if (!form.id_moneda) {
      setErrorMsg('Seleccione la moneda.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_producto: form.id_producto,
      tipo_costo: form.tipo_costo,
      costo_unitario_estandar: form.costo_unitario_estandar,
      id_moneda: form.id_moneda,
      fecha_vigencia_desde: form.fecha_vigencia_desde,
      fecha_vigencia_hasta: form.fecha_vigencia_hasta || null,
      activo: form.activo,
    });
  };

  const handleEliminar = (c: CostoEstandarProducto) => {
    if (window.confirm('¿Eliminar este costo estándar?')) {
      eliminar.mutate(c.id_costo_estandar);
    }
  };

  const productoLabel = (id: string) => {
    const p = productos.find((x) => x.id_producto === id);
    return p ? p.nombre_producto : id;
  };

  const columns: Column<CostoEstandarProducto>[] = [
    { key: 'producto', header: 'Producto', render: (c) => productoLabel(c.id_producto) },
    { key: 'tipo_costo', header: 'Tipo de costo', render: (c) => tipoCostoLabel(c.tipo_costo) },
    {
      key: 'costo_unitario_estandar',
      header: 'Costo unitario estándar',
      render: (c) => c.costo_unitario_estandar,
    },
    {
      key: 'fecha_vigencia_desde',
      header: 'Vigencia desde',
      render: (c) => c.fecha_vigencia_desde,
    },
    {
      key: 'fecha_vigencia_hasta',
      header: 'Vigencia hasta',
      render: (c) => c.fecha_vigencia_hasta || '—',
    },
    { key: 'activo', header: 'Activo', render: (c) => <StatusChip value={c.activo ?? true} /> },
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
          Nuevo costo estándar
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
        getRowKey={(c) => c.id_costo_estandar}
        loading={isLoading}
        emptyMessage="Sin costos estándar. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar costo estándar' : 'Nuevo costo estándar'}</DialogTitle>
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
              <MenuItem value="">— Seleccione —</MenuItem>
              {productos.map((p) => (
                <MenuItem key={p.id_producto} value={p.id_producto}>
                  {p.nombre_producto}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Tipo de costo"
              value={form.tipo_costo}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_costo: e.target.value as TipoCosto }))
              }
              fullWidth
            >
              {TIPO_COSTO_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Costo unitario estándar"
              value={form.costo_unitario_estandar}
              onChange={(e) =>
                setForm((f) => ({ ...f, costo_unitario_estandar: e.target.value }))
              }
              required
              fullWidth
            />
            <TextField
              select
              label="Moneda"
              value={form.id_moneda}
              onChange={(e) => setForm((f) => ({ ...f, id_moneda: e.target.value }))}
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {monedas.map((m) => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>
                  {m.codigo_iso} — {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Vigencia desde"
              type="date"
              value={form.fecha_vigencia_desde}
              onChange={(e) => setForm((f) => ({ ...f, fecha_vigencia_desde: e.target.value }))}
              InputLabelProps={{ shrink: true }}
              required
              fullWidth
            />
            <TextField
              label="Vigencia hasta"
              type="date"
              value={form.fecha_vigencia_hasta}
              onChange={(e) => setForm((f) => ({ ...f, fecha_vigencia_hasta: e.target.value }))}
              InputLabelProps={{ shrink: true }}
              helperText="Opcional."
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
// Análisis de variación de costo
// ─────────────────────────────────────────────────────────────────────────────

interface VariacionForm {
  id_orden_produccion: string;
  id_producto: string;
  tipo_costo: TipoCosto;
  costo_estandar: string;
  costo_real: string;
  variacion_cantidad: string;
  variacion_precio: string;
  variacion_total: string;
  porcentaje_variacion: string;
  tipo_variacion: TipoVariacion;
  fecha_analisis: string;
  observaciones: string;
  activo: boolean;
}

const VARIACION_VACIO: VariacionForm = {
  id_orden_produccion: '',
  id_producto: '',
  tipo_costo: 'MATERIAL_DIRECTO',
  costo_estandar: '',
  costo_real: '',
  variacion_cantidad: '0',
  variacion_precio: '0',
  variacion_total: '',
  porcentaje_variacion: '0',
  tipo_variacion: 'NEUTRO',
  fecha_analisis: '',
  observaciones: '',
  activo: true,
};

const AnalisisVariacionSeccion: React.FC<SubseccionProps> = ({
  empresaId,
  ordenes,
  productos,
}) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<AnalisisVariacionCosto | null>(null);
  const [form, setForm] = useState<VariacionForm>(VARIACION_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: filas = [], isLoading } = useQuery({
    queryKey: costosKeys.variacion(empresaId),
    queryFn: () => analisisVariacionService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: costosKeys.variacionAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(VARIACION_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: AnalisisVariacionCosto) => {
    setEditando(c);
    setForm({
      id_orden_produccion: c.id_orden_produccion,
      id_producto: c.id_producto,
      tipo_costo: c.tipo_costo,
      costo_estandar: c.costo_estandar,
      costo_real: c.costo_real,
      variacion_cantidad: c.variacion_cantidad,
      variacion_precio: c.variacion_precio,
      variacion_total: c.variacion_total,
      porcentaje_variacion: c.porcentaje_variacion,
      tipo_variacion: c.tipo_variacion,
      fecha_analisis: (c.fecha_analisis ?? '').slice(0, 10),
      observaciones: c.observaciones ?? '',
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: AnalisisVariacionCostoPayload) =>
      editando
        ? analisisVariacionService.update(editando.id_analisis_variacion, payload)
        : analisisVariacionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el análisis.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => analisisVariacionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el análisis.')),
  });

  const handleGuardar = () => {
    if (!form.id_orden_produccion) {
      setErrorMsg('Seleccione la orden de producción.');
      return;
    }
    if (!form.id_producto) {
      setErrorMsg('Seleccione el producto.');
      return;
    }
    if (!form.variacion_total.trim()) {
      setErrorMsg('Indique la variación total.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_orden_produccion: form.id_orden_produccion,
      id_producto: form.id_producto,
      tipo_costo: form.tipo_costo,
      costo_estandar: form.costo_estandar || '0',
      costo_real: form.costo_real || '0',
      variacion_cantidad: form.variacion_cantidad || '0',
      variacion_precio: form.variacion_precio || '0',
      variacion_total: form.variacion_total,
      porcentaje_variacion: form.porcentaje_variacion || '0',
      tipo_variacion: form.tipo_variacion,
      fecha_analisis: form.fecha_analisis,
      observaciones: form.observaciones.trim() || null,
      activo: form.activo,
    });
  };

  const handleEliminar = (c: AnalisisVariacionCosto) => {
    if (window.confirm('¿Eliminar este análisis de variación?')) {
      eliminar.mutate(c.id_analisis_variacion);
    }
  };

  const productoLabel = (id: string) => {
    const p = productos.find((x) => x.id_producto === id);
    return p ? p.nombre_producto : id;
  };
  const ordenLabel = (id: string) => {
    const o = ordenes.find((x) => x.id === id);
    return o ? `${o.referencia_externa || o.id}` : id;
  };

  const columns: Column<AnalisisVariacionCosto>[] = [
    { key: 'orden', header: 'Orden', render: (c) => ordenLabel(c.id_orden_produccion) },
    { key: 'producto', header: 'Producto', render: (c) => productoLabel(c.id_producto) },
    { key: 'tipo_costo', header: 'Tipo de costo', render: (c) => tipoCostoLabel(c.tipo_costo) },
    { key: 'costo_estandar', header: 'Costo estándar', render: (c) => c.costo_estandar },
    { key: 'costo_real', header: 'Costo real', render: (c) => c.costo_real },
    {
      key: 'variacion_total',
      header: 'Variación',
      render: (c) => `${c.variacion_total} (${c.porcentaje_variacion}%)`,
    },
    {
      key: 'tipo_variacion',
      header: 'Resultado',
      render: (c) => <StatusChip value={c.tipo_variacion} colorMap={VARIACION_COLOR} />,
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
          Nuevo análisis
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
        getRowKey={(c) => c.id_analisis_variacion}
        loading={isLoading}
        emptyMessage="Sin análisis de variación. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar análisis' : 'Nuevo análisis'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Orden de producción"
              value={form.id_orden_produccion}
              onChange={(e) => setForm((f) => ({ ...f, id_orden_produccion: e.target.value }))}
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {ordenes.map((o) => (
                <MenuItem key={o.id} value={o.id}>
                  {o.referencia_externa || o.id}
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
              <MenuItem value="">— Seleccione —</MenuItem>
              {productos.map((p) => (
                <MenuItem key={p.id_producto} value={p.id_producto}>
                  {p.nombre_producto}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Tipo de costo"
              value={form.tipo_costo}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_costo: e.target.value as TipoCosto }))
              }
              fullWidth
            >
              {TIPO_COSTO_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Costo estándar"
              value={form.costo_estandar}
              onChange={(e) => setForm((f) => ({ ...f, costo_estandar: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Costo real"
              value={form.costo_real}
              onChange={(e) => setForm((f) => ({ ...f, costo_real: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Variación cantidad"
              value={form.variacion_cantidad}
              onChange={(e) => setForm((f) => ({ ...f, variacion_cantidad: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Variación precio"
              value={form.variacion_precio}
              onChange={(e) => setForm((f) => ({ ...f, variacion_precio: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Variación total"
              value={form.variacion_total}
              onChange={(e) => setForm((f) => ({ ...f, variacion_total: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Porcentaje de variación"
              value={form.porcentaje_variacion}
              onChange={(e) => setForm((f) => ({ ...f, porcentaje_variacion: e.target.value }))}
              fullWidth
            />
            <TextField
              select
              label="Resultado"
              value={form.tipo_variacion}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_variacion: e.target.value as TipoVariacion }))
              }
              fullWidth
            >
              {TIPO_VARIACION_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha de análisis"
              type="date"
              value={form.fecha_analisis}
              onChange={(e) => setForm((f) => ({ ...f, fecha_analisis: e.target.value }))}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              label="Observaciones"
              value={form.observaciones}
              onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
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
// Página contenedora con tabs
// ─────────────────────────────────────────────────────────────────────────────

const CostosPage: React.FC = () => {
  const empresaId = getEmpresaId() || '';
  const [tab, setTab] = useState(0);

  // Catálogos compartidos por las tres sub-secciones (productos, monedas, OF).
  const { data: productos = [] } = useQuery({
    queryKey: productosKeys.porEmpresa(empresaId),
    queryFn: async () => toList<Producto>(await fetchProductos(empresaId)),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: fetchMonedas,
  });

  const { data: ordenes = [] } = useQuery({
    queryKey: manufacturaKeys.ordenesAll(),
    queryFn: async () => (await manufacturaService.getOrdenesPaginated(1, 1000)).results,
  });

  return (
    <PageContainer>
      <PageHeader
        title="Costos"
        subtitle="Costeo de producción: costo real, costo estándar y análisis de variación."
      />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Costo real" />
        <Tab label="Costo estándar" />
        <Tab label="Análisis de variación" />
      </Tabs>

      {tab === 0 && (
        <CostosProduccionSeccion
          empresaId={empresaId}
          ordenes={ordenes}
          productos={productos}
          monedas={monedas}
        />
      )}
      {tab === 1 && (
        <CostosEstandarSeccion
          empresaId={empresaId}
          ordenes={ordenes}
          productos={productos}
          monedas={monedas}
        />
      )}
      {tab === 2 && (
        <AnalisisVariacionSeccion
          empresaId={empresaId}
          ordenes={ordenes}
          productos={productos}
          monedas={monedas}
        />
      )}
    </PageContainer>
  );
};

export default CostosPage;
