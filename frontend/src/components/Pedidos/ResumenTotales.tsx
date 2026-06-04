import React from 'react';
import { Box, TextField, Typography, Card, CardContent } from '@mui/material';
import type { PedidoDetalleForm } from './TablaProductos';
import { D, subtotalLinea, sumDecimals } from '../../lib/decimal';

interface ResumenTotalesProps {
  detalles: PedidoDetalleForm[];
  descuentoGeneral: string;
  setDescuentoGeneral: (v: string) => void;
}

const ResumenTotales: React.FC<ResumenTotalesProps> = ({ detalles, descuentoGeneral, setDescuentoGeneral }) => {
  const subtotalDec = sumDecimals(
    detalles.map((det) => subtotalLinea(det.cantidad, det.precio_unitario, det.descuento_porcentaje)),
  );
  const subtotal = subtotalDec.toFixed(2);
  const totalFinal = subtotalDec.minus(D(descuentoGeneral)).toFixed(2);

  return (
    <Card
      variant="outlined"
      sx={{
        mt: 2,
        borderRadius: 'var(--omni-radius-card, 16px)',
        boxShadow: 'var(--omni-shadow-card-soft, 0 2px 12px rgba(0,0,0,0.07))',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <CardContent sx={{ p: { xs: 2, md: 2.5 }, '&:last-child': { pb: { xs: 2, md: 2.5 } } }}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            gap: { xs: 1.5, sm: 2 },
            alignItems: { xs: 'stretch', sm: 'center' },
            justifyContent: 'space-between',
          }}
        >
          {/* Subtotal */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flex: 1 }}>
            <Typography variant="body2" color="text.secondary">Subtotal</Typography>
            <Typography variant="body1" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
              {subtotal}
            </Typography>
          </Box>

          {/* Descuento */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, justifyContent: { xs: 'space-between', sm: 'center' } }}>
            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>Descuento general</Typography>
            <TextField
              type="number"
              size="small"
              value={descuentoGeneral}
              onChange={(e) => setDescuentoGeneral(e.target.value)}
              sx={{ width: 100 }}
              inputProps={{ min: 0, step: 0.01 }}
            />
          </Box>

          {/* Total */}
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flex: 1,
              borderTop: { xs: '1px solid', sm: 'none' },
              borderLeft: { xs: 'none', sm: '1px solid' },
              borderColor: 'divider',
              pt: { xs: 1.5, sm: 0 },
              pl: { xs: 0, sm: 2 },
            }}
          >
            <Typography variant="body1" fontWeight={700}>Total</Typography>
            <Typography variant="h6" color="primary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {totalFinal}
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ResumenTotales;
