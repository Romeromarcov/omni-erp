import React from 'react';
import { Box, Typography, List, ListItem, ListItemText, Button } from '@mui/material';
import type { NotaCredito, Moneda } from './types';

interface SeccionNotasCreditoProps {
  notasCredito: NotaCredito[];
  notasCreditoSeleccionadas: NotaCredito[];
  monedas: Moneda[];
  monedaBase: Moneda | undefined;
  monedaPais: Moneda | undefined;
  tasaBCV: number;
  onToggle: (nota: NotaCredito) => void;
}

/**
 * Lista de notas de crédito disponibles para el cliente/proveedor.
 * Permite seleccionar/deseleccionar cada nota. Solo se renderiza
 * si hay al menos una nota disponible.
 */
const SeccionNotasCredito: React.FC<SeccionNotasCreditoProps> = ({
  notasCredito,
  notasCreditoSeleccionadas,
  monedas,
  monedaBase,
  monedaPais,
  tasaBCV,
  onToggle,
}) => {
  if (notasCredito.length === 0) return null;

  const totalSeleccionadoBase = notasCreditoSeleccionadas.reduce((total, nota) => {
    const tasaConversion =
      nota.id_moneda === monedaBase?.id_moneda ? 1
      : nota.id_moneda === monedaPais?.id_moneda ? 1 / tasaBCV
      : tasaBCV;
    return total + nota.monto_disponible * tasaConversion;
  }, 0);

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="h6" gutterBottom>
        Notas de Crédito Disponibles
      </Typography>
      <List dense>
        {notasCredito.map(nota => {
          const seleccionada = notasCreditoSeleccionadas.some(
            nc => nc.id_nota_credito === nota.id_nota_credito
          );
          const codigoMoneda = monedas.find(m => m.id_moneda === nota.id_moneda)?.codigo_iso;
          return (
            <ListItem key={nota.id_nota_credito}>
              <ListItemText
                primary={`${nota.numero_nota} – ${codigoMoneda} ${nota.monto_disponible.toFixed(2)}`}
                secondary={[
                  `Emisión: ${new Date(nota.fecha_emision).toLocaleDateString()}`,
                  nota.fecha_vencimiento
                    ? ` | Vence: ${new Date(nota.fecha_vencimiento).toLocaleDateString()}`
                    : '',
                ].join('')}
              />
              <Button
                size="small"
                variant={seleccionada ? 'contained' : 'outlined'}
                onClick={() => onToggle(nota)}
              >
                {seleccionada ? 'Seleccionada' : 'Seleccionar'}
              </Button>
            </ListItem>
          );
        })}
      </List>

      {notasCreditoSeleccionadas.length > 0 && (
        <Typography variant="body2" color="primary" sx={{ mt: 1 }}>
          Total notas de crédito seleccionadas:{' '}
          {monedaBase?.codigo_iso} {totalSeleccionadoBase.toFixed(2)}
        </Typography>
      )}
    </Box>
  );
};

export default SeccionNotasCredito;
