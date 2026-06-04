import React from 'react';
import { Box, FormControl, InputLabel, Select, MenuItem, TextField } from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import type { Pago, MetodoPago, Moneda, CuentaBancaria, Datafono, CajaVirtual } from './types';

interface CamposDinamicosProps {
  metodoId: string;
  form: Pago;
  metodos: MetodoPago[];
  monedas: Moneda[];
  cuentasBancarias: CuentaBancaria[];
  datafonos: Datafono[];
  cajas: CajaVirtual[];
  onFormChange: (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | SelectChangeEvent<string>
  ) => void;
}

/**
 * Campos adicionales del formulario de pago que aparecen u ocultan
 * dinámicamente según el método de pago y la moneda seleccionados:
 * Caja Virtual (efectivo), Cuenta Bancaria (transferencias/cheques),
 * Datáfono (tarjetas), Banco Destino (texto libre, bancarios).
 */
const CamposDinamicos: React.FC<CamposDinamicosProps> = ({
  metodoId,
  form,
  metodos,
  monedas,
  cuentasBancarias,
  datafonos,
  cajas,
  onFormChange,
}) => {
  const metodo = metodos.find(m => m.id_metodo_pago === metodoId);
  if (!metodo) return null;

  const tipoMetodo = metodo.tipo_metodo?.toLowerCase() || '';
  const monedaSeleccionada = monedas.find(m => m.id_moneda === form.id_moneda);
  const codigoMoneda = monedaSeleccionada?.codigo_iso;

  const cuentasCompatibles = cuentasBancarias.filter(
    c =>
      c.metodos_pago?.includes(metodoId) &&
      (!codigoMoneda || c.monedas?.includes(form.id_moneda))
  );
  const datafonosCompatibles = datafonos.filter(
    d =>
      d.metodos_pago?.includes(metodoId) &&
      (!codigoMoneda || d.monedas?.includes(form.id_moneda))
  );
  const cajasCompatibles = cajas.filter(
    c => !form.id_moneda || c.id_moneda === form.id_moneda
  );

  const esEfectivo = tipoMetodo.includes('efectivo') || tipoMetodo.includes('cash');
  const esBancario =
    tipoMetodo.includes('transferencia') ||
    tipoMetodo.includes('cheque') ||
    tipoMetodo.includes('banco');
  const esTarjeta =
    tipoMetodo.includes('tarjeta') ||
    tipoMetodo.includes('debito') ||
    tipoMetodo.includes('credito');

  return (
    <>
      {esEfectivo && cajasCompatibles.length > 0 && (
        <Box sx={{ width: { xs: '100%', md: '20%' } }}>
          <FormControl fullWidth size="small">
            <InputLabel>Caja Virtual</InputLabel>
            <Select
              name="id_caja_virtual"
              value={form.id_caja_virtual ?? ''}
              onChange={onFormChange}
              label="Caja Virtual"
            >
              {cajasCompatibles.map(c => (
                <MenuItem key={c.id_caja} value={c.id_caja}>
                  {c.nombre} ({c.moneda_codigo_iso})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      {cuentasCompatibles.length > 0 && (
        <Box sx={{ width: { xs: '100%', md: '20%' } }}>
          <FormControl fullWidth size="small">
            <InputLabel>Cuenta Bancaria</InputLabel>
            <Select
              name="id_cuenta_bancaria"
              value={form.id_cuenta_bancaria ?? ''}
              onChange={onFormChange}
              label="Cuenta Bancaria"
            >
              <MenuItem value=""><em>Seleccionar cuenta bancaria</em></MenuItem>
              {cuentasCompatibles.map(cuenta => {
                const moneda = monedas.find(m => m.id_moneda === cuenta.id_moneda);
                return (
                  <MenuItem key={cuenta.id_cuenta_bancaria} value={cuenta.id_cuenta_bancaria}>
                    {cuenta.nombre_banco} – {cuenta.numero_cuenta} ({moneda?.codigo_iso ?? cuenta.id_moneda})
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
        </Box>
      )}

      {datafonosCompatibles.length > 0 && esTarjeta && (
        <Box sx={{ width: { xs: '100%', md: '20%' } }}>
          <FormControl fullWidth size="small">
            <InputLabel>Datáfono</InputLabel>
            <Select
              name="id_datafono"
              value={form.id_datafono ?? ''}
              onChange={onFormChange}
              label="Datáfono"
            >
              <MenuItem value=""><em>Seleccionar datáfono</em></MenuItem>
              {datafonosCompatibles.map(d => {
                const moneda = monedas.find(m => m.id_moneda === d.id_moneda);
                return (
                  <MenuItem key={d.id_datafono} value={d.id_datafono}>
                    {d.nombre} ({moneda?.codigo_iso ?? d.id_moneda})
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
        </Box>
      )}

      {esBancario && (
        <Box sx={{ width: { xs: '100%', md: '20%' } }}>
          <TextField
            fullWidth
            size="small"
            label="Banco Destino (opcional)"
            name="banco_destino"
            value={form.banco_destino ?? ''}
            onChange={onFormChange}
          />
        </Box>
      )}
    </>
  );
};

export default CamposDinamicos;
