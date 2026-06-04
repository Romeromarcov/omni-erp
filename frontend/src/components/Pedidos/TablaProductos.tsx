import React from 'react';
import { Button } from '@mui/material';
import type { Producto } from '../../services/productosService';
import {
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Box, Typography, Stack, useMediaQuery, useTheme,
} from '@mui/material';
import { D, subtotalLinea } from '../../lib/decimal';

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
    return (
      <Stack spacing={1.5}>
        {detalles.map((det, idx) => {
          const productoObj = productos.find(p => p.id_producto === det.id_producto);
          const nombre = det.producto || productoObj?.nombre_producto || '';
          const cantidad = D(det.cantidad).toNumber();
          const precio = D(det.precio_unitario);
          const descPorc = D(det.descuento_porcentaje);
          const total = subtotalLinea(det.cantidad, det.precio_unitario, det.descuento_porcentaje);
          const sku = det.sku || productoObj?.sku || '';
          return (
            <Box
              key={idx}
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 'var(--omni-radius-card, 16px)',
                p: 2,
                bgcolor: 'background.paper',
                boxShadow: 'var(--omni-shadow-card-soft, 0 1px 6px rgba(0,0,0,0.06))',
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1.5, gap: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="subtitle2" fontWeight={700} noWrap>
                    {sku}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    {nombre}
                  </Typography>
                </Box>
                <Button
                  type="button"
                  variant="outlined"
                  size="small"
                  color="error"
                  onClick={() => onRemove(idx)}
                  sx={{ flexShrink: 0 }}
                >
                  Eliminar
                </Button>
              </Box>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Cantidad</Typography>
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>{cantidad}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Precio</Typography>
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>{precio.toFixed(2)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Desc. %</Typography>
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>{descPorc.toFixed(2)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Total</Typography>
                  <Typography variant="body2" fontWeight={700} color="primary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {total.toFixed(2)}
                  </Typography>
                </Box>
              </Box>
            </Box>
          );
        })}
      </Stack>
    );
  }

  // Vista desktop: tabla completa
  return (
    <TableContainer>
      <Table size="small">
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
            const cantidad = D(det.cantidad).toNumber();
            const precio = D(det.precio_unitario);
            const unidad = '';
            const descPorc = D(det.descuento_porcentaje);
            const montoDesc = precio.times(descPorc.dividedBy(100));
            const total = subtotalLinea(det.cantidad, det.precio_unitario, det.descuento_porcentaje);
            const sku = det.sku || productoObj?.sku || '';
            return (
              <TableRow key={idx} hover>
                <TableCell sx={{ fontVariantNumeric: 'tabular-nums' }}>{sku}</TableCell>
                <TableCell>{nombre}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{cantidad}</TableCell>
                <TableCell>{unidad}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{precio.toFixed(2)}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{descPorc.toFixed(2)}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{montoDesc.times(D(det.cantidad)).toFixed(2)}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>{total.toFixed(2)}</TableCell>
                <TableCell>
                  <Button type="button" variant="outlined" size="small" color="error" onClick={() => onRemove(idx)}>
                    Eliminar
                  </Button>
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
