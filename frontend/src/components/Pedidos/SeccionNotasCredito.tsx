import React from 'react';
import { Box, Typography, List, ListItem, ListItemText, Button, Card, CardContent } from '@mui/material';
import type { NotaCredito, Moneda } from './types';
import SectionTitle from '../ui/SectionTitle';
import StatusChip from '../ui/StatusChip';

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
  monedaPais: _monedaPais,
  tasaBCV: _tasaBCV,
  onToggle,
}) => {
  if (notasCredito.length === 0) return null;

  const totalSeleccionadoBase = notasCreditoSeleccionadas.reduce((total, nota) => {
    const tasaConversion =
      nota.id_moneda === monedaBase?.id_moneda ? 1
      : nota.id_moneda === _monedaPais?.id_moneda ? 1 / _tasaBCV
      : _tasaBCV;
    return total + nota.monto_disponible * tasaConversion;
  }, 0);

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
        <SectionTitle>Notas de Crédito Disponibles</SectionTitle>
        <List dense disablePadding>
          {notasCredito.map(nota => {
            const seleccionada = notasCreditoSeleccionadas.some(
              nc => nc.id_nota_credito === nota.id_nota_credito
            );
            const codigoMoneda = monedas.find(m => m.id_moneda === nota.id_moneda)?.codigo_iso;
            return (
              <ListItem
                key={nota.id_nota_credito}
                sx={{ px: 0, py: 0.75 }}
                secondaryAction={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <StatusChip value={seleccionada ? 'seleccionada' : 'pendiente'} />
                    <Button
                      size="small"
                      variant={seleccionada ? 'contained' : 'outlined'}
                      onClick={() => onToggle(nota)}
                    >
                      {seleccionada ? 'Quitar' : 'Aplicar'}
                    </Button>
                  </Box>
                }
              >
                <ListItemText
                  primary={`${nota.numero_nota} — ${codigoMoneda} ${nota.monto_disponible.toFixed(2)}`}
                  secondary={[
                    `Emisión: ${new Date(nota.fecha_emision).toLocaleDateString()}`,
                    nota.fecha_vencimiento
                      ? ` | Vence: ${new Date(nota.fecha_vencimiento).toLocaleDateString()}`
                      : '',
                  ].join('')}
                  slotProps={{ primary: { sx: { fontWeight: 600, fontSize: 14 } }, secondary: { sx: { fontSize: 12 } } }}
                />
              </ListItem>
            );
          })}
        </List>

        {notasCreditoSeleccionadas.length > 0 && (
          <Typography variant="body2" color="primary" sx={{ mt: 1.5, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
            Total aplicado: {monedaBase?.codigo_iso} {totalSeleccionadoBase.toFixed(2)}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default SeccionNotasCredito;
