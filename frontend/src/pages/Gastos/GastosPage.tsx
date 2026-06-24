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
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  gastosService,
  categoriasGastoService,
  detalleGastoService,
  type Gasto,
  type GastoPayload,
  type EstadoGasto,
  type CategoriaGasto,
  type DetalleGasto,
  type DetalleGastoPayload,
} from '../../services/gastosService';
import { fetchMonedas } from '../../services/monedas';
import { contabilidadService, type CuentaContable } from '../../services/contabilidadService';
import { gastosKeys, finanzasKeys, contabilidadKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const ESTADOS: { value: EstadoGasto | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'PENDIENTE_APROBACION', label: 'Pendiente de aprobación' },
  { value: 'APROBADO', label: 'Aprobado' },
  { value: 'RECHAZADO', label: 'Rechazado' },
  { value: 'REEMBOLSADO', label: 'Reembolsado' },
  { value: 'CONTABILIZADO', label: 'Contabilizado' },
];

const ESTADO_COLOR: Record<string, 'warning' | 'success' | 'error' | 'info' | 'default'> = {
  pendiente_aprobacion: 'warning',
  aprobado: 'success',
  rechazado: 'error',
  reembolsado: 'info',
  contabilizado: 'default',
};

const hoy = () => new Date().toISOString().slice(0, 10);

interface FormState {
  fecha_gasto: string;
  descripcion: string;
  monto: string;
  monto_iva: string;
  id_moneda: string;
  id_categoria_gasto: string;
  tiene_factura: boolean;
  numero_factura: string;
}

const formVacio = (): FormState => ({
  fecha_gasto: hoy(),
  descripcion: '',
  monto: '',
  monto_iva: '0',
  id_moneda: '',
  id_categoria_gasto: '',
  tiene_factura: false,
  numero_factura: '',
});

const GastosPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState<EstadoGasto | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<Gasto | null>(null);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<Gasto | null>(null);

  const { data: gastos = [], isLoading } = useQuery({
    queryKey: gastosKeys.gastos(empresaId, filtroEstado),
    queryFn: () =>
      gastosService.getAll({
        empresa: empresaId || undefined,
        estado: filtroEstado || undefined,
      }),
  });

  const { data: categorias = [] } = useQuery<CategoriaGasto[]>({
    queryKey: gastosKeys.categoriasActivas(),
    queryFn: () => categoriasGastoService.activas(),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: fetchMonedas,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: gastosKeys.gastosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (g: Gasto) => {
    setEditando(g);
    setForm({
      fecha_gasto: g.fecha_gasto,
      descripcion: g.descripcion,
      monto: g.monto,
      monto_iva: g.monto_iva ?? '0',
      id_moneda: g.id_moneda,
      id_categoria_gasto: g.id_categoria_gasto,
      tiene_factura: g.tiene_factura ?? false,
      numero_factura: g.numero_factura ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: GastoPayload) =>
      editando ? gastosService.update(editando.id_gasto, payload) : gastosService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el gasto.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => gastosService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el gasto.')),
  });

  const aprobar = useMutation({
    mutationFn: (id: string) => gastosService.aprobar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo aprobar el gasto.')),
  });

  const rechazar = useMutation({
    mutationFn: (id: string) => gastosService.rechazar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo rechazar el gasto.')),
  });

  const handleGuardar = () => {
    if (!form.descripcion.trim() || !form.monto.trim() || !form.id_categoria_gasto || !form.id_moneda) {
      setErrorMsg('Complete categoría, moneda, descripción y monto.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      fecha_gasto: form.fecha_gasto,
      descripcion: form.descripcion.trim(),
      monto: form.monto.trim(),
      monto_iva: form.monto_iva.trim() || '0',
      id_moneda: form.id_moneda,
      id_categoria_gasto: form.id_categoria_gasto,
      id_proveedor: null,
      tiene_factura: form.tiene_factura,
      numero_factura: form.numero_factura.trim() || null,
    });
  };

  const handleEliminar = (g: Gasto) => {
    if (window.confirm(`¿Eliminar el gasto "${g.descripcion.slice(0, 40)}"?`)) {
      eliminar.mutate(g.id_gasto);
    }
  };

  const handleAprobar = (g: Gasto) => {
    if (window.confirm('¿Aprobar este gasto? Se generará su asiento contable.')) {
      aprobar.mutate(g.id_gasto);
    }
  };

  const handleRechazar = (g: Gasto) => {
    if (window.confirm('¿Rechazar este gasto?')) {
      rechazar.mutate(g.id_gasto);
    }
  };

  const nombreCategoria = (id: string) =>
    categorias.find((c) => c.id_categoria_gasto === id)?.nombre_categoria ?? '—';

  const columns: Column<Gasto>[] = [
    { key: 'fecha_gasto', header: 'Fecha', render: (g) => g.fecha_gasto },
    { key: 'descripcion', header: 'Descripción', render: (g) => g.descripcion },
    {
      key: 'id_categoria_gasto',
      header: 'Categoría',
      render: (g) => nombreCategoria(g.id_categoria_gasto),
    },
    { key: 'monto', header: 'Monto', render: (g) => g.monto },
    { key: 'monto_iva', header: 'IVA', render: (g) => g.monto_iva ?? '0' },
    {
      key: 'estado_gasto',
      header: 'Estado',
      render: (g) => (
        <StatusChip
          value={g.estado_gasto}
          label={g.estado_gasto_display ?? g.estado_gasto}
          colorMap={ESTADO_COLOR}
        />
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (g) => {
        const pendiente = g.estado_gasto === 'PENDIENTE_APROBACION';
        return (
          <Stack direction="row" spacing={1}>
            <Button size="small" onClick={() => setDetalle(g)}>
              Detalle
            </Button>
            <Button size="small" onClick={() => abrirEditar(g)}>
              Editar
            </Button>
            <Button
              size="small"
              color="success"
              disabled={!pendiente || aprobar.isPending}
              onClick={() => handleAprobar(g)}
            >
              Aprobar
            </Button>
            <Button
              size="small"
              color="warning"
              disabled={!pendiente || rechazar.isPending}
              onClick={() => handleRechazar(g)}
            >
              Rechazar
            </Button>
            <Button
              size="small"
              color="error"
              disabled={eliminar.isPending}
              onClick={() => handleEliminar(g)}
            >
              Eliminar
            </Button>
          </Stack>
        );
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Gastos"
        subtitle="Registro de gastos con flujo de aprobación y generación de asiento contable."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo gasto
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <TextField
        select
        label="Estado"
        value={filtroEstado}
        onChange={(e) => setFiltroEstado(e.target.value as EstadoGasto | '')}
        size="small"
        sx={{ mb: 2, minWidth: 260 }}
      >
        {ESTADOS.map((e) => (
          <MenuItem key={e.value || 'todos'} value={e.value}>
            {e.label}
          </MenuItem>
        ))}
      </TextField>

      <DataTable
        columns={columns}
        rows={gastos}
        getRowKey={(g) => g.id_gasto}
        loading={isLoading}
        emptyMessage="Sin gastos. Registra el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar gasto' : 'Nuevo gasto'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Categoría"
              value={form.id_categoria_gasto}
              onChange={(e) => setForm((f) => ({ ...f, id_categoria_gasto: e.target.value }))}
              required
              fullWidth
            >
              {categorias.map((c) => (
                <MenuItem key={c.id_categoria_gasto} value={c.id_categoria_gasto}>
                  {c.nombre_categoria}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha del gasto"
              type="date"
              value={form.fecha_gasto}
              onChange={(e) => setForm((f) => ({ ...f, fecha_gasto: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
              required
              multiline
              minRows={2}
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Monto"
                value={form.monto}
                onChange={(e) => setForm((f) => ({ ...f, monto: e.target.value }))}
                required
                fullWidth
              />
              <TextField
                label="IVA"
                value={form.monto_iva}
                onChange={(e) => setForm((f) => ({ ...f, monto_iva: e.target.value }))}
                fullWidth
              />
            </Stack>
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
                  checked={form.tiene_factura}
                  onChange={(e) => setForm((f) => ({ ...f, tiene_factura: e.target.checked }))}
                />
              }
              label="Tiene factura de respaldo"
            />
            {form.tiene_factura && (
              <TextField
                label="Número de factura"
                value={form.numero_factura}
                onChange={(e) => setForm((f) => ({ ...f, numero_factura: e.target.value }))}
                fullWidth
              />
            )}
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
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 560 }, p: 3 } } }}
      >
        {detalle && <DetalleGastoDrawer gasto={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle del gasto (líneas de imputación contable, CRUD inline) ────────────

interface DetalleGastoDrawerProps {
  gasto: Gasto;
  onClose: () => void;
}

const DetalleGastoDrawer: React.FC<DetalleGastoDrawerProps> = ({ gasto, onClose }) => (
  <Stack spacing={2}>
    <Stack direction="row" alignItems="center" justifyContent="space-between">
      <Typography variant="h6">Gasto</Typography>
      <IconButton onClick={onClose} aria-label="Cerrar detalle">
        <CloseOutlined />
      </IconButton>
    </Stack>
    <Typography variant="body2" color="text.secondary">
      {gasto.descripcion}
    </Typography>
    <Typography variant="body2">
      {gasto.fecha_gasto} · Monto {gasto.monto} · IVA {gasto.monto_iva ?? '0'} ·{' '}
      {gasto.estado_gasto_display ?? gasto.estado_gasto}
    </Typography>

    <Divider />

    <DetallesGasto gastoId={gasto.id_gasto} bloqueado={gasto.estado_gasto !== 'PENDIENTE_APROBACION'} />
  </Stack>
);

interface DetalleForm {
  id_cuenta_contable: string;
  descripcion: string;
  monto: string;
  monto_iva: string;
}

const DETALLE_VACIO: DetalleForm = {
  id_cuenta_contable: '',
  descripcion: '',
  monto: '',
  monto_iva: '0',
};

const DetallesGasto: React.FC<{ gastoId: string; bloqueado: boolean }> = ({
  gastoId,
  bloqueado,
}) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<DetalleForm>(DETALLE_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: detalles = [] } = useQuery({
    queryKey: gastosKeys.detalles(gastoId),
    queryFn: () => detalleGastoService.getAll({ gasto: gastoId }),
  });

  const { data: cuentas = [] } = useQuery<CuentaContable[]>({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: contabilidadService.getPlanCuentas,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: gastosKeys.detalles(gastoId) });

  const reset = () => {
    setForm(DETALLE_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: DetalleGastoPayload) =>
      editId ? detalleGastoService.update(editId, payload) : detalleGastoService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar la línea.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => detalleGastoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar la línea.')),
  });

  const editar = (d: DetalleGasto) => {
    setEditId(d.id_detalle_gasto);
    setForm({
      id_cuenta_contable: d.id_cuenta_contable,
      descripcion: d.descripcion ?? '',
      monto: d.monto,
      monto_iva: d.monto_iva ?? '0',
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_cuenta_contable || !form.monto.trim()) {
      setError('Seleccione la cuenta contable e indique el monto.');
      return;
    }
    guardar.mutate({
      id_gasto: gastoId,
      id_cuenta_contable: form.id_cuenta_contable,
      descripcion: form.descripcion.trim() || null,
      monto: form.monto.trim(),
      monto_iva: form.monto_iva.trim() || '0',
    });
  };

  const nombreCuenta = (id: string) => {
    const cta = cuentas.find((c) => c.id_cuenta_contable === id);
    return cta ? `${cta.codigo_cuenta} — ${cta.nombre_cuenta}` : id;
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Líneas de imputación contable
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Stack spacing={1} sx={{ mb: 2 }}>
        {detalles.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin líneas. Si no agregas ninguna, se imputa a la cuenta de la categoría.
          </Typography>
        ) : (
          detalles.map((d) => (
            <Stack
              key={d.id_detalle_gasto}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {nombreCuenta(d.id_cuenta_contable)} · {d.monto}
                {d.monto_iva && d.monto_iva !== '0' ? ` (IVA ${d.monto_iva})` : ''}
              </Typography>
              {!bloqueado && (
                <Stack direction="row" spacing={0.5}>
                  <Button size="small" onClick={() => editar(d)}>
                    Editar
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    disabled={eliminar.isPending}
                    onClick={() => eliminar.mutate(d.id_detalle_gasto)}
                  >
                    Eliminar
                  </Button>
                </Stack>
              )}
            </Stack>
          ))
        )}
      </Stack>
      {bloqueado ? (
        <Typography variant="caption" color="text.secondary">
          El gasto ya no está pendiente: sus líneas no se pueden modificar.
        </Typography>
      ) : (
        <Stack spacing={1}>
          <TextField
            select
            label="Cuenta contable"
            value={form.id_cuenta_contable}
            onChange={(e) => setForm((f) => ({ ...f, id_cuenta_contable: e.target.value }))}
            size="small"
            fullWidth
          >
            {cuentas.map((c) => (
              <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                {c.codigo_cuenta} — {c.nombre_cuenta}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Descripción"
            value={form.descripcion}
            onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
            size="small"
            fullWidth
          />
          <Stack direction="row" spacing={1}>
            <TextField
              label="Monto"
              value={form.monto}
              onChange={(e) => setForm((f) => ({ ...f, monto: e.target.value }))}
              size="small"
              fullWidth
            />
            <TextField
              label="IVA"
              value={form.monto_iva}
              onChange={(e) => setForm((f) => ({ ...f, monto_iva: e.target.value }))}
              size="small"
              fullWidth
            />
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              size="small"
              onClick={handleGuardar}
              disabled={guardar.isPending}
            >
              {editId ? 'Actualizar línea' : 'Agregar línea'}
            </Button>
            {editId && (
              <Button size="small" onClick={reset}>
                Cancelar
              </Button>
            )}
          </Stack>
        </Stack>
      )}
    </Box>
  );
};

export default GastosPage;
