import React from 'react';
import { Box, Typography, Button, FormControl, InputLabel, Select, MenuItem, TextField } from '@mui/material';
import type { Pago, Moneda } from './types';

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
    <Box sx={{ mb: 3, p: 2, bgcolor: 'warning.light', borderRadius: 1 }}>
      <Typography variant="h6" color="warning.dark" gutterBottom>
        💰 Vuelto Disponible: {monedaBase?.codigo_iso} {vueltoDisponible.toFixed(2)}
      </Typography>

      {!mostrarVueltos ? (
        <Button variant="outlined" color="warning" onClick={onConfigurar}>
          Configurar Vuelto
        </Button>
      ) : (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center', mt: 2 }}>
          <Typography variant="body2">Entregar vuelto en:</Typography>

          <FormControl sx={{ minWidth: 120 }}>
            <InputLabel>Moneda</InputLabel>
            <Select
              value={vuelto?.id_moneda ?? ''}
              onChange={e => onMonedaChange(e.target.value)}
              size="small"
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

          <Button variant="contained" color="success" size="small" onClick={onConfirmarVuelto}>
            Confirmar Vuelto
          </Button>
          <Button variant="outlined" size="small" onClick={onCancelar}>
            Cancelar
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default SeccionVuelto;
