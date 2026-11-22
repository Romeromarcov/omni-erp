/**
 * Diálogo de cobro del POS: pago mixto multimoneda contra el total que
 * devuelve el backend (IVA incluido). Cada pago agregado lleva su clave de
 * idempotencia generada una sola vez (PR #86/#89): un doble toque en
 * "Confirmar cobro" no puede duplicar pagos.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, IconButton, List, ListItem, ListItemText, Stack, TextField, Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import Decimal from 'decimal.js';
import { D, toFixedStr } from '../../../lib/decimal';
import { newIdempotencyKey } from '../../../lib/idempotency';
import type { MetodoPagoEmpresaActiva } from '../../../services/metodosPagoEmpresaActiva';
import type { MonedaEmpresaActiva } from '../../../services/monedasEmpresaActiva';
import {
  codigoIsoMonedaReal,
  idMetodoPagoReal,
  idMonedaReal,
  nombreMetodoPagoReal,
} from './posCatalog';
import { restantePorPagar, totalPagado, vuelto, type PosPago } from './posTotals';

interface Props {
  open: boolean;
  /** Total del documento (con IVA, según backend) en la moneda del documento. */
  total: Decimal;
  /** IVA informativo devuelto por el backend. */
  montoImpuesto: Decimal;
  codigoIsoDocumento: string;
  metodos: MetodoPagoEmpresaActiva[];
  monedas: MonedaEmpresaActiva[];
  /** Tasa USD→VES vigente (1 si no está disponible). */
  tasaBcv: string;
  /** true mientras se registran los pagos en el backend. */
  procesando: boolean;
  /** true cuando se opera sin conexión (total provisional, sin IVA calculado). */
  modoOffline?: boolean;
  error: string | null;
  onConfirm: (pagos: PosPago[], vueltoCalculado: string) => void;
  onClose: () => void;
}

export default function PosPagoDialog({
  open, total, montoImpuesto, codigoIsoDocumento, metodos, monedas, tasaBcv,
  procesando, modoOffline = false, error, onConfirm, onClose,
}: Props) {
  const [pagos, setPagos] = useState<PosPago[]>([]);
  const [idMetodo, setIdMetodo] = useState('');
  const [idMoneda, setIdMoneda] = useState('');
  const [monto, setMonto] = useState('');
  const [referencia, setReferencia] = useState('');
  const [errorForm, setErrorForm] = useState('');

  useEffect(() => {
    if (!open) {
      setPagos([]);
      setErrorForm('');
      setMonto('');
      setReferencia('');
    }
  }, [open]);

  const metodoSel = metodos.find((m) => idMetodoPagoReal(m) === idMetodo);
  // Si el método restringe monedas, solo se ofrecen esas.
  const monedasDelMetodo = useMemo(
    () =>
      metodoSel && Array.isArray(metodoSel.monedas) && metodoSel.monedas.length > 0
        ? monedas.filter((mo) => metodoSel.monedas.includes(idMonedaReal(mo)))
        : monedas,
    [metodoSel, monedas],
  );

  const restante = restantePorPagar(total, pagos, codigoIsoDocumento);
  const pagado = totalPagado(pagos, codigoIsoDocumento);
  const vueltoCalc = vuelto(total, pagos, codigoIsoDocumento);
  const cubierto = restante.isZero() && pagos.length > 0;

  const agregarPago = () => {
    const moneda = monedas.find((mo) => idMonedaReal(mo) === idMoneda);
    const metodo = metodos.find((m) => idMetodoPagoReal(m) === idMetodo);
    if (!metodo || !moneda || !monto || D(monto).lessThanOrEqualTo(0)) {
      setErrorForm('Selecciona método, moneda y un monto mayor que cero.');
      return;
    }
    const codigoMoneda = codigoIsoMonedaReal(moneda);
    setErrorForm('');
    setPagos((prev) => [
      ...prev,
      {
        idempotencyKey: newIdempotencyKey(),
        id_metodo_pago: idMetodoPagoReal(metodo),
        nombre_metodo: nombreMetodoPagoReal(metodo),
        id_moneda: idMonedaReal(moneda),
        codigo_iso: codigoMoneda,
        monto,
        tasa: codigoMoneda.toUpperCase() === codigoIsoDocumento.toUpperCase() ? '1' : tasaBcv,
        referencia: referencia || undefined,
      },
    ]);
    setMonto('');
    setReferencia('');
  };

  const quitarPago = (key: string) => {
    setPagos((prev) => prev.filter((p) => p.idempotencyKey !== key));
  };

  const handleClose = () => {
    if (procesando) return;
    setPagos([]);
    setErrorForm('');
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Cobrar venta</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Box>
            <Typography variant="h5" data-testid="pos-total-cobrar">
              Total: {toFixedStr(total)} {codigoIsoDocumento}
            </Typography>
            <Typography variant="body2" color="text.secondary" data-testid="pos-iva-cobrar">
              {modoOffline
                ? `IVA provisional: ${toFixedStr(montoImpuesto)} ${codigoIsoDocumento} (se calcula al sincronizar)`
                : `IVA incluido: ${toFixedStr(montoImpuesto)} ${codigoIsoDocumento}`}
            </Typography>
          </Box>
          {modoOffline && (
            <Alert severity="info" data-testid="pos-pago-modo-offline">
              Modo sin conexión: el total mostrado es provisional. La venta se encolará y el servidor calculará el IVA definitivo al sincronizar.
            </Alert>
          )}
          <Divider />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              select fullWidth size="small" label="Método de pago" value={idMetodo}
              onChange={(e) => setIdMetodo(e.target.value)}
              slotProps={{
                select: { native: true },
                htmlInput: { 'data-testid': 'pos-pago-metodo' },
                inputLabel: { shrink: true },
              }}
            >
              <option value="" />
              {metodos.map((m) => {
                const mId = idMetodoPagoReal(m);
                return (
                  <option key={m.id || mId} value={mId}>
                    {nombreMetodoPagoReal(m)}
                  </option>
                );
              })}
            </TextField>
            <TextField
              select fullWidth size="small" label="Moneda" value={idMoneda}
              onChange={(e) => setIdMoneda(e.target.value)}
              slotProps={{
                select: { native: true },
                htmlInput: { 'data-testid': 'pos-pago-moneda' },
                inputLabel: { shrink: true },
              }}
            >
              <option value="" />
              {monedasDelMetodo.map((mo) => {
                const moId = idMonedaReal(mo);
                return (
                  <option key={mo.id || moId} value={moId}>
                    {codigoIsoMonedaReal(mo)}
                  </option>
                );
              })}
            </TextField>
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              fullWidth size="small" label="Monto" value={monto}
              onChange={(e) => setMonto(e.target.value)}
              slotProps={{ htmlInput: { inputMode: 'decimal', 'data-testid': 'pos-pago-monto' } }}
            />
            <TextField
              fullWidth size="small" label="Referencia (opcional)" value={referencia}
              onChange={(e) => setReferencia(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'pos-pago-referencia' } }}
            />
            <Button variant="outlined" onClick={agregarPago} sx={{ whiteSpace: 'nowrap' }}>
              Agregar pago
            </Button>
          </Stack>
          {errorForm && <Alert severity="warning">{errorForm}</Alert>}

          {pagos.length > 0 && (
            <List dense data-testid="pos-pagos-lista">
              {pagos.map((p) => (
                <ListItem
                  key={p.idempotencyKey}
                  secondaryAction={
                    <IconButton edge="end" aria-label={`Quitar pago ${p.nombre_metodo}`} onClick={() => quitarPago(p.idempotencyKey)} disabled={procesando}>
                      <DeleteIcon />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={`${p.nombre_metodo} — ${toFixedStr(p.monto)} ${p.codigo_iso}`}
                    secondary={p.referencia ? `Ref: ${p.referencia}` : undefined}
                  />
                </ListItem>
              ))}
            </List>
          )}

          <Divider />
          <Stack direction="row" justifyContent="space-between">
            <Typography data-testid="pos-pagado">Pagado: {toFixedStr(pagado)} {codigoIsoDocumento}</Typography>
            <Typography data-testid="pos-restante">Restante: {toFixedStr(restante)} {codigoIsoDocumento}</Typography>
          </Stack>
          {vueltoCalc.greaterThan(0) && (
            <Alert severity="info" data-testid="pos-vuelto">
              Vuelto: {toFixedStr(vueltoCalc)} {codigoIsoDocumento}
            </Alert>
          )}
          {error && <Alert severity="error" data-testid="pos-cobro-error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={procesando}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={!cubierto || procesando}
          onClick={() => onConfirm(pagos, toFixedStr(vueltoCalc))}
          data-testid="pos-confirmar-cobro"
        >
          {procesando ? 'Procesando…' : 'Confirmar cobro'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
