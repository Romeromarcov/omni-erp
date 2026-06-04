import React from 'react';
import { Box, Typography, Button, FormControl, InputLabel, Select, MenuItem, TextField, Card, CardContent } from '@mui/material';
import type { Pago, Moneda } from './types';
import SectionTitle from '../ui/SectionTitle';

interface SeccionVueltoProps {
  vueltoDisponible: number;
  mostrarVueltos: boolean;
  vuelto: Pago | null;
  monedas: Moneda[];
  monedaBase: Moneda | undefined;
  onConfigurar: () => void;
  onMonedaChange: (monedaId: string) => void;
  onMontoChange: (monto: number) => void;
  onTasaChange: (tasa: number) => void;
  onConfirmarVuelto: () => void;
  onCancelar: () => void;
}

/**
 * Sección de vuelto: se muestra solo cuando el total de pagos supera
 * el monto del documento. Permite configurar moneda, monto y tasa
 * del vuelto a entregar.
 */
const SeccionVuelto: React.FC<SeccionVueltoProps> = ({
  vueltoDisponible,
  mostrarVueltos,
  vuelto,
  monedas,
  monedaBase,
  onConfigurar,
  onMonedaChange,
  onMontoChange,
  onTasaChange,
  onConfirmarVuelto,
  onCancelar,
}) => {
  if (vueltoDisponible <= 0) return null;

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 3,
        mt: 2,
        borderRadius: 'var(--omni-radius-card, 16px)',
        border: '1px solid',
        borderColor: 'warning.light',
        bgcolor: 'warning.50',
        boxShadow: 'none',
      }}
    >
      <CardContent sx={{ p: { xs: 2, md: 2.5 }, '&:last-child': { pb: { xs: 2, md: 2.5 } } }}>
        <SectionTitle>
          <Typography component="span" color="warning.dark" sx={{ fontWeight: 700, fontSize: 15 }}>
            Vuelto disponible: {monedaBase?.codigo_iso} {vueltoDisponible.toFixed(2)}
          </Typography>
        </SectionTitle>

        {!mostrarVueltos ? (
          <Button variant="outlined" color="warning" size="small" onClick={onConfigurar}>
            Configurar vuelto
          </Button>
        ) : (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', mt: 1 }}>
            <Typography variant="body2" color="text.secondary" sx={{ width: '100%' }}>
              Entregar vuelto en:
            </Typography>

            <FormControl sx={{ minWidth: 120 }} size="small">
              <InputLabel>Moneda</InputLabel>
              <Select
                value={vuelto?.id_moneda ?? ''}
                onChange={e => onMonedaChange(e.target.value)}
                label="Moneda"
              >
                {monedas.map(m => (
                  <MenuItem key={m.id_moneda} value={m.codigo_iso}>
                    {m.codigo_iso}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              label="Monto"
              type="number"
              value={vuelto?.monto ?? 0}
              onChange={e => onMontoChange(Number(e.target.value))}
              size="small"
              sx={{ width: 120 }}
            />

            <TextField
              label="Tasa"
              type="number"
              value={vuelto?.tasa ?? 1}
              onChange={e => onTasaChange(Number(e.target.value))}
              size="small"
              sx={{ width: 100 }}
            />

            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button variant="contained" color="success" size="small" onClick={onConfirmarVuelto}>
                Confirmar vuelto
              </Button>
              <Button variant="outlined" size="small" onClick={onCancelar}>
                Cancelar
              </Button>
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default SeccionVuelto;
