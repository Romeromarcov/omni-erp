import React, { useEffect, useState } from 'react';
import { get } from '../../../services/api';
import { pagosService } from '../../../services/pagosService';
import PageLayout from '../../../components/PageLayout';
import { useParams, useNavigate } from 'react-router-dom';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import { fetchProductos } from '../../../services/productosService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, Divider, List, ListItem, ListItemText, Paper, Typography } from '@mui/material';
import ModalPago from '../../../components/Pedidos/ModalPago';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import type { Pago as PagoFinanzas } from '../../../services/pagosService';

interface FacturaFiscalDetalle {
  id_detalle_factura: string;
  id_producto: { nombre_producto: string };
  cantidad: string;
  precio_unitario: string;
  subtotal: string;
  observaciones?: string;
}

interface ClienteInfoFactura {
  razon_social?: string;
  nombre?: string;
  rif?: string;
  telefono?: string;
}

interface FacturaFiscal {
  id_factura: string;
  numero_factura: string;
  fecha_emision: string;
  estado: string;
  id_empresa: { id_empresa: string; nombre: string };
  id_sucursal?: { id_sucursal: string; nombre: string };
  id_caja?: { id_caja: string; nombre: string };
  id_usuario?: { id: number; username: string; first_name: string; last_name: string };
  id_cliente: ClienteInfoFactura;
  observaciones?: string;
  detalles: FacturaFiscalDetalle[];
  // pagos será cargado desde la nueva API
}

const FacturaFiscalDetailPage: React.FC = () => {
  const { id_factura } = useParams();
  const [factura, setFactura] = useState<FacturaFiscal | null>(null);
  const [pagos, setPagos] = useState<PagoFinanzas[]>([]);
  const [loading, setLoading] = useState(false);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [descuentoGeneral, setDescuentoGeneral] = useState<string>('');
  const [showPagoModal, setShowPagoModal] = useState(false);
  const [pagoSuccess, setPagoSuccess] = useState('');
  const [pagoError, setPagoError] = useState('');
  const navigate = useNavigate();

  const loadPagos = async (facturaId: string) => {
    try {
      const pagosData = await pagosService.getPagosByTipoDocumento('FACTURA_FISCAL', facturaId);
      setPagos(pagosData);
    } catch (error) {
      console.error('Error al cargar pagos:', error);
    }
  };

  useEffect(() => {
    if (!id_factura) return;
    setLoading(true);
    get<FacturaFiscal>(`/ventas/facturas-fiscales/${id_factura}/`)
      .then(res => {
        setFactura(res);
        // Cargar pagos de la factura
        loadPagos(id_factura);
      })
      .catch(() => setFactura(null))
      .finally(() => setLoading(false));
  }, [id_factura]);

  useEffect(() => {
    if (factura?.id_empresa && factura.id_empresa.id_empresa) {
      fetchProductos(factura.id_empresa.id_empresa)
        .then((res) => {
          if (Array.isArray(res)) setProductos(res);
          else if (res && Array.isArray((res as { results: Producto[] }).results)) setProductos((res as { results: Producto[] }).results);
          else setProductos([]);
        })
        .catch(() => setProductos([]));
    }
  }, [factura?.id_empresa]);

  function mapDetalles(detalles: FacturaFiscalDetalle[]) {
    return detalles.map(det => ({
      id_producto: det.id_producto?.id_producto || '',
      sku: det.id_producto?.sku || '',
      producto: det.id_producto?.nombre_producto || det.producto || '',
      cantidad: det.cantidad,
      precio_unitario: det.precio_unitario,
      descuento_porcentaje: det.descuento_porcentaje || '0',
      comentarios: det.observaciones || '',
      subtotal: det.subtotal || '',
    }));
  }

  function getClienteInfo(cliente: ClienteInfoFactura | null | undefined) {
    if (!cliente) return '-';
    const nombre = cliente.razon_social || cliente.nombre || '-';
    const rif = cliente.rif ? ` | RIF: ${cliente.rif}` : '';
    const telefono = cliente.telefono ? ` | Tel: ${cliente.telefono}` : '';
    return `${nombre}${rif}${telefono}`;
  }

  const handleConfirmPago = async (pagos: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    if (!id_factura || !factura) return;

    setPagoError('');
    setPagoSuccess('');

    try {
      // Procesar notas de crédito si fueron seleccionadas
      if (notasCreditoUtilizadas && notasCreditoUtilizadas.length > 0) {
        await pagosService.conciliarNotasCredito(notasCreditoUtilizadas, id_factura, 'FACTURA_FISCAL');
      }

      // Enviar los pagos al backend usando la nueva API unificada
      for (const pago of pagos) {
        await pagosService.createPagoDocumento('FACTURA_FISCAL', id_factura, {
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
      if (id_factura) {
        loadPagos(id_factura);
      }

      // Limpiar mensaje de éxito después de 3 segundos
      setTimeout(() => setPagoSuccess(''), 3000);
    } catch {
      setPagoError('Error al registrar los pagos. Intente nuevamente.');
    }
  };

  const calcularTotalFactura = () => {
    if (!factura?.detalles) return 0;
    return factura.detalles.reduce((total, detalle) => {
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
      ) : !factura ? (
        <Typography>No se encontró la factura fiscal.</Typography>
      ) : (
        <Paper sx={{ p: 3, borderRadius: 2, boxShadow: 2 }}>
          <Typography variant="h4" gutterBottom>
            Factura Fiscal {factura.numero_factura}
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Fecha:</strong> {factura.fecha_emision}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Estado:</strong> {factura.estado}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Empresa:</strong> {factura.id_empresa?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Sucursal:</strong> {factura.id_sucursal?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Caja:</strong> {factura.id_caja?.nombre || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>ID Caja:</strong> {factura.id_caja?.id_caja || '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Usuario:</strong> {factura.id_usuario ? (factura.id_usuario.first_name && factura.id_usuario.last_name ? `${factura.id_usuario.first_name} ${factura.id_usuario.last_name}` : factura.id_usuario.username) : '-'}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Número de Factura:</strong> {factura.numero_factura}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <Typography><strong>Cliente:</strong> {getClienteInfo(factura.id_cliente)}</Typography>
            </Box>
            <Box sx={{ flex: '1 1 100%' }}>
              <Typography><strong>Observaciones:</strong> {factura.observaciones || '-'}</Typography>
            </Box>
          </Box>
          <Divider sx={{ my: 3 }} />
          <Typography variant="h5" gutterBottom>Detalles</Typography>
          {factura.detalles && factura.detalles.length > 0 ? (
            <>
              <TablaProductos
                detalles={mapDetalles(factura.detalles)}
                productos={productos}
                onRemove={() => {}}
              />
              <Box sx={{ mt: 2 }}>
                <ResumenTotales detalles={mapDetalles(factura.detalles)} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
              </Box>
            </>
          ) : (
            <Typography>No hay productos en esta factura fiscal.</Typography>
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
            <Typography>No hay pagos registrados para esta factura fiscal.</Typography>
          )}
        </Paper>
      )}
      {!loading && factura && (
        <ModalPago
          open={showPagoModal}
          monto={calcularTotalFactura()}
          onClose={() => setShowPagoModal(false)}
          onConfirm={handleConfirmPago}
          empresaId={factura?.id_empresa?.id_empresa}
          tipoDocumento="FACTURA"
          idDocumento={factura?.id_factura}
          idCliente={factura?.id_cliente ? 'temp-id' : undefined} // TODO: Obtener ID real del cliente
          tipoOperacionInicial="INGRESO"
        />
      )}
    </PageLayout>
  );
};

export default FacturaFiscalDetailPage;