import React from 'react';
import { Box, Typography } from '@mui/material';
import type { Moneda } from './types';

interface ResumenPagoProps {
  monto: number;
  totalPagadoConNotasBase: number;
  saldoRestante: number;
  toleranciaPositiva: number;
  notasCreditoCount: number;
  monedaBase: Moneda | undefined;
  monedaPais: Moneda | undefined;
  tasaBCV: number;
  esDiferenciaAceptable: (d: number) => boolean;
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
  const colorSaldo = esDiferenciaAceptable(saldoRestante) ? 'success.main' : 'error';

  return (
    <>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2, mb: 3 }}>
        <Box>
          <Typography variant="h6">Total Documento:</Typography>
          <Typography variant="body1">{monedaBase?.codigo_iso} {monto.toFixed(2)}</Typography>
          <Typography variant="body2" color="textSecondary">{monedaPais?.codigo_iso} {(monto * tasaBCV).toFixed(2)}</Typography>
        </Box>
        <Box>
          <Typography variant="h6" color={colorSaldo}>Total Pagos + Notas Crédito:</Typography>
          <Typography variant="body1" color={colorSaldo}>{monedaBase?.codigo_iso} {totalPagadoConNotasBase.toFixed(2)}</Typography>
          <Typography variant="body2" color="textSecondary">{monedaPais?.codigo_iso} {(totalPagadoConNotasBase * tasaBCV).toFixed(2)}</Typography>
          {notasCreditoCount > 0 && (
            <Typography variant="caption" color="info.main">Incluye {notasCreditoCount} nota(s) de crédito</Typography>
          )}
        </Box>
      </Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" color={colorSaldo}>Diferencia Total (Validación al Confirmar):</Typography>
        <Typography variant="body1" color={colorSaldo}>{monedaBase?.codigo_iso} {saldoRestante.toFixed(2)}</Typography>
        <Typography variant="body2" color="textSecondary">{monedaPais?.codigo_iso} {(saldoRestante * tasaBCV).toFixed(2)}</Typography>
        {saldoRestante < 0 && esDiferenciaAceptable(saldoRestante) && (
          <Typography variant="caption" color="success.main">✅ Diferencia negativa aceptable</Typography>
        )}
        {saldoRestante > toleranciaPositiva && (
          <Typography variant="caption" color="error">❌ Diferencia positiva excesiva (&gt; {toleranciaPositiva.toFixed(2)})</Typography>
        )}
        {saldoRestante >= 0 && saldoRestante <= toleranciaPositiva && (
          <Typography variant="caption" color="success.main">✅ Dentro de tolerancia positiva (≤ {toleranciaPositiva.toFixed(2)})</Typography>
        )}
      </Box>
    </>
  );
};

export default ResumenPago;
