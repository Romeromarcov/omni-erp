import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get } from '../../../services/api';
import { pagosService } from '../../../services/pagosService';
import PageLayout from '../../../components/PageLayout';
import { useParams, useNavigate } from 'react-router-dom';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import type { PedidoDetalleForm } from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import { fetchProductos } from '../../../services/productosService';
import { toList } from '../../../utils/api';
import { Alert, Box, Button, Divider, List, ListItem, ListItemText, Paper, Typography } from '@mui/material';
import ModalPago from '../../../components/Pedidos/ModalPago';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import type { Pago as PagoFinanzas } from '../../../services/pagosService';

interface PedidoDetalle {
  id_detalle_pedido: string;
  id_producto: { nombre_producto: string };
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

const PedidoDetailPage: React.FC = () => {
  const { id_pedido } = useParams();
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [pagos, setPagos] = useState<PagoFinanzas[]>([]);
  const [loading, setLoading] = useState(false);
  const [productos, setProductos] = useState<PedidoDetalleForm[]>([]);
  const [descuentoGeneral, setDescuentoGeneral] = useState<string>('');
  const [showPagoModal, setShowPagoModal] = useState(false);
  const [pagoSuccess, setPagoSuccess] = useState('');
  const [pagoError, setPagoError] = useState('');
  const navigate = useNavigate();

  const loadPagos = async (pedidoId: string) => {
    try {
      const pagosData = await pagosService.getPagosPedido(pedidoId);
      setPagos(pagosData);
    } catch (error) {
      console.error('Error al cargar pagos:', error);
    }
  };

  useEffect(() => {
    if (!id_pedido) return;
    setLoading(true);
    get(`/ventas/pedidos/${id_pedido}/`)
      .then((res) => {
        setPedido(res);
        // Cargar pagos del pedido
        loadPagos(id_pedido);
      })
      .catch(() => setPedido(null))
      .finally(() => setLoading(false));
  }, [id_pedido]);

  useEffect(() => {
    if (pedido?.id_empresa && pedido.id_empresa.id_empresa) {
      fetchProductos(pedido.id_empresa.id_empresa)
        .then((res) => {
          if (Array.isArray(res)) setProductos(res as PedidoDetalleForm[]);
          else if (res && Array.isArray((res as { results: PedidoDetalleForm[] }).results)) setProductos((res as { results: PedidoDetalleForm[] }).results);
          else setProductos([]);
        })
        .catch(() => setProductos([]));
    }
  }, [pedido?.id_empresa]);

  function mapDetalles(detalles: PedidoDetalle[]): PedidoDetalleForm[] {
    return detalles.map(det => ({
      id_producto: typeof det.id_producto === 'object' && det.id_producto ? det.id_producto.id_producto : '',
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
      if (id_pedido) {
        loadPagos(id_pedido);
      }

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
    <PageLayout>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" color="secondary" onClick={() => navigate(-1)}>Volver</Button>
      </Box>
      {loading ? (
        <Typography>Cargando...</Typography>
      ) : !pedido ? (
        <Typography>No se encontró el pedido.</Typography>
      ) : (
        <Paper sx={{ p: 3, borderRadius: 2, boxShadow: 2 }}>
          <Typography variant="h4" gutterBottom>
            Pedido {pedido.numero_pedido}
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Fecha:</strong> {pedido.fecha_pedido}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Estado:</strong> {pedido.estado}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Empresa:</strong> {pedido.id_empresa?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Sucursal:</strong> {pedido.id_sucursal?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Caja:</strong> {pedido.id_caja?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>ID Caja:</strong> {pedido.id_caja?.id_caja || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Usuario:</strong> {pedido.id_usuario ? (pedido.id_usuario.first_name && pedido.id_usuario.last_name ? `${pedido.id_usuario.first_name} ${pedido.id_usuario.last_name}` : pedido.id_usuario.username) : '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Número de Pedido:</strong> {pedido.numero_pedido}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Cliente:</strong> {getClienteInfo(pedido.id_cliente)}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 100%' }}>
              <Typography><strong>Observaciones:</strong> {pedido.observaciones || '-'}</Typography>
            </Box>
          </Box>
          <Divider sx={{ my: 3 }} />
          <Typography variant="h5" gutterBottom>Detalles</Typography>
          {pedido.detalles && pedido.detalles.length > 0 ? (
            <>
              <TablaProductos
                detalles={mapDetalles(pedido.detalles)}
                productos={productos}
                onRemove={() => {}}
              />
              <Box sx={{ mt: 2 }}>
                <ResumenTotales detalles={mapDetalles(pedido.detalles)} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
              </Box>
            </>
          ) : (
            <Typography>No hay productos en este pedido.</Typography>
          )}
          <Divider sx={{ my: 3 }} />
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h5" gutterBottom>Pagos</Typography>
            <Button variant="contained" onClick={() => setShowPagoModal(true)}>
              Agregar Pago
            </Button>
          </Box>
          {pagoSuccess && <Alert severity="success" sx={{ mb: 2 }}>{pagoSuccess}</Alert>}
          {pagoError && <Alert severity="error" sx={{ mb: 2 }}>{pagoError}</Alert>}
          {pagos && pagos.length > 0 ? (
            <List>
              {pagos.map(pago => (
                  <ListItem key={pago.id_pago} divider>
                  <ListItemText
                    primary={`${pago.id_metodo_pago_obj?.nombre_metodo || pago.id_metodo_pago || 'N/A'} - ${pago.id_moneda_obj?.codigo_iso || pago.id_moneda || 'N/A'} ${pago.monto} - Tasa: ${pago.tasa}`}
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
        </Paper>
      )}
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
    </PageLayout>
  );
};

export default PedidoDetailPage;
