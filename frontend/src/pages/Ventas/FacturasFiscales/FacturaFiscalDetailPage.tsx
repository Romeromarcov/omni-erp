import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get, fetchBlob } from '../../../services/api';
import { sumDecimals, subtotalLinea } from '../../../lib/decimal';
import { pagosService } from '../../../services/pagosService';
import { useParams, useNavigate } from 'react-router-dom';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import { fetchProductos } from '../../../services/productosService';
import type { Producto } from '../../../services/productosService';
import { toList } from '../../../utils/api';
import { Alert, Box, Button, Card, Divider, List, ListItem, ListItemText, Typography } from '@mui/material';
import ModalPago from '../../../components/Pedidos/ModalPago';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import type { Pago as PagoFinanzas } from '../../../services/pagosService';
import { PageContainer, PageHeader, SectionTitle, StatusChip } from '../../../components/ui';

interface FacturaFiscalDetalle {
  id_detalle_factura: string;
  id_producto?: { id_producto?: string; sku?: string; nombre_producto: string } | null;
  producto?: string;
  cantidad: string;
  precio_unitario: string;
  descuento_porcentaje?: string;
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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [descuentoGeneral, setDescuentoGeneral] = useState<string>('');
  const [showPagoModal, setShowPagoModal] = useState(false);
  const [pagoSuccess, setPagoSuccess] = useState('');
  const [pagoError, setPagoError] = useState('');

  const { data: factura = null, isLoading: loading } = useQuery<FacturaFiscal | null>({
    queryKey: [`/ventas/facturas-fiscales/${id_factura}/`],
    queryFn: () => get<FacturaFiscal>(`/ventas/facturas-fiscales/${id_factura}/`),
    enabled: !!id_factura,
  });

  const { data: pagos = [] } = useQuery<PagoFinanzas[]>({
    queryKey: [`/finanzas/pagos/?tipo_documento=FACTURA_FISCAL&id_documento=${id_factura}`],
    queryFn: () => pagosService.getPagosByTipoDocumento('FACTURA_FISCAL', id_factura!),
    enabled: !!id_factura,
  });

  const empresaId = factura?.id_empresa?.id_empresa;
  const { data: productos = [] } = useQuery<unknown, Error, Producto[]>({
    queryKey: [`/ventas/productos/?id_empresa=${empresaId}`],
    queryFn: () => fetchProductos(empresaId!),
    select: toList,
    enabled: !!empresaId,
  });

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
      queryClient.invalidateQueries({ queryKey: [`/finanzas/pagos/?tipo_documento=FACTURA_FISCAL&id_documento=${id_factura}`] });

      // Limpiar mensaje de éxito después de 3 segundos
      setTimeout(() => setPagoSuccess(''), 3000);
    } catch {
      setPagoError('Error al registrar los pagos. Intente nuevamente.');
    }
  };

  // FE-HIGH-7: total con aritmética decimal (no Number()*Number()).
  const calcularTotalFactura = () => {
    if (!factura?.detalles) return 0;
    return sumDecimals(
      factura.detalles.map((d) =>
        subtotalLinea(d.cantidad, d.precio_unitario, d.descuento_porcentaje),
      ),
    ).toNumber();
  };

  // FE-NEW-1: descargar el PDF vía fetchBlob (envía Authorization desde el token
  // en memoria). window.open no manda el header → daba 401 tras mover el token a
  // memoria. Se descarga como blob y se dispara con un <a> temporal.
  const handleDescargarPDF = async () => {
    if (!id_factura) return;
    try {
      const blob = await fetchBlob(`/ventas/facturas-fiscales/${id_factura}/pdf/`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `factura-${factura?.numero_factura ?? id_factura}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setPagoError('No se pudo descargar el PDF de la factura. Intente nuevamente.');
    }
  };

  return (
    <PageContainer>
      {loading ? (
        <Typography>Cargando...</Typography>
      ) : !factura ? (
        <Typography>No se encontró la factura fiscal.</Typography>
      ) : (
        <>
          <PageHeader
            title={`Factura Fiscal ${factura.numero_factura}`}
            subtitle={`${factura.fecha_emision} · ${factura.id_empresa?.nombre || ''}`}
            actions={
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button variant="outlined" color="secondary" onClick={() => navigate(-1)}>Volver</Button>
                <Button variant="outlined" color="primary" onClick={handleDescargarPDF}>
                  Descargar PDF
                </Button>
              </Box>
            }
          />
          <Card sx={{ p: 3, mb: 2 }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Fecha</Typography>
                <Typography variant="body1">{factura.fecha_emision}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Estado</Typography>
                <StatusChip value={factura.estado} />
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Empresa</Typography>
                <Typography variant="body1">{factura.id_empresa?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Sucursal</Typography>
                <Typography variant="body1">{factura.id_sucursal?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Caja</Typography>
                <Typography variant="body1">{factura.id_caja?.nombre || '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Usuario</Typography>
                <Typography variant="body1">{factura.id_usuario ? (factura.id_usuario.first_name && factura.id_usuario.last_name ? `${factura.id_usuario.first_name} ${factura.id_usuario.last_name}` : factura.id_usuario.username) : '-'}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 200px' }}>
                <Typography variant="body2" color="text.secondary">Cliente</Typography>
                <Typography variant="body1">{getClienteInfo(factura.id_cliente)}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 100%' }}>
                <Typography variant="body2" color="text.secondary">Observaciones</Typography>
                <Typography variant="body1">{factura.observaciones || '-'}</Typography>
              </Box>
            </Box>
          </Card>

          <Card sx={{ p: 3, mb: 2 }}>
            <SectionTitle>Detalles</SectionTitle>
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
              <Typography>No hay pagos registrados para esta factura fiscal.</Typography>
            )}
          </Card>
        </>
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
    </PageContainer>
  );
};

export default FacturaFiscalDetailPage;