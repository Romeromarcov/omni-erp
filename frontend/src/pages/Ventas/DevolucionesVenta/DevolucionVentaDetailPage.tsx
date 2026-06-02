import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { devolucionVentaService } from '../../../services/ventas';
import type { DevolucionVenta } from '../../../types/ventas';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { ventasKeys } from '../../../lib/queryKeys';
import { Alert, Box, Button, Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';

const DevolucionVentaDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const { data: devolucion = null, isLoading: loading, isError } = useQuery<DevolucionVenta | null>({
    queryKey: ventasKeys.devoluciones.detail(id!),
    queryFn: () => devolucionVentaService.getById(id!),
    enabled: !!id,
  });

  const error = isError ? 'Error al cargar la devolución' : null;

  const procesarMutation = useMutation({
    mutationFn: (devolucionId: string) => devolucionVentaService.procesar(devolucionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ventasKeys.devoluciones.detail(id!) });
    },
    onError: () => snackbar.error('Error al procesar la devolución'),
  });

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'PENDIENTE': return 'warning';
      case 'APROBADA': return 'info';
      case 'PROCESADA': return 'success';
      case 'RECHAZADA': return 'error';
      case 'ANULADA': return 'default';
      default: return 'default';
    }
  };

  const getEstadoProductoColor = (estado: string) => {
    switch (estado) {
      case 'BUENO': return 'success';
      case 'DEFECTUOSO': return 'error';
      case 'VENCIDO': return 'warning';
      case 'DAÑADO': return 'error';
      default: return 'default';
    }
  };

  const getAccionInventarioColor = (accion: string) => {
    switch (accion) {
      case 'REINTEGRAR': return 'success';
      case 'CUARENTENA': return 'warning';
      case 'DESCARTAR': return 'error';
      case 'REPARAR': return 'info';
      default: return 'default';
    }
  };

  const handleProcesar = () => {
    if (devolucion && devolucion.estado === 'PENDIENTE') {
      procesarMutation.mutate(devolucion.id_devolucion);
    }
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;
  if (error) return <PageLayout><Alert severity="error">{error}</Alert></PageLayout>;
  if (!devolucion) return <PageLayout><div>No se encontró la devolución</div></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1">
            Devolución #{devolucion.numero_devolucion}
          </Typography>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button variant="contained" color="secondary" onClick={() => navigate(`${devolucion.id_devolucion}/edit`)}>
              Editar
            </Button>
            {devolucion.estado === 'PENDIENTE' && (
              <Button variant="contained" onClick={handleProcesar}>
                Procesar Devolución
              </Button>
            )}
          </Box>
        </Box>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 3, mb: 3 }}>
            <Box>
              <Typography variant="body2" color="text.secondary">Estado</Typography>
              <Chip
                label={devolucion.estado || 'PENDIENTE'}
                color={getEstadoColor(devolucion.estado || 'PENDIENTE')}
                size="small"
              />
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Fecha de Devolución</Typography>
              <Typography variant="body1">
                {new Date(devolucion.fecha_devolucion).toLocaleDateString('es-ES', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Cliente</Typography>
              <Typography variant="body1">
                {devolucion.id_cliente ? (
                  <div>
                    <div style={{ fontWeight: 'bold' }}>{devolucion.id_cliente.razon_social}</div>
                    <div style={{ fontSize: '12px', color: '#6c757d' }}>
                      {devolucion.id_cliente.razon_social} - {devolucion.id_cliente.rif}
                    </div>
                  </div>
                ) : (
                  <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                )}
              </Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Factura Origen</Typography>
              <Typography variant="body1">{devolucion.id_factura_origen || 'N/A'}</Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Motivo</Typography>
              <Typography variant="body1">{devolucion.motivo_devolucion}</Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Monto Total</Typography>
              <Typography variant="body1" sx={{ fontWeight: 'bold', fontSize: '1.2em' }}>
                {devolucion.monto_total?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
              </Typography>
            </Box>
            {devolucion.id_nota_credito_generada && (
              <Box>
                <Typography variant="body2" color="text.secondary">Nota de Crédito Generada</Typography>
                <Typography variant="body1">{devolucion.id_nota_credito_generada}</Typography>
              </Box>
            )}
          </Box>

          {devolucion.observaciones && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="body2" color="text.secondary">Observaciones</Typography>
              <Typography variant="body1">{devolucion.observaciones}</Typography>
            </Box>
          )}
        </Paper>

        {devolucion.detalles && devolucion.detalles.length > 0 && (
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Detalles de la Devolución</Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Producto</TableCell>
                    <TableCell align="right">Cantidad Devuelta</TableCell>
                    <TableCell align="right">Precio Unitario</TableCell>
                    <TableCell align="right">Subtotal</TableCell>
                    <TableCell>Estado del Producto</TableCell>
                    <TableCell>Acción en Inventario</TableCell>
                    <TableCell>Observaciones</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {devolucion.detalles.map((detalle) => (
                    <TableRow key={detalle.id_detalle_devolucion}>
                      <TableCell>{detalle.id_producto}</TableCell>
                      <TableCell align="right">{detalle.cantidad_devuelta}</TableCell>
                      <TableCell align="right">
                        {detalle.precio_unitario?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                      </TableCell>
                      <TableCell align="right">
                        {detalle.subtotal?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={detalle.estado_producto}
                          color={getEstadoProductoColor(detalle.estado_producto)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={detalle.accion_inventario}
                          color={getAccionInventarioColor(detalle.accion_inventario)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>{detalle.observaciones || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        )}
      </Box>
    </PageLayout>
  );
};

export default DevolucionVentaDetailPage;