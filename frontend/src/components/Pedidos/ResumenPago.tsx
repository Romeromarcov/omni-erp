import React from 'react';
import { Box, Typography, Card, CardContent, Divider } from '@mui/material';
import type { Moneda } from './types';
import { D, toFixedStr, type DecimalInput } from '../../lib/decimal';

interface ResumenPagoProps {
  monto: DecimalInput;
  totalPagadoConNotasBase: DecimalInput;
  saldoRestante: DecimalInput;
  toleranciaPositiva: DecimalInput;
  notasCreditoCount: number;
  monedaBase: Moneda | undefined;
  monedaPais: Moneda | undefined;
  tasaBCV: DecimalInput;
  esDiferenciaAceptable: (d: DecimalInput) => boolean;
}

/**
 * Resumen de totales y diferencia del ModalPago:
 * muestra monto del documento, total de pagos + notas de crédito,
 * y la diferencia con indicadores de tolerancia.
 */
const ResumenPago: React.FC<ResumenPagoProps> = ({
  monto, totalPagadoConNotasBase, saldoRestante, toleranciaPositiva,
  notasCreditoCount, monedaBase, monedaPais, tasaBCV, esDiferenciaAceptable,
}) => {
  const saldoDec = D(saldoRestante);
  const tolDec = D(toleranciaPositiva);
  const colorSaldo = esDiferenciaAceptable(saldoDec) ? 'success.main' : 'error.main';

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 3,
        borderRadius: 'var(--omni-radius-card, 16px)',
        boxShadow: 'var(--omni-shadow-card-soft, 0 2px 12px rgba(0,0,0,0.07))',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <CardContent sx={{ p: { xs: 2, md: 2.5 }, '&:last-child': { pb: { xs: 2, md: 2.5 } } }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2, mb: 2 }}>
          {/* Total documento */}
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Total Documento
            </Typography>
            <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, mt: 0.25 }}>
              {monedaBase?.codigo_iso} {toFixedStr(monto)}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {monedaPais?.codigo_iso} {toFixedStr(D(monto).times(D(tasaBCV)))}
            </Typography>
          </Box>

          {/* Total pagos + notas crédito */}
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Total Pagos{notasCreditoCount > 0 ? ` + ${notasCreditoCount} NC` : ''}
            </Typography>
            <Typography variant="h6" color={colorSaldo} sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, mt: 0.25 }}>
              {monedaBase?.codigo_iso} {toFixedStr(totalPagadoConNotasBase)}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {monedaPais?.codigo_iso} {toFixedStr(D(totalPagadoConNotasBase).times(D(tasaBCV)))}
            </Typography>
          </Box>
        </Box>

        <Divider sx={{ my: 1.5 }} />

        {/* Diferencia */}
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Diferencia (Saldo)
          </Typography>
          <Typography variant="h6" color={colorSaldo} sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, mt: 0.25 }}>
            {monedaBase?.codigo_iso} {toFixedStr(saldoDec)}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {monedaPais?.codigo_iso} {toFixedStr(saldoDec.times(D(tasaBCV)))}
          </Typography>
          {saldoDec.lt(0) && esDiferenciaAceptable(saldoDec) && (
            <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 0.5 }}>
              Diferencia negativa aceptable
            </Typography>
          )}
          {saldoDec.gt(tolDec) && (
            <Typography variant="caption" color="error" sx={{ display: 'block', mt: 0.5 }}>
              Diferencia positiva excesiva (&gt; {toFixedStr(tolDec)})
            </Typography>
          )}
          {saldoDec.gte(0) && saldoDec.lte(tolDec) && (
            <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 0.5 }}>
              Dentro de tolerancia positiva ({'≤'} {toFixedStr(tolDec)})
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

export default ResumenPago;
