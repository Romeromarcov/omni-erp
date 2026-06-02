import React from 'react';
import { Box, TextField, Typography, Paper, useMediaQuery, useTheme } from '@mui/material';
import type { PedidoDetalleForm } from './TablaProductos';
import { D, subtotalLinea, sumDecimals } from '../../lib/decimal';

interface ResumenTotalesProps {
  detalles: PedidoDetalleForm[];
  descuentoGeneral: string;
  setDescuentoGeneral: (v: string) => void;
}

const ResumenTotales: React.FC<ResumenTotalesProps> = ({ detalles, descuentoGeneral, setDescuentoGeneral }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const subtotalDec = sumDecimals(
    detalles.map((det) => subtotalLinea(det.cantidad, det.precio_unitario, det.descuento_porcentaje)),
  );
  const subtotal = subtotalDec.toFixed(2);
  const totalFinal = subtotalDec.minus(D(descuentoGeneral)).toFixed(2);

  if (isMobile) {
    return (
      <Paper sx={{ p: 2, mt: 2 }}>
        <Typography variant="h6" gutterBottom>
          Resumen Total
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="body1">Subtotal:</Typography>
            <Typography variant="body1">{subtotal}</Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body1" sx={{ flex: 1 }}>Descuento general:</Typography>
            <TextField
              type="number"
              size="small"
              value={descuentoGeneral}
              onChange={(e) => setDescuentoGeneral(e.target.value)}
              sx={{ width: 80 }}
              inputProps={{ min: 0, step: 0.01 }}
            />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', borderTop: 1, borderColor: 'divider', pt: 1 }}>
            <Typography variant="h6">Total:</Typography>
            <Typography variant="h6" color="primary">{totalFinal}</Typography>
          </Box>
        </Box>
      </Paper>
    );
  }

  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
      <Typography variant="h6">Subtotal: {subtotal}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="body1">Descuento general:</Typography>
        <TextField
          type="number"
          size="small"
          value={descuentoGeneral}
          onChange={(e) => setDescuentoGeneral(e.target.value)}
          sx={{ width: 100 }}
          inputProps={{ min: 0, step: 0.01 }}
        />
      </Box>
      <Typography variant="h6" color="primary">Total: {totalFinal}</Typography>
    </Box>
  );
};

export default ResumenTotales;
