import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get } from '../../../services/api';
import { pagosService } from '../../../services/pagosService';
import { pedidoService } from '../../../services/ventas';
import { almacenesService } from '../../../services/almacenesService';
import { useParams, useNavigate } from 'react-router-dom';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import type { PedidoDetalleForm } from '../../../components/Pedidos/TablaProductos';
import LineasProductoTabla from '../../../components/Pedidos/LineasProductoTabla';
import type { ColumnDef } from '../../../hooks/useColumnVisibility';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import { D } from '../../../lib/decimal';
import { fetchProductos } from '../../../services/productosService';
import { mensajeDeError, toList } from '../../../utils/api';
import { almacenesKeys, cxcKeys, inventarioKeys, pagosKeys, pedidosKeys } from '../../../lib/queryKeys';
import { useSnackbar } from '../../../contexts/feedbackTypes';

type ProductoItem = React.ComponentProps<typeof TablaProductos>['productos'][number];
import {
  Alert,
  Box,
  Button,
  Card,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  TextField,
  Typography,
} from '@mui/material';
import ModalPago from '../../../components/Pedidos/ModalPago';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import type { Pago as PagoFinanzas } from '../../../services/pagosService';
import { PageContainer, PageHeader, SectionTitle, StatusChip } from '../../../components/ui';

interface PedidoDetalle {
  id_detalle_pedido: string;
  id_producto: { id_producto?: string; nombre_producto: string };
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  observaciones?: string;
}

interface Pedido {
  id_pedido: string;
  numero_pedido: string;
  fecha_pedido: string;
  estado: string;
  id_empresa: { id_empresa: string; nombre: string };
  id_sucursal?: { id_sucursal: string; nombre: string };
  id_caja?: { id_caja: string; nombre: string };
  id_usuario?: { id: number; username: string; first_name: string; last_name: string };
  id_cliente: { nombre: string };
  observaciones?: string;
  detalles: PedidoDetalle[];
  // pagos será cargado desde la nueva API
}

/** Columnas configurables (estilo Odoo) para las líneas del documento. */
const LINE_COLUMNS: ColumnDef<PedidoDetalle>[] = [
  {
    key: 'codigo',
    label: 'Código',
    defaultVisible: false,
    render: (d) => (typeof d.id_producto === 'object' && d.id_producto?.id_producto) || '—',
  },
  {
    key: 'producto',
    label: 'Producto',
    always: true,
    render: (d) => (typeof d.id_producto === 'object' && d.id_producto ? d.id_producto.nombre_producto : '—'),
  },
  { key: 'cantidad', label: 'Cantidad', align: 'right', defaultVisible: true, render: (d) => D(d.cantidad).toNumber() },
  {
    key: 'precio',
    label: 'Precio unit.',
    align: 'right',
    defaultVisible: true,
    render: (d) => D(d.precio_unitario).toFixed(2),
  },
  { key: 'observaciones', label: 'Comentarios', defaultVisible: false, render: (d) => d.observaciones || '—' },
  {
    key: 'subtotal',
    label: 'Subtotal',
    align: 'right',
    always: true,
    render: (d) => D(d.subtotal || '0').toFixed(2),
  },
];

const PedidoDetailPage: React.FC = () => {
  const { id_pedido } = useParams();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  // Catálogo de productos de la empresa (precargado para acciones futuras de edición).
  const [, setProductos] = useState<ProductoItem[]>([]);
  const [descuentoGeneral, setDescuentoGeneral] = useState<string>('');
  const [showPagoModal, setShowPagoModal] = useState(false);
  const [pagoSuccess, setPagoSuccess] = useState('');
  const [pagoError, setPagoError] = useState('');
  // Confirmación de pedido (gap E2E PR #76: no existía botón en la UI)
  const [showConfirmarDialog, setShowConfirmarDialog] = useState(false);
  const [almacenSeleccionado, setAlmacenSeleccionado] = useState('');
  const [confirmarError, setConfirmarError] = useState('');
  const navigate = useNavigate();

  const { data: pedido = null, isLoading: loading } = useQuery<Pedido | null>({
    queryKey: pedidosKeys.detail(id_pedido ?? ''),
    queryFn: async () => (await get(`/ventas/pedidos/${id_pedido}/`)) as Pedido,
    enabled: !!id_pedido,
  });

  const { data: pagos = [] } = useQuery<PagoFinanzas[]>({
    queryKey: pagosKeys.porDocumento('PEDIDO', id_pedido ?? ''),
    queryFn: () => pagosService.getPagosPedido(id_pedido!),
    enabled: !!id_pedido,
  });

  const { data: almacenes = [], isLoading: almacenesLoading } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
    enabled: showConfirmarDialog,
  });

  const almacenesEmpresa = almacenes.filter(
    (a) => !pedido?.id_empresa?.id_empresa || a.id_empresa === pedido.id_empresa.id_empresa,
  );

  const confirmarMutation = useMutation({
    mutationFn: () => pedidoService.confirmar(id_pedido!, almacenSeleccionado),
    onSuccess: (res) => {
      setShowConfirmarDialog(false);
      setConfirmarError('');
      snackbar.success(
        `Pedido ${res.numero_pedido} confirmado: ${res.reservas_creadas} reserva(s) de stock` +
          (res.cxc_generada ? ' y cuenta por cobrar generada' : ''),
      );
      // El estado del pedido, el stock comprometido y la cartera CxC cambian.
      queryClient.invalidateQueries({ queryKey: pedidosKeys.all() });
      queryClient.invalidateQueries({ queryKey: inventarioKeys.stockActualAll() });
      queryClient.invalidateQueries({ queryKey: cxcKeys.carteraAll() });
    },
    onError: (err: unknown) => {
      setConfirmarError(mensajeDeError(err, 'Error al confirmar el pedido.'));
    },
  });

  const puedeConfirmar = pedido?.estado === 'PENDIENTE' || pedido?.estado === 'ENVIADO';

  useEffect(() => {
    if (pedido?.id_empresa && pedido.id_empresa.id_empresa) {
      fetchProductos(pedido.id_empresa.id_empresa)
        .then((res) => {
          setProductos(toList<ProductoItem>(res));
        })
        .catch(() => setProductos([]));
    }
  }, [pedido?.id_empresa]);

  function mapDetalles(detalles: PedidoDetalle[]): PedidoDetalleForm[] {
    return detalles.map(det => ({
      id_producto: typeof det.id_producto === 'object' && det.id_producto ? (det.id_producto.id_producto ?? '') : '',
      sku: '',
      producto: typeof det.id_producto === 'object' && det.id_producto ? det.id_producto.nombre_producto : '',
      cantidad: det.cantidad,
      precio_unitario: det.precio_unitario,
      descuento_porcentaje: '0',
      comentarios: det.observaciones || '',
      subtotal: det.subtotal || '',
    }));
  }

  function getClienteInfo(cliente?: { razon_social?: string; nombre?: string; rif?: string; telefono?: string }): string {
    if (!cliente) return '-';
    const nombre = cliente.razon_social || cliente.nombre || '-';
    const rif = cliente.rif ? ` | RIF: ${cliente.rif}` : '';
    const telefono = cliente.telefono ? ` | Tel: ${cliente.telefono}` : '';
    return `${nombre}${rif}${telefono}`;
  }

  const handleConfirmPago = async (pagos: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    if (!id_pedido || !pedido) return;

    setPagoError('');
    setPagoSuccess('');

    try {
      // Procesar notas de crédito si fueron seleccionadas
      if (notasCreditoUtilizadas && notasCreditoUtilizadas.length > 0) {
        await pagosService.conciliarNotasCredito(notasCreditoUtilizadas, id_pedido, 'PEDIDO');
      }

      // Enviar los pagos al backend usando la nueva API unificada
      for (const pago of pagos) {
        await pagosService.createPagoDocumento('PEDIDO', id_pedido, {
          monto: pago.monto,
          id_metodo_pago: pago.id_metodo_pago,
          id_moneda: pago.id_moneda,
          tasa: pago.tasa,
          referencia: pago.referencia,
          observaciones: pago.observaciones,
          id_caja_fisica: pago.id_caja_fisica,
          id_caja_virtual: pago.id_caja_virtual,
          id_cuenta_bancaria: pago.id_cuenta_bancaria,
          id_datafono: pago.id_datafono,
          banco_destino: pago.banco_destino,
        });
      }

      // Procesar vueltos creando movimientos de caja/banco
      if (vueltos && vueltos.length > 0) {
        await pagosService.procesarVueltos(vueltos);
      }

      setPagoSuccess('Pagos registrados exitosamente.');
      setShowPagoModal(false);

      // Recargar los pagos para mostrar los nuevos
      queryClient.invalidateQueries({ queryKey: pagosKeys.porDocumento('PEDIDO', id_pedido) });

      // Limpiar mensaje de éxito después de 3 segundos
      setTimeout(() => setPagoSuccess(''), 3000);
    } catch {
      setPagoError('Error al registrar los pagos. Intente nuevamente.');
    }
  };

  const calcularTotalPedido = () => {
    if (!pedido?.detalles) return 0;
    return pedido.detalles.reduce((total, detalle) => {
      return total + (Number(detalle.precio_unitario) * Number(detalle.cantidad));
    }, 0);
  };

  return (
    <PageContainer>
      {loading ? (
        <Typography>Cargando...</Typography>
      ) : !pedido ? (
        <Typography>No se encontró el pedido.</Typography>
      ) : (
        <>
          <PageHeader
            title={`Pedido ${pedido.numero_pedido}`}
            subtitle={`${pedido.fecha_pedido} · ${pedido.id_empresa?.nombre || ''}`}
            actions={
              <Box sx={{ display: 'flex', gap: 1 }}>
                {puedeConfirmar && (
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={() => {
                      setConfirmarError('');
                      setShowConfirmarDialog(true);
                    }}
                  >
                    Confirmar pedido
                  </Button>
                )}
                <Button variant="outlined" color="secondary" onClick={() => navigate(-1)}>Volver</Button>
              </Box>
            }
          />
          <Card sx={{ p: 3, mb: 2 }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Fecha</Typography>
                <Typography variant="body1">{pedido.fecha_pedido}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Estado</Typography>
                <StatusChip value={pedido.estado} />
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Empresa</Typography>
                <Typography variant="body1">{pedido.id_empresa?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Sucursal</Typography>
                <Typography variant="body1">{pedido.id_sucursal?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Caja</Typography>
                <Typography variant="body1">{pedido.id_caja?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Usuario</Typography>
                <Typography variant="body1">{pedido.id_usuario ? (pedido.id_usuario.first_name && pedido.id_usuario.last_name ? `${pedido.id_usuario.first_name} ${pedido.id_usuario.last_name}` : pedido.id_usuario.username) : '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Cliente</Typography>
                <Typography variant="body1">{getClienteInfo(pedido.id_cliente)}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 100%' }}>
                <Typography variant="body2" color="text.secondary">Observaciones</Typography>
                <Typography variant="body1">{pedido.observaciones || '-'}</Typography>
              </Box>
            </Box>
          </Card>

          <Card sx={{ p: 3, mb: 2 }}>
            <SectionTitle>Detalles</SectionTitle>
            {pedido.detalles && pedido.detalles.length > 0 ? (
              <>
                <LineasProductoTabla
                  rows={pedido.detalles}
                  columns={LINE_COLUMNS}
                  storageKey="pedido"
                  getRowKey={(d) => d.id_detalle_pedido}
                />
                <Box sx={{ mt: 2 }}>
                  <ResumenTotales detalles={mapDetalles(pedido.detalles)} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
                </Box>
              </>
            ) : (
              <Typography>No hay productos en este pedido.</Typography>
            )}
          </Card>

          <Card sx={{ p: 3 }}>
            <SectionTitle action={
              <Button variant="contained" size="small" onClick={() => setShowPagoModal(true)}>
                Agregar Pago
              </Button>
            }>Pagos</SectionTitle>
            <Divider sx={{ mb: 2 }} />
            {pagoSuccess && <Alert severity="success" sx={{ mb: 2 }}>{pagoSuccess}</Alert>}
            {pagoError && <Alert severity="error" sx={{ mb: 2 }}>{pagoError}</Alert>}
            {pagos && pagos.length > 0 ? (
              <List>
                {pagos.map(pago => (
                  <ListItem key={pago.id_pago} divider>
                    <ListItemText
                      primary={`${pago.metodo_pago_nombre || pago.id_metodo_pago_obj?.nombre_metodo || 'N/A'} - ${pago.moneda_codigo || pago.id_moneda_obj?.codigo_iso || 'N/A'} ${pago.monto} - Tasa: ${pago.tasa}`}
                      secondary={pago.referencia ? `Ref: ${pago.referencia}` : undefined}
                    />
                    {pago.observaciones && (
                      <Typography variant="body2" color="text.secondary">
                        Obs: {pago.observaciones}
                      </Typography>
                    )}
                  </ListItem>
                ))}
              </List>
            ) : (
              <Typography>No hay pagos registrados para este pedido.</Typography>
            )}
          </Card>
        </>
      )}
      <Dialog
        open={showConfirmarDialog}
        onClose={() => !confirmarMutation.isPending && setShowConfirmarDialog(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Confirmar pedido</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Al confirmar, el pedido pasa a APROBADO y se reserva el stock en el almacén
            seleccionado. Si el cliente es a crédito, se genera la cuenta por cobrar.
          </DialogContentText>
          {confirmarError && <Alert severity="error" sx={{ mb: 2 }}>{confirmarError}</Alert>}
          <TextField
            select
            fullWidth
            required
            label="Almacén de despacho"
            value={almacenSeleccionado}
            onChange={(e) => setAlmacenSeleccionado(e.target.value)}
            disabled={almacenesLoading}
            helperText={
              almacenesLoading
                ? 'Cargando almacenes…'
                : almacenesEmpresa.length === 0
                  ? 'No hay almacenes disponibles para esta empresa.'
                  : undefined
            }
          >
            {almacenesEmpresa.map((a) => (
              <MenuItem key={a.id_almacen} value={a.id_almacen}>
                {a.nombre_almacen}
              </MenuItem>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowConfirmarDialog(false)} disabled={confirmarMutation.isPending}>
            Cancelar
          </Button>
          <Button
            variant="contained"
            onClick={() => confirmarMutation.mutate()}
            disabled={!almacenSeleccionado || confirmarMutation.isPending}
            startIcon={confirmarMutation.isPending ? <CircularProgress size={16} /> : undefined}
          >
            Confirmar
          </Button>
        </DialogActions>
      </Dialog>
      {!loading && pedido && (
        <ModalPago
          open={showPagoModal}
          monto={calcularTotalPedido()}
          onClose={() => setShowPagoModal(false)}
          onConfirm={handleConfirmPago}
          empresaId={pedido?.id_empresa?.id_empresa}
          tipoDocumento="PEDIDO"
          idDocumento={pedido?.id_pedido}
          idCliente={pedido?.id_cliente ? 'temp-id' : undefined}
          tipoOperacionInicial="INGRESO"
        />
      )}
    </PageContainer>
  );
};

export default PedidoDetailPage;
