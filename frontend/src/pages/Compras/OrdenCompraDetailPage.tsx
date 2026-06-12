/**
 * Detalle de Orden de Compra (workstream F): líneas con subtotales Decimal,
 * estado y acciones del flujo de compras —
 *   aprobar OC → recepcionar mercancía (entrada de inventario + CxP) →
 *   registrar factura del proveedor sobre la recepción.
 *
 * Los 400/422 del backend (OC no aprobada, falta de mapeo contable, número de
 * factura duplicado…) se muestran en los diálogos sin romper el flujo.
 */
import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { comprasService } from '../../services/comprasService';
import { almacenesService } from '../../services/almacenesService';
import { fetchProductos, type Producto } from '../../services/productosService';
import {
  recepcionSchema,
  facturaCompraSchema,
  type RecepcionInput,
  type FacturaCompraInput,
} from '../../schemas/compras.schemas';
import { comprasKeys, cxpKeys, almacenesKeys, productosKeys } from '../../lib/queryKeys';
import { mensajeDeError, toList } from '../../utils/api';
import { D, sumDecimals, toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import type { DetalleOrdenCompra } from '../../services/comprasService';

export default function OrdenCompraDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const empresaId = getEmpresaId() || '';

  const [dialogoRecepcion, setDialogoRecepcion] = useState(false);
  const [dialogoFactura, setDialogoFactura] = useState(false);
  const [errorRecepcion, setErrorRecepcion] = useState('');
  const [errorFactura, setErrorFactura] = useState('');

  const { data: orden, isLoading: cargandoOrden } = useQuery({
    queryKey: comprasKeys.orden(id),
    queryFn: () => comprasService.getOrden(id),
    enabled: !!id,
  });

  const { data: detalles = [], isLoading: cargandoDetalles } = useQuery({
    queryKey: comprasKeys.detalles(id),
    queryFn: () => comprasService.getDetallesOrden(id),
    enabled: !!id,
  });

  const { data: recepciones = [] } = useQuery({
    queryKey: comprasKeys.recepciones(id),
    queryFn: () => comprasService.getRecepcionesOrden(id),
    enabled: !!id,
  });

  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
    enabled: dialogoRecepcion,
  });

  const { data: productosRaw } = useQuery({
    queryKey: productosKeys.porEmpresa(empresaId),
    queryFn: () => fetchProductos(empresaId),
    enabled: !!empresaId,
  });
  const nombreProducto = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const p of toList<Producto>(productosRaw)) mapa.set(p.id_producto, p.nombre_producto);
    return (idProducto: string) => mapa.get(idProducto) ?? idProducto.slice(0, 8);
  }, [productosRaw]);

  // Total de la OC sumando subtotales con decimal.js (R-CODE-4).
  const total = useMemo(() => sumDecimals(detalles.map((d) => d.subtotal)), [detalles]);

  const formRecepcion = useForm<RecepcionInput>({
    resolver: zodResolver(recepcionSchema),
    defaultValues: { almacen_id: '', items: [] },
  });
  const itemsArray = useFieldArray({ control: formRecepcion.control, name: 'items' });

  const formFactura = useForm<FacturaCompraInput>({
    resolver: zodResolver(facturaCompraSchema),
    defaultValues: { recepcion_id: '', numero_factura: '', fecha_emision: '' },
  });

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: comprasKeys.ordenesAll() });
    // La recepción/factura crean o actualizan CxP.
    void queryClient.invalidateQueries({ queryKey: cxpKeys.cuentasAll() });
    void queryClient.invalidateQueries({ queryKey: cxpKeys.agingAll() });
  };

  const aprobarMutation = useMutation({
    mutationFn: () => comprasService.aprobarOrden(id),
    onSuccess: () => {
      snackbar.success(t('compras.detalle.aprobada'));
      invalidar();
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, t('compras.detalle.errorAprobar')));
    },
  });

  const recepcionMutation = useMutation({
    mutationFn: (input: RecepcionInput) =>
      comprasService.recepcionar({
        orden_compra_id: id,
        almacen_id: input.almacen_id,
        items: input.items.map((it) => ({
          producto_id: it.producto_id,
          cantidad: it.cantidad,
          costo_unitario: it.costo_unitario,
        })),
      }),
    onSuccess: (res) => {
      snackbar.success(t('compras.detalle.recepcionOk', { monto: toFixedStr(res.monto_total) }));
      cerrarRecepcion();
      invalidar();
    },
    onError: (err: unknown) => {
      // 400 del backend: OC no aprobada, producto inválido, falta mapeo contable…
      setErrorRecepcion(mensajeDeError(err, t('compras.detalle.errorRecepcion')));
    },
  });

  const facturaMutation = useMutation({
    mutationFn: (input: FacturaCompraInput) =>
      comprasService.facturar({
        recepcion_id: input.recepcion_id,
        numero_factura: input.numero_factura,
        ...(input.fecha_emision ? { fecha_emision: input.fecha_emision } : {}),
      }),
    onSuccess: (res) => {
      snackbar.success(t('compras.detalle.facturaOk', { numero: res.numero_factura }));
      cerrarFactura();
      invalidar();
    },
    onError: (err: unknown) => {
      // 400 del backend: número duplicado, recepción ya facturada, mapeo contable…
      setErrorFactura(mensajeDeError(err, t('compras.detalle.errorFactura')));
    },
  });

  function abrirRecepcion() {
    setErrorRecepcion('');
    // Prefill: una fila por línea de la OC (cantidad y costo editables).
    formRecepcion.reset({
      almacen_id: '',
      items: detalles.map((d) => ({
        producto_id: d.id_producto,
        cantidad: d.cantidad,
        costo_unitario: d.precio_unitario,
      })),
    });
    setDialogoRecepcion(true);
  }

  function cerrarRecepcion() {
    setDialogoRecepcion(false);
    setErrorRecepcion('');
  }

  function abrirFactura() {
    setErrorFactura('');
    formFactura.reset({
      recepcion_id: recepciones[0]?.id_recepcion ?? '',
      numero_factura: '',
      fecha_emision: '',
    });
    setDialogoFactura(true);
  }

  function cerrarFactura() {
    setDialogoFactura(false);
    setErrorFactura('');
  }

  const columns: Column<DetalleOrdenCompra>[] = [
    { key: 'producto', header: t('compras.form.producto'), render: (d) => nombreProducto(d.id_producto) },
    { key: 'cantidad', header: t('compras.form.cantidad'), align: 'right', render: (d) => toFixedStr(d.cantidad) },
    {
      key: 'precio',
      header: t('compras.form.precioUnitario'),
      align: 'right',
      render: (d) => toFixedStr(d.precio_unitario),
    },
    {
      key: 'subtotal',
      header: t('compras.form.subtotal'),
      align: 'right',
      render: (d) => (
        <Typography component="span" fontWeight={600} sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {toFixedStr(d.subtotal)}
        </Typography>
      ),
    },
  ];

  if (cargandoOrden) {
    return (
      <PageContainer>
        <Stack alignItems="center" sx={{ py: 8 }}>
          <CircularProgress />
        </Stack>
      </PageContainer>
    );
  }

  const puedeAprobar = orden?.estado === 'BORRADOR' || orden?.estado === 'ENVIADA';
  const puedeRecepcionar = orden?.estado === 'APROBADA';

  return (
    <PageContainer>
      <PageHeader
        title={`${t('compras.detalle.title')} ${orden?.numero_orden ?? ''}`}
        subtitle={orden ? `${t('compras.ordenes.fecha')}: ${orden.fecha_orden}` : undefined}
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate('/compras/ordenes')}>
              {t('common.back')}
            </Button>
            <Button
              variant="contained"
              onClick={() => aprobarMutation.mutate()}
              disabled={!puedeAprobar || aprobarMutation.isPending}
            >
              {t('compras.detalle.aprobar')}
            </Button>
            <Button variant="contained" color="secondary" onClick={abrirRecepcion} disabled={!puedeRecepcionar}>
              {t('compras.detalle.recepcionar')}
            </Button>
            <Button
              variant="contained"
              color="success"
              onClick={abrirFactura}
              disabled={recepciones.length === 0}
            >
              {t('compras.detalle.registrarFactura')}
            </Button>
          </>
        }
      />

      {orden && (
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('compras.ordenes.estado')}:
          </Typography>
          <StatusChip value={orden.estado} />
          {orden.observaciones && (
            <Typography variant="body2" color="text.secondary">
              · {orden.observaciones}
            </Typography>
          )}
        </Stack>
      )}

      <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('compras.form.lineas')}
        </Typography>
        <DataTable
          columns={columns}
          rows={detalles}
          getRowKey={(d) => d.id_detalle_orden_compra}
          loading={cargandoDetalles}
          emptyMessage={t('compras.detalle.sinLineas')}
        />
        <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2 }}>
          <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {`${t('compras.form.total')}: ${toFixedStr(total)}`}
          </Typography>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('compras.detalle.recepciones')}
        </Typography>
        {recepciones.length === 0 ? (
          <Alert severity="info">{t('compras.detalle.sinRecepciones')}</Alert>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('compras.detalle.fechaRecepcion')}</TableCell>
                <TableCell align="right">{t('compras.detalle.montoTotal')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {recepciones.map((r) => (
                <TableRow key={r.id_recepcion}>
                  <TableCell>{r.fecha_recepcion}</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {toFixedStr(r.monto_total)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* ── Diálogo: recepción de mercancía ────────────────────────────────── */}
      <Dialog open={dialogoRecepcion} onClose={cerrarRecepcion} fullWidth maxWidth="md">
        <DialogTitle>{t('compras.detalle.recepcionar')}</DialogTitle>
        <form
          onSubmit={formRecepcion.handleSubmit((input) => {
            setErrorRecepcion('');
            recepcionMutation.mutate(input);
          })}
          noValidate
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorRecepcion && <Alert severity="error">{errorRecepcion}</Alert>}
              <TextField
                select
                label={t('compras.detalle.almacen')}
                defaultValue=""
                fullWidth
                required
                error={!!formRecepcion.formState.errors.almacen_id}
                helperText={formRecepcion.formState.errors.almacen_id?.message}
                {...formRecepcion.register('almacen_id')}
              >
                {almacenes.map((a) => (
                  <MenuItem key={a.id_almacen} value={a.id_almacen}>
                    {a.nombre_almacen}
                  </MenuItem>
                ))}
              </TextField>
              {itemsArray.fields.length === 0 && (
                <Alert severity="warning">{t('compras.detalle.sinLineas')}</Alert>
              )}
              {itemsArray.fields.map((field, idx) => {
                // eslint-disable-next-line security/detect-object-injection -- FP: `idx` es el índice entero que emite fields.map (array de RHF), no una clave arbitraria
                const erroresItem = formRecepcion.formState.errors.items?.[idx];
                return (
                <Stack key={field.id} direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
                  <Typography variant="body2" sx={{ minWidth: 180 }}>
                    {nombreProducto(field.producto_id)}
                  </Typography>
                  <TextField
                    size="small"
                    inputMode="decimal"
                    label={t('compras.detalle.cantidadRecibida')}
                    error={!!erroresItem?.cantidad}
                    helperText={erroresItem?.cantidad?.message}
                    {...formRecepcion.register(`items.${idx}.cantidad`)}
                  />
                  <TextField
                    size="small"
                    inputMode="decimal"
                    label={t('compras.detalle.costoUnitario')}
                    error={!!erroresItem?.costo_unitario}
                    helperText={erroresItem?.costo_unitario?.message}
                    {...formRecepcion.register(`items.${idx}.costo_unitario`)}
                  />
                </Stack>
                );
              })}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarRecepcion} disabled={recepcionMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" variant="contained" disabled={recepcionMutation.isPending}>
              {t('compras.detalle.confirmarRecepcion')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* ── Diálogo: factura del proveedor ─────────────────────────────────── */}
      <Dialog open={dialogoFactura} onClose={cerrarFactura} fullWidth maxWidth="sm">
        <DialogTitle>{t('compras.detalle.registrarFactura')}</DialogTitle>
        <form
          onSubmit={formFactura.handleSubmit((input) => {
            setErrorFactura('');
            facturaMutation.mutate(input);
          })}
          noValidate
        >
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              {errorFactura && <Alert severity="error">{errorFactura}</Alert>}
              <TextField
                select
                label={t('compras.detalle.recepcion')}
                defaultValue={recepciones[0]?.id_recepcion ?? ''}
                fullWidth
                required
                error={!!formFactura.formState.errors.recepcion_id}
                helperText={formFactura.formState.errors.recepcion_id?.message}
                {...formFactura.register('recepcion_id')}
              >
                {recepciones.map((r) => (
                  <MenuItem key={r.id_recepcion} value={r.id_recepcion}>
                    {r.fecha_recepcion} — {toFixedStr(D(r.monto_total))}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label={t('compras.detalle.numeroFactura')}
                fullWidth
                required
                error={!!formFactura.formState.errors.numero_factura}
                helperText={formFactura.formState.errors.numero_factura?.message}
                {...formFactura.register('numero_factura')}
              />
              <TextField
                label={t('compras.detalle.fechaEmision')}
                type="date"
                fullWidth
                InputLabelProps={{ shrink: true }}
                error={!!formFactura.formState.errors.fecha_emision}
                helperText={formFactura.formState.errors.fecha_emision?.message}
                {...formFactura.register('fecha_emision')}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarFactura} disabled={facturaMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" variant="contained" color="success" disabled={facturaMutation.isPending}>
              {t('compras.detalle.confirmarFactura')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
