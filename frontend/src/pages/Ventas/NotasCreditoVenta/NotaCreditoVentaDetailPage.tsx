import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notaCreditoVentaService } from '../../../services/ventas';
import type { NotaCreditoVenta } from '../../../types/ventas';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { ventasKeys } from '../../../lib/queryKeys';
import { Alert, Box, Button, Card, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { PageContainer, PageHeader, SectionTitle, StatusChip } from '../../../components/ui';

const NotaCreditoVentaDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const { data: notaCredito = null, isLoading: loading, isError } = useQuery<NotaCreditoVenta | null>({
    queryKey: ventasKeys.notasCreditoVenta.detail(id!),
    queryFn: () => notaCreditoVentaService.getById(id!),
    enabled: !!id,
  });

  const error = isError ? 'Error al cargar la nota de crédito' : null;

  const aplicarMutation = useMutation({
    mutationFn: (notaCreditoId: string) => notaCreditoVentaService.aplicar(notaCreditoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [`/ventas/notas-credito-venta/${id}/`] });
    },
    onError: () => snackbar.error('Error al aplicar la nota de crédito'),
  });

  const handleAplicar = () => {
    if (notaCredito && notaCredito.estado !== 'APLICADA') {
      aplicarMutation.mutate(notaCredito.id_nota_credito);
    }
  };

  if (loading) return <PageContainer><Typography>Cargando...</Typography></PageContainer>;
  if (error) return <PageContainer><Alert severity="error">{error}</Alert></PageContainer>;
  if (!notaCredito) return <PageContainer><Typography>No se encontró la nota de crédito</Typography></PageContainer>;

  return (
    <PageContainer>
      <PageHeader
        title={`Nota de Crédito de Venta #${notaCredito.numero_nota_credito}`}
        subtitle={new Date(notaCredito.fecha_emision).toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })}
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button variant="outlined" color="secondary" onClick={() => navigate(`${notaCredito.id_nota_credito}/edit`)}>
              Editar
            </Button>
            {notaCredito.estado !== 'APLICADA' && (
              <Button variant="contained" onClick={handleAplicar}>
                Aplicar Nota de Crédito
              </Button>
            )}
          </Box>
        }
      />

      <Card sx={{ p: 3, mb: 2 }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 3, mb: 3 }}>
          <Box>
            <Typography variant="body2" color="text.secondary">Estado</Typography>
            <StatusChip value={notaCredito.estado || 'PENDIENTE'} />
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
            {notaCredito.id_cliente ? (
              <>
                <Typography variant="body1" fontWeight={600}>{notaCredito.id_cliente.nombre}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {notaCredito.id_cliente.razon_social} - {notaCredito.id_cliente.rif}
                </Typography>
              </>
            ) : (
              <Typography variant="body2" color="error">Cliente no encontrado</Typography>
            )}
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">Motivo</Typography>
            <Typography variant="body1">{notaCredito.motivo}</Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">Monto Total</Typography>
            <Typography variant="body1" fontWeight={700} fontSize="1.2em">
              {notaCredito.monto_total?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
            </Typography>
          </Box>
        </Box>

        {notaCredito.observaciones && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">Observaciones</Typography>
            <Typography variant="body1">{notaCredito.observaciones}</Typography>
          </Box>
        )}
      </Card>

      {notaCredito.detalles && notaCredito.detalles.length > 0 && (
        <Card sx={{ p: 3 }}>
          <SectionTitle>Detalles</SectionTitle>
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
        </Card>
      )}
    </PageContainer>
  );
};

export default NotaCreditoVentaDetailPage;