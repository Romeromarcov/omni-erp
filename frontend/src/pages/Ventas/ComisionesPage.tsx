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
  Grid,
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
import { PageContainer, PageHeader, DataTable, StatusChip, KpiCard } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  esquemasComisionService,
  esquemasComisionCategoriaService,
  comisionesService,
  type EsquemaComision,
  type EsquemaComisionPayload,
  type EsquemaComisionCategoria,
  type ComisionVenta,
  type EstadoComision,
  type ResumenComisionVendedor,
} from '../../services/comisionesService';
import { fetchUsuarios, type Usuario } from '../../services/users';
import { categoriasProductoService, type CategoriaProducto } from '../../services/inventarioService';
import { comisionesKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

// ── Choices y helpers compartidos ─────────────────────────────────────────────

const ESTADO_OPCIONES: { value: EstadoComision; label: string }[] = [
  { value: 'DEVENGADA', label: 'Devengada' },
  { value: 'LIQUIDADA', label: 'Liquidada' },
  { value: 'ANULADA', label: 'Anulada' },
];

// Color del chip por estado de la comisión.
const ESTADO_COLOR = {
  devengada: 'warning' as const,
  liquidada: 'success' as const,
  anulada: 'error' as const,
};

// ─────────────────────────────────────────────────────────────────────────────
// Tab 1 — Esquemas de comisión (CRUD esquema + overrides por categoría inline)
// ─────────────────────────────────────────────────────────────────────────────

interface EsquemaForm {
  vendedor: string;
  porcentaje_base: string;
  vigente_desde: string;
  vigente_hasta: string;
  activo: boolean;
}

const ESQUEMA_VACIO: EsquemaForm = {
  vendedor: '',
  porcentaje_base: '',
  vigente_desde: '',
  vigente_hasta: '',
  activo: true,
};

interface EsquemasSeccionProps {
  vendedores: Usuario[];
  categorias: CategoriaProducto[];
}

const EsquemasSeccion: React.FC<EsquemasSeccionProps> = ({ vendedores, categorias }) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<EsquemaComision | null>(null);
  const [form, setForm] = useState<EsquemaForm>(ESQUEMA_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalleEsquema, setDetalleEsquema] = useState<EsquemaComision | null>(null);

  const { data: esquemas = [], isLoading } = useQuery({
    queryKey: comisionesKeys.esquemas(),
    queryFn: () => esquemasComisionService.getAll(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: comisionesKeys.all() });

  const vendedorLabel = (id: string) => {
    const v = vendedores.find((u) => u.id === id);
    return v ? v.username : id;
  };

  const abrirCrear = () => {
    setEditando(null);
    setForm(ESQUEMA_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (e: EsquemaComision) => {
    setEditando(e);
    setForm({
      vendedor: e.vendedor,
      porcentaje_base: e.porcentaje_base,
      vigente_desde: e.vigente_desde ?? '',
      vigente_hasta: e.vigente_hasta ?? '',
      activo: e.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: EsquemaComisionPayload) =>
      editando
        ? esquemasComisionService.update(editando.id_esquema_comision, payload)
        : esquemasComisionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el esquema.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => esquemasComisionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el esquema.')),
  });

  const handleGuardar = () => {
    if (!form.vendedor || !form.porcentaje_base.trim()) {
      setErrorMsg('Seleccione el vendedor e indique el porcentaje base.');
      return;
    }
    guardar.mutate({
      vendedor: form.vendedor,
      porcentaje_base: form.porcentaje_base.trim(),
      vigente_desde: form.vigente_desde || null,
      vigente_hasta: form.vigente_hasta || null,
      activo: form.activo,
    });
  };

  const handleEliminar = (e: EsquemaComision) => {
    if (window.confirm('¿Eliminar este esquema de comisión?')) {
      eliminar.mutate(e.id_esquema_comision);
    }
  };

  const columns: Column<EsquemaComision>[] = [
    {
      key: 'vendedor',
      header: 'Vendedor',
      render: (e) => e.vendedor_username || vendedorLabel(e.vendedor),
    },
    { key: 'porcentaje_base', header: '% base', render: (e) => `${e.porcentaje_base}%` },
    { key: 'vigente_desde', header: 'Vigente desde', render: (e) => e.vigente_desde || '—' },
    { key: 'vigente_hasta', header: 'Vigente hasta', render: (e) => e.vigente_hasta || '—' },
    { key: 'activo', header: 'Activo', render: (e) => <StatusChip value={e.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (e) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalleEsquema(e)}>
            Categorías
          </Button>
          <Button size="small" onClick={() => abrirEditar(e)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(e)}
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
          Nuevo esquema
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={esquemas}
        getRowKey={(e) => e.id_esquema_comision}
        loading={isLoading}
        emptyMessage="Sin esquemas de comisión. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar esquema' : 'Nuevo esquema'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Vendedor"
              value={form.vendedor}
              onChange={(e) => setForm((f) => ({ ...f, vendedor: e.target.value }))}
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {vendedores.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Porcentaje base"
              value={form.porcentaje_base}
              onChange={(e) => setForm((f) => ({ ...f, porcentaje_base: e.target.value }))}
              inputMode="decimal"
              required
              helperText="Porcentaje sobre el subtotal sin impuestos (0–100)."
              fullWidth
            />
            <TextField
              label="Vigente desde"
              type="date"
              value={form.vigente_desde}
              onChange={(e) => setForm((f) => ({ ...f, vigente_desde: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Vigente hasta"
              type="date"
              value={form.vigente_hasta}
              onChange={(e) => setForm((f) => ({ ...f, vigente_hasta: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
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

      <Drawer
        anchor="right"
        open={Boolean(detalleEsquema)}
        onClose={() => setDetalleEsquema(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 560 }, p: 3 } } }}
      >
        {detalleEsquema && (
          <CategoriasEsquema
            esquema={detalleEsquema}
            categorias={categorias}
            onClose={() => setDetalleEsquema(null)}
          />
        )}
      </Drawer>
    </>
  );
};

// ── Drawer: overrides por categoría de un esquema (CRUD inline) ────────────────

interface CategoriasEsquemaProps {
  esquema: EsquemaComision;
  categorias: CategoriaProducto[];
  onClose: () => void;
}

interface CategoriaForm {
  categoria: string;
  porcentaje: string;
}

const CATEGORIA_VACIO: CategoriaForm = { categoria: '', porcentaje: '' };

const CategoriasEsquema: React.FC<CategoriasEsquemaProps> = ({ esquema, categorias, onClose }) => {
  const queryClient = useQueryClient();
  const esquemaId = esquema.id_esquema_comision;
  const [form, setForm] = useState<CategoriaForm>(CATEGORIA_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: overrides = [] } = useQuery({
    queryKey: comisionesKeys.categorias(esquemaId),
    queryFn: () => esquemasComisionCategoriaService.getAll({ esquema: esquemaId }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: comisionesKeys.categorias(esquemaId) });

  const nombreCategoria = (id: string) => {
    const c = categorias.find((cat) => cat.id_categoria_producto === id);
    return c ? c.nombre_categoria : id;
  };

  const reset = () => {
    setForm(CATEGORIA_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: { esquema: string; categoria: string; porcentaje: string }) =>
      editId
        ? esquemasComisionCategoriaService.update(editId, payload)
        : esquemasComisionCategoriaService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el override.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => esquemasComisionCategoriaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el override.')),
  });

  const editar = (o: EsquemaComisionCategoria) => {
    setEditId(o.id_esquema_comision_categoria);
    setForm({ categoria: o.categoria, porcentaje: o.porcentaje });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.categoria || !form.porcentaje.trim()) {
      setError('Seleccione una categoría e indique el porcentaje.');
      return;
    }
    guardar.mutate({
      esquema: esquemaId,
      categoria: form.categoria,
      porcentaje: form.porcentaje.trim(),
    });
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">
          Comisión por categoría — {esquema.vendedor_username || ''}
        </Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        % base del esquema: {esquema.porcentaje_base}%. Cada override reemplaza el base para los
        productos de su categoría.
      </Typography>

      <Divider />

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack spacing={1}>
        {overrides.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin overrides por categoría.
          </Typography>
        ) : (
          overrides.map((o) => (
            <Stack
              key={o.id_esquema_comision_categoria}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {o.categoria_nombre || nombreCategoria(o.categoria)} · {o.porcentaje}%
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(o)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(o.id_esquema_comision_categoria)}
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
          label="Categoría"
          value={form.categoria}
          onChange={(e) => setForm((f) => ({ ...f, categoria: e.target.value }))}
          size="small"
          fullWidth
        >
          {categorias.map((c) => (
            <MenuItem key={c.id_categoria_producto} value={c.id_categoria_producto}>
              {c.nombre_categoria}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label="Porcentaje"
          value={form.porcentaje}
          onChange={(e) => setForm((f) => ({ ...f, porcentaje: e.target.value }))}
          inputMode="decimal"
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <Button
            variant="contained"
            size="small"
            onClick={handleGuardar}
            disabled={guardar.isPending}
          >
            {editId ? 'Actualizar override' : 'Agregar override'}
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
// Tab 2 — Comisiones devengadas (read-only + filtros + resumen + liquidar)
// ─────────────────────────────────────────────────────────────────────────────

interface DevengadasSeccionProps {
  vendedores: Usuario[];
}

const DevengadasSeccion: React.FC<DevengadasSeccionProps> = ({ vendedores }) => {
  const queryClient = useQueryClient();
  const [vendedor, setVendedor] = useState('');
  const [estado, setEstado] = useState<EstadoComision | ''>('');
  const [liquidarOpen, setLiquidarOpen] = useState(false);
  const [liqVendedor, setLiqVendedor] = useState('');
  const [liqDesde, setLiqDesde] = useState('');
  const [liqHasta, setLiqHasta] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [okMsg, setOkMsg] = useState('');

  const filtros = { vendedor: vendedor || undefined, estado: estado || undefined };

  const { data: comisiones = [], isLoading } = useQuery({
    queryKey: comisionesKeys.devengadas(filtros),
    queryFn: () => comisionesService.getAll({ vendedor: vendedor || undefined, estado: estado || undefined }),
  });

  const { data: resumen } = useQuery({
    queryKey: comisionesKeys.resumen(filtros),
    queryFn: () => comisionesService.resumen({ vendedor: vendedor || undefined, estado: estado || undefined }),
  });

  const vendedorLabel = (id: string) => {
    const v = vendedores.find((u) => u.id === id);
    return v ? v.username : id;
  };

  const liquidar = useMutation({
    mutationFn: () =>
      comisionesService.liquidar({ vendedor: liqVendedor, desde: liqDesde, hasta: liqHasta }),
    onSuccess: (res) => {
      setLiquidarOpen(false);
      setOkMsg(
        `Se liquidaron ${res.liquidadas} comisiones por un total de ${res.monto_total}.`,
      );
      setErrorMsg('');
      queryClient.invalidateQueries({ queryKey: comisionesKeys.all() });
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudieron liquidar las comisiones.')),
  });

  const abrirLiquidar = () => {
    setLiqVendedor(vendedor || '');
    setLiqDesde('');
    setLiqHasta('');
    setErrorMsg('');
    setLiquidarOpen(true);
  };

  const handleLiquidar = () => {
    if (!liqVendedor || !liqDesde || !liqHasta) {
      setErrorMsg('Seleccione el vendedor y el período (desde y hasta).');
      return;
    }
    liquidar.mutate();
  };

  const columns: Column<ComisionVenta>[] = [
    {
      key: 'vendedor',
      header: 'Vendedor',
      render: (c) => c.vendedor_username || vendedorLabel(c.vendedor),
    },
    { key: 'numero_nota', header: 'Nota de venta', render: (c) => c.numero_nota || c.nota_venta },
    { key: 'base_comisionable', header: 'Base', render: (c) => c.base_comisionable },
    { key: 'monto', header: 'Monto', render: (c) => c.monto },
    {
      key: 'estado',
      header: 'Estado',
      render: (c) => <StatusChip value={c.estado} colorMap={ESTADO_COLOR} />,
    },
    { key: 'fecha_devengo', header: 'Devengo', render: (c) => c.fecha_devengo },
    { key: 'fecha_liquidacion', header: 'Liquidación', render: (c) => c.fecha_liquidacion || '—' },
  ];

  const filasResumen: ResumenComisionVendedor[] = resumen?.resultados ?? [];

  return (
    <>
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      {okMsg && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setOkMsg('')}>
          {okMsg}
        </Alert>
      )}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Vendedor"
          value={vendedor}
          onChange={(e) => setVendedor(e.target.value)}
          size="small"
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {vendedores.map((u) => (
            <MenuItem key={u.id} value={u.id}>
              {u.username}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Estado"
          value={estado}
          onChange={(e) => setEstado(e.target.value as EstadoComision | '')}
          size="small"
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADO_OPCIONES.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="contained" onClick={abrirLiquidar}>
          Liquidar
        </Button>
      </Stack>

      {filasResumen.length > 0 && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {filasResumen.map((r) => (
            <Grid key={r.vendedor} size={{ xs: 12, sm: 6, md: 4 }}>
              <KpiCard
                label={r.vendedor_username}
                value={r.devengada}
                tone="warning"
                caption={`Liquidada: ${r.liquidada} · ${r.cantidad} comisiones`}
              />
            </Grid>
          ))}
        </Grid>
      )}

      <DataTable
        columns={columns}
        rows={comisiones}
        getRowKey={(c) => c.id_comision_venta}
        loading={isLoading}
        emptyMessage="Sin comisiones devengadas para el filtro seleccionado."
      />

      <Dialog open={liquidarOpen} onClose={() => setLiquidarOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Liquidar comisiones</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Marca como LIQUIDADA las comisiones DEVENGADAS del vendedor en el período.
            </Typography>
            <TextField
              select
              label="Vendedor"
              value={liqVendedor}
              onChange={(e) => setLiqVendedor(e.target.value)}
              required
              fullWidth
            >
              <MenuItem value="">— Seleccione —</MenuItem>
              {vendedores.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {u.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Desde"
              type="date"
              value={liqDesde}
              onChange={(e) => setLiqDesde(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              required
              fullWidth
            />
            <TextField
              label="Hasta"
              type="date"
              value={liqHasta}
              onChange={(e) => setLiqHasta(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              required
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLiquidarOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleLiquidar} disabled={liquidar.isPending}>
            Liquidar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Página contenedora con tabs
// ─────────────────────────────────────────────────────────────────────────────

const ComisionesPage: React.FC = () => {
  const empresaId = getEmpresaId() || '';
  const [tab, setTab] = useState(0);

  const { data: vendedores = [] } = useQuery({
    queryKey: ['usuarios', empresaId],
    queryFn: () => fetchUsuarios(empresaId || undefined),
  });

  const { data: categorias = [] } = useQuery({
    queryKey: ['categorias-producto'],
    queryFn: () => categoriasProductoService.getAll(),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Comisiones de Ventas"
        subtitle="Esquemas de comisión por vendedor, comisiones devengadas y liquidación por período."
      />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Esquemas" />
        <Tab label="Comisiones devengadas" />
      </Tabs>

      {tab === 0 && <EsquemasSeccion vendedores={vendedores} categorias={categorias} />}
      {tab === 1 && <DevengadasSeccion vendedores={vendedores} />}
    </PageContainer>
  );
};

export default ComisionesPage;
