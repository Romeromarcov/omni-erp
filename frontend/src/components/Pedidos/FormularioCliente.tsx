import React from 'react';
import {
  Box, TextField, Button, MenuItem, Select, FormControl, InputLabel,
  Grid,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import SectionTitle from '../ui/SectionTitle';

interface FormularioClienteProps {
  clienteManual: { razon_social: string; rif: string; telefono: string; direccion?: string; correo?: string; codigo_cliente?: string };
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onBlur: () => void;
  onBuscar: () => void;
}

const FormularioCliente: React.FC<FormularioClienteProps> = ({ clienteManual, onChange, onKeyDown, onBlur, onBuscar }) => (
  <Box
    sx={{
      border: '1px solid',
      borderColor: 'divider',
      borderRadius: 'var(--omni-radius-card, 16px)',
      p: { xs: 2, md: 2.5 },
      mb: 2,
    }}
  >
    <SectionTitle action={
      <Button type="button" variant="outlined" size="small" onClick={onBuscar}>
        Buscar cliente existente
      </Button>
    }>
      Datos del cliente
    </SectionTitle>

    <Grid container spacing={2}>
      <Grid size={{ xs: 12, sm: clienteManual.codigo_cliente ? 6 : 12 }}>
        <TextField
          fullWidth
          size="small"
          label="Razón Social"
          name="razon_social"
          value={clienteManual.razon_social}
          onChange={onChange as React.ChangeEventHandler<HTMLInputElement>}
          onKeyDown={onKeyDown}
          onBlur={onBlur}
          required
        />
      </Grid>

      {clienteManual.codigo_cliente && (
        <Grid size={{ xs: 12, sm: 6 }}>
          <TextField
            fullWidth
            size="small"
            label="Código de Cliente"
            name="codigo_cliente"
            value={clienteManual.codigo_cliente}
            InputProps={{ readOnly: true }}
          />
        </Grid>
      )}

      {/* RIF */}
      <Grid size={{ xs: 12, sm: 6 }}>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel>Tipo RIF</InputLabel>
            <Select
              name="rif_prefijo"
              value={clienteManual.rif.split('-')[0] || ''}
              onChange={(e: SelectChangeEvent<string>) => onChange({ target: { name: e.target.name, value: e.target.value } } as React.ChangeEvent<HTMLSelectElement>)}
              label="Tipo RIF"
              required
            >
              <MenuItem value="">Seleccione</MenuItem>
              <MenuItem value="V">V — Persona</MenuItem>
              <MenuItem value="J">J — Empresa</MenuItem>
              <MenuItem value="E">E — Extranjero</MenuItem>
              <MenuItem value="G">G — Gobierno</MenuItem>
              <MenuItem value="P">P — Pasaporte</MenuItem>
            </Select>
          </FormControl>
          <TextField
            fullWidth
            size="small"
            label="Número RIF"
            name="rif_numero"
            value={clienteManual.rif.split('-')[1] || ''}
            onChange={(e) => {
              const value = e.target.value.replace(/\D/g, '');
              onChange({ ...e, target: { ...e.target, value, name: 'rif_numero' } } as React.ChangeEvent<HTMLInputElement>);
            }}
            onKeyDown={onKeyDown}
            onBlur={onBlur}
            placeholder="Número"
            required
          />
        </Box>
      </Grid>

      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField
          fullWidth
          size="small"
          label="Teléfono"
          name="telefono"
          value={clienteManual.telefono}
          onChange={onChange as React.ChangeEventHandler<HTMLInputElement>}
          required
        />
      </Grid>

      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField
          fullWidth
          size="small"
          label="Dirección (opcional)"
          name="direccion"
          value={clienteManual.direccion || ''}
          onChange={onChange as React.ChangeEventHandler<HTMLInputElement>}
        />
      </Grid>

      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField
          fullWidth
          size="small"
          label="Correo electrónico (opcional)"
          name="correo"
          type="email"
          value={clienteManual.correo || ''}
          onChange={onChange as React.ChangeEventHandler<HTMLInputElement>}
        />
      </Grid>
    </Grid>
  </Box>
);

export default FormularioCliente;
