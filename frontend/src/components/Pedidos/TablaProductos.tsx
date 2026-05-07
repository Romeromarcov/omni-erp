import React from 'react';
import { Button } from '../Button';
import type { Producto } from '../../services/productosService';
import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Box, Typography, useMediaQuery, useTheme } from '@mui/material';

export interface PedidoDetalleForm {
  id_producto: string;
  cantidad: string;
  precio_unitario: string;
  descuento_porcentaje?: string;
  sku?: string;
  producto?: string;
  comentarios?: string;
}

interface TablaProductosProps {
  detalles: PedidoDetalleForm[];
  productos: Producto[];
  onRemove: (idx: number) => void;
}

const TablaProductos: React.FC<TablaProductosProps> = ({ detalles, productos, onRemove }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  if (isMobile) {
    // Vista móvil: mostrar como lista de cards
    return (
      <Box>
        {detalles.map((det, idx) => {
          const productoObj = productos.find(p => p.id_producto === det.id_producto);
          const nombre = det.producto || productoObj?.nombre_producto || '';
          const cantidad = parseFloat(det.cantidad) || 0;
          const precio = parseFloat(det.precio_unitario) || 0;
          const descPorc = parseFloat(det.descuento_porcentaje || '0') || 0;
          const montoDesc = precio * (descPorc / 100);
          const total = (cantidad * precio) - (cantidad * montoDesc);
          const sku = det.sku || productoObj?.sku || '';
          return (
            <Box
              key={idx}
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                p: 2,
                mb: 2,
                bgcolor: 'background.paper'
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight="bold">
                    {sku}
                  </Typography>
                  <Typography variant="body2">
                    {nombre}
                  </Typography>
                </Box>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => onRemove(idx)}
                >
                  Eliminar
                </Button>
              </Box>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Cantidad</Typography>
                  <Typography variant="body2">{cantidad}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Precio</Typography>
                  <Typography variant="body2">{precio.toFixed(2)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Desc. %</Typography>
                  <Typography variant="body2">{descPorc.toFixed(2)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Total</Typography>
                  <Typography variant="body2" fontWeight="bold">{total.toFixed(2)}</Typography>
                </Box>
              </Box>
            </Box>
          );
        })}
      </Box>
    );
  }

  // Vista desktop: tabla completa
  return (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>SKU</TableCell>
            <TableCell>Descripción</TableCell>
            <TableCell align="right">Cantidad</TableCell>
            <TableCell>Unidad</TableCell>
            <TableCell align="right">Precio</TableCell>
            <TableCell align="right">% Desc.</TableCell>
            <TableCell align="right">Monto Desc.</TableCell>
            <TableCell align="right">Total</TableCell>
            <TableCell>Acción</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {detalles.map((det, idx) => {
            const productoObj = productos.find(p => p.id_producto === det.id_producto);
            const nombre = det.producto || productoObj?.nombre_producto || '';
            const cantidad = parseFloat(det.cantidad) || 0;
            const precio = parseFloat(det.precio_unitario) || 0;
            const unidad = '';
            const descPorc = parseFloat(det.descuento_porcentaje || '0') || 0;
            const montoDesc = precio * (descPorc / 100);
            const total = (cantidad * precio) - (cantidad * montoDesc);
            const sku = det.sku || productoObj?.sku || '';
            return (
              <TableRow key={idx}>
                <TableCell>{sku}</TableCell>
                <TableCell>{nombre}</TableCell>
                <TableCell align="right">{cantidad}</TableCell>
                <TableCell>{unidad}</TableCell>
                <TableCell align="right">{precio.toFixed(2)}</TableCell>
                <TableCell align="right">{descPorc.toFixed(2)}</TableCell>
                <TableCell align="right">{(montoDesc * cantidad).toFixed(2)}</TableCell>
                <TableCell align="right">{total.toFixed(2)}</TableCell>
                <TableCell>
                  <Button type="button" variant="secondary" onClick={() => onRemove(idx)}>Eliminar</Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

export default TablaProductos;
