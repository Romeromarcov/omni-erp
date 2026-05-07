import React from 'react';
import { Box, TextField, Typography, Paper, useMediaQuery, useTheme } from '@mui/material';
import type { PedidoDetalleForm } from './TablaProductos';

interface ResumenTotalesProps {
  detalles: PedidoDetalleForm[];
  descuentoGeneral: string;
  setDescuentoGeneral: (v: string) => void;
}

const ResumenTotales: React.FC<ResumenTotalesProps> = ({ detalles, descuentoGeneral, setDescuentoGeneral }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const subtotal = detalles.reduce((acc, det) => {
    const cantidad = parseFloat(det.cantidad) || 0;
    const precio = parseFloat(det.precio_unitario) || 0;
    const descPorc = parseFloat(det.descuento_porcentaje || '0') || 0;
    const montoDesc = precio * (descPorc / 100);
    const total = (cantidad * precio) - (cantidad * montoDesc);
    return acc + total;
  }, 0);
  const descuentoGeneralNum = parseFloat(descuentoGeneral || '0') || 0;
  const totalFinal = subtotal - descuentoGeneralNum;

  if (isMobile) {
    return (
      <Paper sx={{ p: 2, mt: 2 }}>
        <Typography variant="h6" gutterBottom>
          Resumen Total
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="body1">Subtotal:</Typography>
            <Typography variant="body1">{subtotal.toFixed(2)}</Typography>
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
            <Typography variant="h6" color="primary">{totalFinal.toFixed(2)}</Typography>
          </Box>
        </Box>
      </Paper>
    );
  }

  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
      <Typography variant="h6">Subtotal: {subtotal.toFixed(2)}</Typography>
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
      <Typography variant="h6" color="primary">Total: {totalFinal.toFixed(2)}</Typography>
    </Box>
  );
};

export default ResumenTotales;
