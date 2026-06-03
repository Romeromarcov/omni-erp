import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { devolucionVentaService } from '../../../services/ventas';
import type { DevolucionVenta } from '../../../types/ventas';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { ventasKeys } from '../../../lib/queryKeys';
import { Alert, Box, Button, Card, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { PageContainer, PageHeader, SectionTitle, StatusChip } from '../../../components/ui';

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

  const ESTADO_PRODUCTO_COLOR: Record<string, 'default' | 'success' | 'error' | 'warning' | 'info'> = {
    bueno: 'success',
    defectuoso: 'error',
    vencido: 'warning',
    dañado: 'error',
  };

  const ACCION_INVENTARIO_COLOR: Record<string, 'default' | 'success' | 'error' | 'warning' | 'info'> = {
    reintegrar: 'success',
    cuarentena: 'warning',
    descartar: 'error',
    reparar: 'info',
  };

  const handleProcesar = () => {
    if (devolucion && devolucion.estado === 'PENDIENTE') {
      procesarMutation.mutate(devolucion.id_devolucion);
    }
  };

  if (loading) return <PageContainer><Typography>Cargando...</Typography></PageContainer>;
  if (error) return <PageContainer><Alert severity="error">{error}</Alert></PageContainer>;
  if (!devolucion) return <PageContainer><Typography>No se encontró la devolución</Typography></PageContainer>;

  return (
    <PageContainer>
      <PageHeader
        title={`Devolución #${devolucion.numero_devolucion}`}
        subtitle={new Date(devolucion.fecha_devolucion).toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })}
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button variant="outlined" color="secondary" onClick={() => navigate(`${devolucion.id_devolucion}/edit`)}>
              Editar
            </Button>
            {devolucion.estado === 'PENDIENTE' && (
              <Button variant="contained" onClick={handleProcesar}>
                Procesar Devolución
              </Button>
            )}
          </Box>
        }
      />

      <Card sx={{ p: 3, mb: 2 }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 3, mb: 3 }}>
          <Box>
            <Typography variant="body2" color="text.secondary">Estado</Typography>
            <StatusChip value={devolucion.estado || 'PENDIENTE'} />
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
            {devolucion.id_cliente ? (
              <>
                <Typography variant="body1" fontWeight={600}>{devolucion.id_cliente.razon_social}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {devolucion.id_cliente.razon_social} - {devolucion.id_cliente.rif}
                </Typography>
              </>
            ) : (
              <Typography variant="body2" color="error">Cliente no encontrado</Typography>
            )}
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
            <Typography variant="body1" fontWeight={700} fontSize="1.2em">
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
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">Observaciones</Typography>
            <Typography variant="body1">{devolucion.observaciones}</Typography>
          </Box>
        )}
      </Card>

      {devolucion.detalles && devolucion.detalles.length > 0 && (
        <Card sx={{ p: 3 }}>
          <SectionTitle>Detalles de la Devolución</SectionTitle>
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
                      <StatusChip value={detalle.estado_producto} colorMap={ESTADO_PRODUCTO_COLOR} />
                    </TableCell>
                    <TableCell>
                      <StatusChip value={detalle.accion_inventario} colorMap={ACCION_INVENTARIO_COLOR} />
                    </TableCell>
                    <TableCell>{detalle.observaciones || '-'}</TableCell>
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

export default DevolucionVentaDetailPage;