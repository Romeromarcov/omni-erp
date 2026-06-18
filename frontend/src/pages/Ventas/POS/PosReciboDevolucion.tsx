/**
 * Recibo imprimible de 80mm para DEVOLUCIONES del POS (sub-fase 1.G).
 * Mismo patrón del recibo de venta (PosRecibo): CSS print + window.print();
 * la impresión térmica nativa llega con el shell Tauri (Fase 3).
 */
import { Box, Button, Dialog, DialogActions, DialogContent, Divider, Stack, Typography } from '@mui/material';
import PrintIcon from '@mui/icons-material/Print';
import { useTranslation } from 'react-i18next';
import { D, toFixedStr } from '../../../lib/decimal';
import type { ReciboDevolucionData } from './PosDevolucionDialog';

interface Props {
  open: boolean;
  recibo: ReciboDevolucionData | null;
  empresaNombre: string;
  onCerrar: () => void;
}

/** Solo el recibo es visible al imprimir, en ancho de rollo térmico de 80mm. */
const PRINT_CSS = `
@media print {
  body * { visibility: hidden !important; }
  .pos-recibo-80mm, .pos-recibo-80mm * { visibility: visible !important; }
  .pos-recibo-80mm {
    position: absolute !important;
    left: 0; top: 0;
    width: 80mm !important;
    padding: 2mm !important;
  }
}
`;

export default function PosReciboDevolucion({ open, recibo, empresaNombre, onCerrar }: Props) {
  const { t } = useTranslation();
  if (!recibo) return null;
  const { resultado, venta, items, codigoIso } = recibo;
  const nc = resultado.nota_credito_fiscal ?? resultado.nota_credito_venta;
  return (
    <Dialog open={open} maxWidth="xs" fullWidth>
      <style>{PRINT_CSS}</style>
      <DialogContent>
        <Box className="pos-recibo-80mm" sx={{ fontFamily: 'monospace', maxWidth: '80mm', mx: 'auto' }} data-testid="pos-dev-recibo">
          <Typography align="center" sx={{ fontWeight: 'bold' }}>{empresaNombre}</Typography>
          <Typography align="center" variant="body2">
            {t('ventas.pos.reciboDevolucion.caja', { nombre: resultado.caja_fisica })}
          </Typography>
          <Typography align="center" sx={{ fontWeight: 'bold' }}>
            {t('ventas.pos.reciboDevolucion.titulo', { numero: resultado.devolucion.numero_devolucion })}
          </Typography>
          <Typography align="center" variant="body2">
            {t('ventas.pos.reciboDevolucion.ventaOriginal', { numero: venta.numero_nota })}
          </Typography>
          {nc && (
            <Typography align="center" variant="body2" data-testid="pos-dev-recibo-nc">
              {t('ventas.pos.reciboDevolucion.notaCredito', { numero: nc.numero_nota_credito })}
            </Typography>
          )}
          {resultado.nota_credito_fiscal && (
            <Typography align="center" variant="body2">
              {t('ventas.pos.reciboDevolucion.control', { numero: resultado.nota_credito_fiscal.numero_control })}
            </Typography>
          )}
          <Typography align="center" variant="body2">{new Date().toLocaleString()}</Typography>
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          {items.map((item) => (
            <Stack key={item.id_detalle} direction="row" justifyContent="space-between" spacing={1}>
              <Typography variant="body2">
                {item.cantidad} x {item.nombre}
              </Typography>
              <Typography variant="body2">{toFixedStr(D(item.cantidad).times(D(item.precio)))}</Typography>
            </Stack>
          ))}
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          {resultado.nota_credito_fiscal && (
            <>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="body2">Subtotal</Typography>
                <Typography variant="body2">
                  {toFixedStr(resultado.nota_credito_fiscal.base_imponible)} {codigoIso}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="body2">IVA</Typography>
                <Typography variant="body2">
                  {toFixedStr(resultado.nota_credito_fiscal.monto_iva)} {codigoIso}
                </Typography>
              </Stack>
            </>
          )}
          <Stack direction="row" justifyContent="space-between">
            <Typography sx={{ fontWeight: 'bold' }}>{t('ventas.pos.reciboDevolucion.reembolsado')}</Typography>
            <Typography sx={{ fontWeight: 'bold' }} data-testid="pos-dev-recibo-total">
              {toFixedStr(resultado.monto_reembolsado)} {codigoIso}
            </Typography>
          </Stack>
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          <Typography align="center" variant="body2">{t('ventas.pos.reciboDevolucion.pie')}</Typography>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button startIcon={<PrintIcon />} onClick={() => window.print()} data-testid="pos-dev-imprimir">
          {t('ventas.pos.reciboDevolucion.imprimir')}
        </Button>
        <Button variant="contained" onClick={onCerrar} data-testid="pos-dev-cerrar">
          {t('ventas.pos.reciboDevolucion.cerrar')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
