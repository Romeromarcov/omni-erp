import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { pagosService } from '../../../services/pagosService';
import PageLayout from '../../../components/PageLayout';
import { useParams, useNavigate } from 'react-router-dom';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import { fetchProductos } from '../../../services/productosService';
import { toList } from '../../../utils/api';
import { Alert, Box, Button, Chip, Divider, List, ListItem, ListItemText, Paper, Typography } from '@mui/material';
import ModalPago from '../../../components/Pedidos/ModalPago';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import type { Pago as PagoFinanzas } from '../../../services/pagosService';
import { notaVentaService } from '../../../services/ventas';
import type { NotaVenta } from '../../../types/ventas';
import type { PedidoDetalleForm } from '../../../components/Pedidos/TablaProductos';
import type { Producto as ProductoService } from '../../../services/productosService';
import { notasVentaKeys, pagosKeys, productosKeys } from '../../../lib/queryKeys';

interface ProductoDisplay {
  id_producto: string;
  nombre_producto: string;
  sku?: string;
}

interface Detalle {
  id_producto: ProductoDisplay;
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  observaciones?: string;
  descuento_porcentaje?: string;
  producto?: string;
}

interface NotaVentaDetail extends Omit<NotaVenta, 'id_empresa' | 'id_sucursal' | 'id_caja' | 'detalles'> {
  id_empresa: { id_empresa: string; nombre: string };
  id_sucursal: { id_sucursal: string; nombre: string };
  id_caja: { id_caja: string; nombre: string };
  id_usuario?: { id: number; username: string; first_name: string; last_name: string };
  detalles?: Detalle[];
}


const NotaVentaDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [descuentoGeneral, setDescuentoGeneral] = useState<string>('');
  const [showPagoModal, setShowPagoModal] = useState(false);
  const [pagoSuccess, setPagoSuccess] = useState('');
  const [pagoError, setPagoError] = useState('');

  const { data: notaVenta = null, isLoading: loading } = useQuery<NotaVentaDetail | null>({
    queryKey: notasVentaKeys.detail(id!),
    queryFn: () => notaVentaService.getById(id!) as unknown as Promise<NotaVentaDetail>,
    enabled: !!id,
  });

  const { data: pagos = [] } = useQuery<PagoFinanzas[]>({
    queryKey: pagosKeys.porDocumento('NOTA_VENTA', id!),
    queryFn: () => pagosService.getPagosNotaVenta(id!),
    enabled: !!id,
  });

  const empresaId = notaVenta?.id_empresa?.id_empresa;
  const { data: productos = [] } = useQuery<unknown, Error, ProductoService[]>({
    queryKey: productosKeys.porEmpresa(empresaId!),
    queryFn: () => fetchProductos(empresaId!),
    select: toList,
    enabled: !!empresaId,
  });

  const convertirMutation = useMutation({
    mutationFn: (notaId: string) => notaVentaService.convertirAFactura(notaId, {}),
    onSuccess: () => {
      // Convertir a factura afecta la nota, sus pagos y la lista de notas de venta.
      queryClient.invalidateQueries({ queryKey: notasVentaKeys.detail(id!) });
      queryClient.invalidateQueries({ queryKey: notasVentaKeys.all() });
      queryClient.invalidateQueries({ queryKey: pagosKeys.porDocumento('NOTA_VENTA', id!) });
    },
    onError: () => alert('Error al convertir la nota de venta a factura'),
  });

  function mapDetalles(detalles: Detalle[]): PedidoDetalleForm[] {
    return detalles.map(det => ({
      id_producto: det.id_producto?.id_producto || '',
      sku: det.id_producto?.sku || '',
      producto: det.id_producto?.nombre_producto || det.producto || '',
      cantidad: det.cantidad,
      precio_unitario: det.precio_unitario,
      descuento_porcentaje: det.descuento_porcentaje || '0',
      comentarios: det.observaciones || '',
    }));
  }

  function getClienteInfo(cliente?: { razon_social?: string; nombre?: string; rif?: string; telefono?: string }): string {
    if (!cliente) return '-';
    const nombre = cliente.razon_social || cliente.nombre || '-';
    const rif = cliente.rif ? ` | RIF: ${cliente.rif}` : '';
    const telefono = cliente.telefono ? ` | Tel: ${cliente.telefono}` : '';
    return `${nombre}${rif}${telefono}`;
  }

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'BORRADOR': return 'default';
      case 'ENTREGADA': return 'primary';
      case 'FACTURADA': return 'success';
      case 'ANULADA': return 'error';
      default: return 'default';
    }
  };

  const handleConfirmPago = async (pagos: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    if (!id || !notaVenta) return;

    setPagoError('');
    setPagoSuccess('');

    try {
      // Procesar notas de crédito si fueron seleccionadas
      if (notasCreditoUtilizadas && notasCreditoUtilizadas.length > 0) {
        await pagosService.conciliarNotasCredito(notasCreditoUtilizadas, id, 'NOTA_VENTA');
      }

      // Enviar los pagos al backend usando la nueva API unificada
      for (const pago of pagos) {
        await pagosService.createPagoDocumento('NOTA_VENTA', id, {
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
      queryClient.invalidateQueries({ queryKey: pagosKeys.porDocumento('NOTA_VENTA', id) });

      // Limpiar mensaje de éxito después de 3 segundos
      setTimeout(() => setPagoSuccess(''), 3000);
    } catch {
      setPagoError('Error al registrar los pagos. Intente nuevamente.');
    }
  };

  const handleConvertirAFactura = () => {
    if (notaVenta && !notaVenta.convertido_a_factura) {
      convertirMutation.mutate(notaVenta.id_nota_venta);
    }
  };

  const calcularTotalNotaVenta = () => {
    if (!notaVenta?.detalles) return 0;
    return notaVenta.detalles.reduce((total, detalle) => {
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
      ) : !notaVenta ? (
        <Typography>No se encontró la nota de venta.</Typography>
      ) : (
        <Paper sx={{ p: 3, borderRadius: 2, boxShadow: 2 }}>
          <Typography variant="h4" gutterBottom>
            Nota de Venta {notaVenta.numero_nota}
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Fecha:</strong> {notaVenta.fecha_nota}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Estado:</strong> <Chip label={notaVenta.estado} color={getEstadoColor(notaVenta.estado)} size="small" /></Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Empresa:</strong> {notaVenta.id_empresa?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Sucursal:</strong> {notaVenta.id_sucursal?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Caja:</strong> {notaVenta.id_caja?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>ID Caja:</strong> {notaVenta.id_caja?.id_caja || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Usuario:</strong> {notaVenta.id_usuario ? (notaVenta.id_usuario.first_name && notaVenta.id_usuario.last_name ? `${notaVenta.id_usuario.first_name} ${notaVenta.id_usuario.last_name}` : notaVenta.id_usuario.username) : '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Número de Nota:</strong> {notaVenta.numero_nota}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Cliente:</strong> {getClienteInfo(notaVenta.id_cliente)}</Typography>
            </Box>
            {notaVenta.id_pedido_origen && (
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography><strong>Pedido Origen:</strong> {notaVenta.id_pedido_origen}</Typography>
              </Box>
            )}
            {notaVenta.convertido_a_factura && (
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography><strong>Estado Conversión:</strong> <Chip label="Convertido a Factura" color="success" size="small" /></Typography>
              </Box>
            )}
            <Box sx={{ flex: '1 1 100%' }}>
              <Typography><strong>Observaciones:</strong> {notaVenta.observaciones || '-'}</Typography>
            </Box>
          </Box>
          <Divider sx={{ my: 3 }} />
          <Typography variant="h5" gutterBottom>Detalles</Typography>
          {notaVenta.detalles && notaVenta.detalles.length > 0 ? (
            <>
              <TablaProductos
                detalles={mapDetalles(notaVenta.detalles)}
                productos={productos}
                onRemove={() => { }}
              />
              <Box sx={{ mt: 2 }}>
                <ResumenTotales detalles={mapDetalles(notaVenta.detalles)} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
              </Box>
            </>
          ) : (
            <Typography>No hay productos en esta nota de venta.</Typography>
          )}
          <Divider sx={{ my: 3 }} />
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h5" gutterBottom>Pagos</Typography>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button variant="contained" onClick={() => setShowPagoModal(true)}>
                Agregar Pago
              </Button>
              {!notaVenta.convertido_a_factura && notaVenta.estado === 'ENTREGADA' && (
                <Button variant="contained" color="secondary" onClick={handleConvertirAFactura}>
                  Convertir a Factura
                </Button>
              )}
            </Box>
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
            <Typography>No hay pagos registrados para esta nota de venta.</Typography>
          )}
        </Paper>
      )}
      {!loading && notaVenta && (
        <ModalPago
          open={showPagoModal}
          monto={calcularTotalNotaVenta()}
          onClose={() => setShowPagoModal(false)}
          onConfirm={handleConfirmPago}
          empresaId={notaVenta?.id_empresa?.id_empresa}
          tipoDocumento="NOTA_VENTA"
          idDocumento={notaVenta?.id_nota_venta}
          idCliente={notaVenta?.id_cliente ? 'temp-id' : undefined}
          tipoOperacionInicial="INGRESO"
        />
      )}
    </PageLayout>
  );
};

export default NotaVentaDetailPage;