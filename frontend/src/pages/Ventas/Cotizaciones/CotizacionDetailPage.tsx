
import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get } from '../../../services/api';
import { pagosService } from '../../../services/pagosService';
import type { Pago as PagoFinanzas } from '../../../services/pagosService';
import { useParams, useNavigate } from 'react-router-dom';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import { fetchProductos } from '../../../services/productosService';
import type { Producto } from '../../../services/productosService';
import { toList } from '../../../utils/api';
import { ventasKeys, finanzasKeys } from '../../../lib/queryKeys';
import { Alert, Box, Button, Card, Divider, List, ListItem, ListItemText, Typography } from '@mui/material';
import ModalPago from '../../../components/Pedidos/ModalPago';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import { PageContainer, PageHeader, SectionTitle, StatusChip } from '../../../components/ui';

interface ClienteInfoAPI {
  id_cliente?: string;
  razon_social?: string;
  nombre?: string;
  rif?: string;
  telefono?: string;
}

interface CotizacionDetalleAPI {
  id_producto?: { id_producto: string; sku?: string; nombre_producto: string };
  producto?: string;
  cantidad: string | number;
  precio_unitario: string | number;
  descuento_porcentaje?: string | number;
  observaciones?: string;
  subtotal?: string | number;
}

interface CotizacionAPI {
  id_cotizacion: string;
  numero_cotizacion: string;
  fecha_cotizacion: string;
  estado: string;
  id_empresa?: { id_empresa: string; nombre: string };
  id_sucursal?: { id_sucursal: string; nombre: string };
  id_caja?: { id_caja: string; nombre: string };
  id_usuario?: { id: number; username: string; first_name: string; last_name: string };
  id_cliente?: ClienteInfoAPI | null;
  observaciones?: string;
  detalles: CotizacionDetalleAPI[];
}

const CotizacionDetailPage: React.FC = () => {
  const { id_cotizacion } = useParams<{ id_cotizacion: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPagoModal, setShowPagoModal] = useState(false);
  const [pagoSuccess, setPagoSuccess] = useState('');
  const [pagoError, setPagoError] = useState('');
  const [descuentoGeneral, setDescuentoGeneral] = useState('');

  const { data: cotizacion = null, isLoading: loading } = useQuery<CotizacionAPI | null>({
    queryKey: ventasKeys.cotizaciones.detail(id_cotizacion!),
    queryFn: () => get<CotizacionAPI>(`/ventas/cotizaciones/${id_cotizacion}/`),
    enabled: !!id_cotizacion,
  });

  const { data: pagos = [] } = useQuery<PagoFinanzas[]>({
    queryKey: finanzasKeys.pagos.porDocumento('COTIZACION', id_cotizacion!),
    queryFn: () => pagosService.getPagos({ tipo_documento: 'COTIZACION', id_documento: id_cotizacion! }),
    enabled: !!id_cotizacion,
  });

  const empresaId = cotizacion?.id_empresa?.id_empresa;
  const { data: productos = [] } = useQuery<unknown, Error, Producto[]>({
    queryKey: ventasKeys.productos(empresaId),
    queryFn: () => fetchProductos(empresaId!),
    select: toList,
    enabled: !!empresaId,
  });

  function mapDetalles(detalles: CotizacionDetalleAPI[]) {
    return detalles.map(det => ({
      id_producto: det.id_producto?.id_producto || '',
      sku: det.id_producto?.sku || '',
      producto: det.id_producto?.nombre_producto || det.producto || '',
      cantidad: det.cantidad.toString(),
      precio_unitario: det.precio_unitario.toString(),
      descuento_porcentaje: (det.descuento_porcentaje || '0').toString(),
      comentarios: det.observaciones || '',
      subtotal: (det.subtotal || '').toString(),
    }));
  }

  function getClienteInfo(cliente: ClienteInfoAPI | null | undefined) {
    if (!cliente) return '-';
    const nombre = cliente.razon_social || cliente.nombre || '-';
    const rif = cliente.rif ? ` | RIF: ${cliente.rif}` : '';
    const telefono = cliente.telefono ? ` | Tel: ${cliente.telefono}` : '';
    return `${nombre}${rif}${telefono}`;
  }

  const handleConfirmPago = async (pagos: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    if (!id_cotizacion || !cotizacion) return;
    setPagoError('');
    setPagoSuccess('');
    try {
      if (notasCreditoUtilizadas && notasCreditoUtilizadas.length > 0) {
        await pagosService.conciliarNotasCredito(notasCreditoUtilizadas, id_cotizacion, 'COTIZACION');
      }
      for (const pago of pagos) {
        await pagosService.createPagoDocumento('COTIZACION', id_cotizacion, {
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
      if (vueltos && vueltos.length > 0) {
        await pagosService.procesarVueltos(vueltos);
      }
      setPagoSuccess('Pagos registrados exitosamente.');
      setShowPagoModal(false);
      queryClient.invalidateQueries({ queryKey: finanzasKeys.pagos.porDocumento('COTIZACION', id_cotizacion!) });
      setTimeout(() => setPagoSuccess(''), 3000);
    } catch {
      setPagoError('Error al registrar los pagos. Intente nuevamente.');
    }
  };

  const calcularTotalCotizacion = () => {
    if (!cotizacion?.detalles) return 0;
    return cotizacion.detalles.reduce((total: number, detalle: CotizacionDetalleAPI) => {
      return total + (Number(detalle.precio_unitario) * Number(detalle.cantidad));
    }, 0);
  };

  return (
    <PageContainer>
      {loading ? (
        <Typography>Cargando...</Typography>
      ) : !cotizacion ? (
        <Typography>No se encontró la cotización.</Typography>
      ) : (
        <>
          <PageHeader
            title={`Cotización ${cotizacion.numero_cotizacion}`}
            subtitle={`${cotizacion.fecha_cotizacion} · ${cotizacion.id_empresa?.nombre || ''}`}
            actions={
              <Button variant="outlined" color="secondary" onClick={() => navigate(-1)}>Volver</Button>
            }
          />
          <Card sx={{ p: 3, mb: 2 }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Fecha</Typography>
                <Typography variant="body1">{cotizacion.fecha_cotizacion}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Estado</Typography>
                <StatusChip value={cotizacion.estado} />
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Empresa</Typography>
                <Typography variant="body1">{cotizacion.id_empresa?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Sucursal</Typography>
                <Typography variant="body1">{cotizacion.id_sucursal?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Caja</Typography>
                <Typography variant="body1">{cotizacion.id_caja?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Usuario</Typography>
                <Typography variant="body1">{cotizacion.id_usuario ? (cotizacion.id_usuario.first_name && cotizacion.id_usuario.last_name ? `${cotizacion.id_usuario.first_name} ${cotizacion.id_usuario.last_name}` : cotizacion.id_usuario.username) : '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Cliente</Typography>
                <Typography variant="body1">{getClienteInfo(cotizacion.id_cliente)}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 100%' }}>
                <Typography variant="body2" color="text.secondary">Observaciones</Typography>
                <Typography variant="body1">{cotizacion.observaciones || '-'}</Typography>
              </Box>
            </Box>
          </Card>

          <Card sx={{ p: 3, mb: 2 }}>
            <SectionTitle>Detalles</SectionTitle>
            {cotizacion.detalles && cotizacion.detalles.length > 0 ? (
              <>
                <TablaProductos
                  detalles={mapDetalles(cotizacion.detalles)}
                  productos={productos}
                  onRemove={() => { }}
                />
                <Box sx={{ mt: 2 }}>
                  <ResumenTotales detalles={mapDetalles(cotizacion.detalles)} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
                </Box>
              </>
            ) : (
              <Typography>No hay productos en esta cotización.</Typography>
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
              <Typography>No hay pagos registrados para esta cotización.</Typography>
            )}
          </Card>
        </>
      )}
      {!loading && cotizacion && (
        <ModalPago
          open={showPagoModal}
          monto={calcularTotalCotizacion()}
          onClose={() => setShowPagoModal(false)}
          onConfirm={handleConfirmPago}
          empresaId={cotizacion?.id_empresa?.id_empresa}
          tipoDocumento="COTIZACION"
          idDocumento={cotizacion?.id_cotizacion}
          idCliente={cotizacion?.id_cliente?.id_cliente || undefined}
          tipoOperacionInicial="INGRESO"
        />
      )}
    </PageContainer>
  );
};

export default CotizacionDetailPage;