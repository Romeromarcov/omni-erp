import React, { useState, useEffect, useMemo } from 'react';
import {
  Modal, Box, Typography, TextField, Button, Select, MenuItem,
  FormControl, InputLabel, IconButton, List, ListItem, ListItemText,
  Divider, Paper,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';

import type { Pago, NotaCredito, ModalPagoProps } from './types';
import { useModalPagoData } from './useModalPagoData';
import CamposDinamicos from './CamposDinamicos';
import SeccionNotasCredito from './SeccionNotasCredito';
import SeccionVuelto from './SeccionVuelto';
import ResumenPago from './ResumenPago';
import { useSnackbar } from '../../contexts/feedbackTypes';

// Re-exportar los tipos públicos que usan otros módulos
export type { Pago, NotaCredito } from './types';

const FORM_VACIO: Pago = {
  id_metodo_pago: '', id_moneda: '', monto: 0, referencia: '',
  tasa: 1, tipo_tasa: 'OFICIAL_BCV',
  id_caja_fisica: '', id_caja_virtual: '', id_cuenta_bancaria: '',
  id_datafono: '', banco_destino: '', metodo: '', moneda: '',
};

const ModalPago: React.FC<ModalPagoProps> = ({
  open,
  monto,
  onClose,
  onConfirm,
  empresaId,
  tipoDocumento,
  idDocumento: _idDocumento,
  idCliente,
  idProveedor,
  tipoOperacionInicial,
}) => {
  const snackbar = useSnackbar();
  const [pagos, setPagos] = useState<Pago[]>([]);
  const [form, setForm] = useState<Pago>(FORM_VACIO);
  const [tipoOperacion, setTipoOperacion] = useState<'INGRESO' | 'EGRESO'>(tipoOperacionInicial ?? 'INGRESO');
  const [notasCreditoSeleccionadas, setNotasCreditoSeleccionadas] = useState<NotaCredito[]>([]);
  const [mostrarVueltos, setMostrarVueltos] = useState(false);
  const [vuelto, setVuelto] = useState<Pago | null>(null);

  const { metodos, monedas, cajas, tasaBCV, toleranciaPositiva, permitirNegativas, notasCredito, cuentasBancarias, datafonos, tasaBCVNoDisponible, tasaBCVError } =
    useModalPagoData({ empresaId, idCliente, idProveedor });

  const monedaBase = useMemo(
    () => monedas.find(m => m.es_base) ?? monedas.find(m => m.codigo_iso?.toUpperCase() === 'USD'),
    [monedas]
  );
  const monedaPais = useMemo(
    () => monedas.find(m => m.es_pais) ?? monedas.find(m => m.codigo_iso?.toUpperCase() === 'VES'),
    [monedas]
  );

  useEffect(() => {
    setForm(f => f.tipo_tasa === 'OFICIAL_BCV' ? { ...f, tasa: tasaBCV } : f);
  }, [tasaBCV]);

  useEffect(() => {
    if (!tipoDocumento) return;
    const ingresos = ['PEDIDO', 'NOTA_VENTA', 'FACTURA'];
    const egresos = ['CXP', 'GASTO', 'REEMBOLSO_GASTO', 'NOMINA', 'IMPUESTO'];
    if (ingresos.includes(tipoDocumento)) setTipoOperacion('INGRESO');
    else if (egresos.includes(tipoDocumento)) setTipoOperacion('EGRESO');
  }, [tipoDocumento]);

  useEffect(() => {
    if (!form.id_metodo_pago || !cuentasBancarias.length || !datafonos.length || !cajas.length) return;

    const cuentaCompatible = cuentasBancarias.find(
      c => c.metodos_pago?.includes(form.id_metodo_pago) && c.monedas?.includes(form.id_moneda)
    );
    if (cuentaCompatible) {
      setForm(f => ({ ...f, id_cuenta_bancaria: cuentaCompatible.id_cuenta_bancaria, id_datafono: '', id_caja_virtual: '' }));
      return;
    }

    const datafonoCompatible = datafonos.find(
      d => d.metodos_pago?.includes(form.id_metodo_pago) && d.monedas?.includes(form.id_moneda)
    );
    if (datafonoCompatible) {
      setForm(f => ({ ...f, id_datafono: datafonoCompatible.id_datafono, id_cuenta_bancaria: '', id_caja_virtual: '' }));
      return;
    }

    const metodo = metodos.find(m => m.id_metodo_pago === form.id_metodo_pago);
    if (metodo?.tipo_metodo?.toLowerCase().includes('efectivo')) {
      const cajaCompatible = cajas.find(c => c.moneda_codigo_iso === form.moneda);
      if (cajaCompatible) {
        setForm(f => ({ ...f, id_caja_virtual: cajaCompatible.id_caja, id_cuenta_bancaria: '', id_datafono: '' }));
        return;
      }
    }
    setForm(f => ({ ...f, id_cuenta_bancaria: '', id_datafono: '', id_caja_virtual: '' }));
  }, [form.id_metodo_pago, form.metodo, form.id_moneda, form.moneda, cuentasBancarias, datafonos, cajas, metodos]);

  const conversiones = useMemo(
    () => (montoVal: number, tasa: number, monedaId: string) => {
      if (!monedaBase || !monedaPais) return { base: 0, pais: 0 };
      if (monedaId === monedaBase.codigo_iso) return { base: montoVal, pais: montoVal * tasa };
      if (monedaId === monedaPais.codigo_iso) return { base: montoVal / tasa, pais: montoVal };
      const base = montoVal / tasa;
      return { base, pais: base * tasaBCV };
    },
    [monedaBase, monedaPais, tasaBCV]
  );

  const totalPagadoBase = useMemo(
    () => pagos.reduce((acc, p) => acc + (p.monto_base ?? 0), 0),
    [pagos]
  );
  const totalNotasCreditoBase = useMemo(
    () => notasCreditoSeleccionadas.reduce((total, nota) => {
      const tasa = nota.id_moneda === monedaBase?.id_moneda ? 1
        : nota.id_moneda === monedaPais?.id_moneda ? 1 / tasaBCV
        : tasaBCV;
      return total + nota.monto_disponible * tasa;
    }, 0),
    [notasCreditoSeleccionadas, monedaBase, monedaPais, tasaBCV]
  );

  const totalPagadoConNotasBase = totalPagadoBase + totalNotasCreditoBase;
  const saldoRestanteConNotasBase = monto - totalPagadoConNotasBase;

  const calcularVueltoDisponible = () => Math.max(0, totalPagadoConNotasBase - monto);
  const esDiferenciaAceptable = (diferencia: number) =>
    diferencia > 0 ? diferencia <= toleranciaPositiva : permitirNegativas;

  const handleFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | SelectChangeEvent<string>
  ) => {
    const { name, value } = e.target;
    if (name === 'tasa') { setForm(f => ({ ...f, tasa: Number(value), tipo_tasa: 'MANUAL' })); return; }
    if (name === 'id_moneda') {
      const monedaSel = monedas.find(m => m.id_moneda === value);
      setForm(f => ({ ...f, id_moneda: value, moneda: monedaSel?.codigo_iso ?? value }));
      return;
    }
    if (name === 'id_metodo_pago') {
      const metodoSel = metodos.find(m => m.id_metodo_pago === value);
      setForm(f => ({ ...f, id_metodo_pago: value, metodo: metodoSel?.nombre_metodo ?? value }));
      return;
    }
    setForm(f => ({ ...f, [name]: name === 'monto' ? Number(value) : value }));
  };

  const handleAddPago = () => {
    if (!form.id_metodo_pago || !form.id_moneda || !form.monto || form.monto <= 0) {
      snackbar.warning('Por favor, complete todos los campos obligatorios del pago.');
      return;
    }
    const metodo = metodos.find(m => m.id_metodo_pago === form.id_metodo_pago);
    if (!metodo) { snackbar.warning('Método de pago no válido.'); return; }
    const tipo = metodo.tipo_metodo?.toLowerCase() ?? '';
    if ((tipo.includes('efectivo') || tipo.includes('cash')) && !form.id_caja_virtual) {
      snackbar.warning('Para pagos en efectivo, debe seleccionar una caja virtual.'); return;
    }
    if ((tipo.includes('transferencia') || tipo.includes('cheque') || tipo.includes('banco')) && !form.id_cuenta_bancaria) {
      snackbar.warning('Para este método de pago, debe seleccionar una cuenta bancaria.'); return;
    }
    if ((tipo.includes('tarjeta') || tipo.includes('debito') || tipo.includes('credito')) && !form.id_datafono) {
      snackbar.warning('Para pagos con tarjeta, debe seleccionar un datáfono.'); return;
    }
    if (!form.id_caja_virtual && !form.id_cuenta_bancaria && !form.id_datafono) {
      snackbar.warning('Debe seleccionar al menos una entidad financiera para el pago.'); return;
    }
    const conv = conversiones(form.monto, form.tasa, form.moneda ?? '');
    setPagos(prev => [...prev, { ...form, monto_base: conv.base, monto_pais: conv.pais }]);
    setForm({ ...FORM_VACIO, tasa: tasaBCV });
  };

  const handleRemovePago = (idx: number) => setPagos(prev => prev.filter((_, i) => i !== idx));

  const handleConfigurarVuelto = () => {
    const vueltoDisponible = calcularVueltoDisponible();
    if (vueltoDisponible <= 0) return;
    setMostrarVueltos(true);
    const monedaVuelto = monedaPais?.codigo_iso ?? 'VES';
    const tasaVuelto = monedaVuelto === monedaBase?.codigo_iso ? 1 : tasaBCV;
    setVuelto({
      id_metodo_pago: 'efectivo',
      id_moneda: monedaVuelto,
      monto: vueltoDisponible / tasaVuelto,
      tasa: tasaVuelto,
      referencia: 'Vuelto automático',
      observaciones: 'Vuelto generado automáticamente por pago excedente',
      id_caja_virtual: form.id_caja_virtual,
    });
  };

  if (!open) return null;

  const vueltoDisponible = calcularVueltoDisponible();

  return (
    <Modal open={open} onClose={onClose}>
      <Paper sx={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '80%', maxWidth: 900,
        bgcolor: 'background.paper', boxShadow: 24, p: 4,
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        <Typography variant="h5" component="h2" gutterBottom>
          Registrar Pago (Validación al Confirmar)
        </Typography>
        <Divider sx={{ my: 2 }} />

        {/* Tipo de operación */}
        <Box sx={{ mb: 3 }}>
          <FormControl fullWidth>
            <InputLabel>Tipo de Operación</InputLabel>
            <Select
              value={tipoOperacion}
              onChange={e => setTipoOperacion(e.target.value as 'INGRESO' | 'EGRESO')}
              label="Tipo de Operación"
            >
              <MenuItem value="INGRESO">INGRESO</MenuItem>
              <MenuItem value="EGRESO">EGRESO</MenuItem>
            </Select>
          </FormControl>
          {tipoDocumento && (
            <Typography variant="caption" color="textSecondary" sx={{ mt: 1 }}>
              Detectado automáticamente del documento: {tipoDocumento}
            </Typography>
          )}
        </Box>

        <ResumenPago
          monto={monto}
          totalPagadoConNotasBase={totalPagadoConNotasBase}
          saldoRestante={saldoRestanteConNotasBase}
          toleranciaPositiva={toleranciaPositiva}
          notasCreditoCount={notasCreditoSeleccionadas.length}
          monedaBase={monedaBase}
          monedaPais={monedaPais}
          tasaBCV={tasaBCV}
          esDiferenciaAceptable={esDiferenciaAceptable}
        />

        {/* Notas de crédito */}
        <SeccionNotasCredito
          notasCredito={notasCredito}
          notasCreditoSeleccionadas={notasCreditoSeleccionadas}
          monedas={monedas}
          monedaBase={monedaBase}
          monedaPais={monedaPais}
          tasaBCV={tasaBCV}
          onToggle={nota =>
            setNotasCreditoSeleccionadas(prev =>
              prev.some(nc => nc.id_nota_credito === nota.id_nota_credito)
                ? prev.filter(nc => nc.id_nota_credito !== nota.id_nota_credito)
                : [...prev, nota]
            )
          }
        />

        {/* Formulario de nuevo pago */}
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          <Box sx={{ width: { xs: '100%', md: '20%' } }}>
            <FormControl fullWidth>
              <InputLabel>Método</InputLabel>
              <Select name="id_metodo_pago" value={form.id_metodo_pago} onChange={handleFormChange}>
                {metodos.map(m => <MenuItem key={m.id_metodo_pago} value={m.id_metodo_pago}>{m.nombre_metodo}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <FormControl fullWidth>
              <InputLabel>Moneda</InputLabel>
              <Select name="id_moneda" value={form.id_moneda} onChange={handleFormChange}>
                {monedas.map(m => <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <TextField fullWidth label={`Tasa → ${monedaBase?.codigo_iso ?? 'BASE'}`} name="tasa" type="number" value={form.tasa} onChange={handleFormChange} />
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <TextField fullWidth label="Monto" name="monto" type="number" value={form.monto} onChange={handleFormChange} />
          </Box>
          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <TextField fullWidth label="Referencia" name="referencia" value={form.referencia ?? ''} onChange={handleFormChange} />
          </Box>

          {form.id_metodo_pago && form.id_moneda && (
            <CamposDinamicos
              metodoId={form.id_metodo_pago}
              form={form}
              metodos={metodos}
              monedas={monedas}
              cuentasBancarias={cuentasBancarias}
              datafonos={datafonos}
              cajas={cajas}
              onFormChange={handleFormChange}
            />
          )}

          <Box sx={{ width: { xs: '100%', md: '15%' } }}>
            <Button
              fullWidth variant="contained"
              onClick={handleAddPago}
              disabled={!form.id_metodo_pago || !form.id_moneda || !form.monto || form.monto <= 0}
            >
              Agregar
            </Button>
          </Box>
        </Box>

        {/* Vuelto */}
        <SeccionVuelto
          vueltoDisponible={vueltoDisponible}
          mostrarVueltos={mostrarVueltos}
          vuelto={vuelto}
          monedas={monedas}
          monedaBase={monedaBase}
          onConfigurar={handleConfigurarVuelto}
          onMonedaChange={id => setVuelto(prev => prev ? { ...prev, id_moneda: id } : null)}
          onMontoChange={val => setVuelto(prev => prev ? { ...prev, monto: val } : null)}
          onTasaChange={val => setVuelto(prev => prev ? { ...prev, tasa: val } : null)}
          onConfirmarVuelto={() => { /* lógica adicional de vuelto si aplica */ }}
          onCancelar={() => setMostrarVueltos(false)}
        />

        {/* Lista de pagos */}
        <List sx={{ mt: 3 }}>
          {pagos.map((p, idx) => (
            <ListItem
              key={idx} divider
              secondaryAction={
                <IconButton edge="end" aria-label="delete" onClick={() => handleRemovePago(idx)}>
                  <DeleteIcon />
                </IconButton>
              }
            >
              <ListItemText
                primary={`${metodos.find(m => m.id_metodo_pago === p.id_metodo_pago)?.nombre_metodo} – ${p.referencia}`}
                secondary={`Monto: ${monedas.find(m => m.codigo_iso === p.moneda)?.codigo_iso} ${p.monto.toFixed(2)} | Base: ${monedaBase?.codigo_iso} ${p.monto_base?.toFixed(2)} | País: ${monedaPais?.codigo_iso} ${p.monto_pais?.toFixed(2)}`}
              />
            </ListItem>
          ))}
        </List>

        <Divider sx={{ my: 2 }} />

        {/* Acciones */}
        {tasaBCVError && (
          <Typography color="error" variant="body2" sx={{ mt: 2 }}>
            No se pudo cargar la tasa BCV. No es posible confirmar pagos hasta que la tasa esté disponible.
          </Typography>
        )}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 3 }}>
          <Button onClick={onClose} sx={{ mr: 1 }}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (!esDiferenciaAceptable(saldoRestanteConNotasBase)) {
                snackbar.warning(`El total de pagos tiene una diferencia que excede la tolerancia configurada (${toleranciaPositiva.toFixed(2)}). No se pueden confirmar los pagos.`);
                return;
              }
              onConfirm(pagos, vuelto ? [vuelto] : undefined, notasCreditoSeleccionadas);
            }}
            disabled={tasaBCVNoDisponible || (pagos.length === 0 && notasCreditoSeleccionadas.length === 0)}
          >
            Confirmar pagos
          </Button>
        </Box>
      </Paper>
    </Modal>
  );
};

export default ModalPago;
