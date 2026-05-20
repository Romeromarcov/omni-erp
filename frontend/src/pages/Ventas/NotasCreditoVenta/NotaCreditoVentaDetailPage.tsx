import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { notaCreditoVentaService } from '../../../services/ventas';
import type { NotaCreditoVenta } from '../../../types/ventas';
import { Alert, Box, Button, Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';

const NotaCreditoVentaDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: notaCredito = null, isLoading: loading, isError } = useQuery<NotaCreditoVenta | null>({
    queryKey: [`/ventas/notas-credito-venta/${id}/`],
    queryFn: () => notaCreditoVentaService.getById(id!),
    enabled: !!id,
  });

  const error = isError ? 'Error al cargar la nota de crédito' : null;

  const aplicarMutation = useMutation({
    mutationFn: (notaCreditoId: string) => notaCreditoVentaService.aplicar(notaCreditoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [`/ventas/notas-credito-venta/${id}/`] });
    },
    onError: () => alert('Error al aplicar la nota de crédito'),
  });

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'PENDIENTE': return 'warning';
      case 'APLICADA': return 'success';
      case 'ANULADA': return 'error';
      default: return 'default';
    }
  };

  const handleAplicar = () => {
    if (notaCredito && notaCredito.estado !== 'APLICADA') {
      aplicarMutation.mutate(notaCredito.id_nota_credito);
    }
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;
  if (error) return <PageLayout><Alert severity="error">{error}</Alert></PageLayout>;
  if (!notaCredito) return <PageLayout><div>No se encontró la nota de crédito</div></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1">
            Nota de Crédito de Venta #{notaCredito.numero_nota_credito}
          </Typography>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button variant="contained" color="secondary" onClick={() => navigate(`${notaCredito.id_nota_credito}/edit`)}>
              Editar
            </Button>
            {notaCredito.estado !== 'APLICADA' && (
              <Button variant="contained" onClick={handleAplicar}>
                Aplicar Nota de Crédito
              </Button>
            )}
          </Box>
        </Box>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 3, mb: 3 }}>
            <Box>
              <Typography variant="body2" color="text.secondary">Estado</Typography>
              <Chip
                label={notaCredito.estado || 'PENDIENTE'}
                color={getEstadoColor(notaCredito.estado || 'PENDIENTE')}
                size="small"
              />
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Fecha de Emisión</Typography>
              <Typography variant="body1">
                {new Date(notaCredito.fecha_emision).toLocaleDateString('es-ES', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Cliente</Typography>
              <Typography variant="body1">
                {notaCredito.id_cliente ? (
                  <div>
                    <div style={{ fontWeight: 'bold' }}>{notaCredito.id_cliente.nombre}</div>
                    <div style={{ fontSize: '12px', color: '#6c757d' }}>
                      {notaCredito.id_cliente.razon_social} - {notaCredito.id_cliente.rif}
                    </div>
                  </div>
                ) : (
                  <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                )}
              </Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Motivo</Typography>
              <Typography variant="body1">{notaCredito.motivo}</Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Monto Total</Typography>
              <Typography variant="body1" sx={{ fontWeight: 'bold', fontSize: '1.2em' }}>
                {notaCredito.monto_total?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
              </Typography>
            </Box>
          </Box>

          {notaCredito.observaciones && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="body2" color="text.secondary">Observaciones</Typography>
              <Typography variant="body1">{notaCredito.observaciones}</Typography>
            </Box>
          )}
        </Paper>

        {notaCredito.detalles && notaCredito.detalles.length > 0 && (
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Detalles</Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Producto</TableCell>
                    <TableCell align="right">Cantidad</TableCell>
                    <TableCell align="right">Precio Unitario</TableCell>
                    <TableCell align="right">Subtotal</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {notaCredito.detalles.map((detalle) => (
                    <TableRow key={detalle.id_detalle_nota_credito}>
                      <TableCell>{detalle.id_producto}</TableCell>
                      <TableCell align="right">{detalle.cantidad}</TableCell>
                      <TableCell align="right">
                        {detalle.precio_unitario?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                      </TableCell>
                      <TableCell align="right">
                        {detalle.subtotal?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                      </TableCell>
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

export default NotaCreditoVentaDetailPage;