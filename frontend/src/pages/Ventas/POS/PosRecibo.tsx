/**
 * Recibo imprimible de 80mm para el POS de mostrador (sub-fase 1.G).
 * Sin hardware específico todavía: CSS print + window.print(); la impresión
 * térmica nativa llega con el shell Tauri (Fase 3).
 */
import { Box, Button, Dialog, DialogActions, DialogContent, Divider, Stack, Typography } from '@mui/material';
import PrintIcon from '@mui/icons-material/Print';
import { toFixedStr } from '../../../lib/decimal';
import type { PosCartItem, PosPago } from './posTotals';
import { lineaTotal } from './posTotals';

export interface ReciboData {
  numero: string;
  fecha: string;
  empresaNombre: string;
  cajaNombre: string;
  items: PosCartItem[];
  subtotal: string;
  montoImpuesto: string;
  total: string;
  pagos: PosPago[];
  vuelto: string;
  codigoIso: string;
}

interface Props {
  open: boolean;
  recibo: ReciboData | null;
  onNuevaVenta: () => void;
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

export default function PosRecibo({ open, recibo, onNuevaVenta }: Props) {
  if (!recibo) return null;
  return (
    <Dialog open={open} maxWidth="xs" fullWidth>
      <style>{PRINT_CSS}</style>
      <DialogContent>
        <Box className="pos-recibo-80mm" sx={{ fontFamily: 'monospace', maxWidth: '80mm', mx: 'auto' }} data-testid="pos-recibo">
          <Typography align="center" sx={{ fontWeight: 'bold' }}>{recibo.empresaNombre}</Typography>
          <Typography align="center" variant="body2">Caja: {recibo.cajaNombre}</Typography>
          <Typography align="center" variant="body2">
            {recibo.numero ? `Nota de venta N° ${recibo.numero}` : 'Nota de venta'}
          </Typography>
          <Typography align="center" variant="body2">{recibo.fecha}</Typography>
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          {recibo.items.map((item) => (
            <Stack key={item.id_producto} direction="row" justifyContent="space-between" spacing={1}>
              <Typography variant="body2">
                {item.cantidad} x {item.nombre}
              </Typography>
              <Typography variant="body2">{toFixedStr(lineaTotal(item))}</Typography>
            </Stack>
          ))}
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2">Subtotal</Typography>
            <Typography variant="body2">{recibo.subtotal} {recibo.codigoIso}</Typography>
          </Stack>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2">IVA</Typography>
            <Typography variant="body2">{recibo.montoImpuesto} {recibo.codigoIso}</Typography>
          </Stack>
          <Stack direction="row" justifyContent="space-between">
            <Typography sx={{ fontWeight: 'bold' }}>TOTAL</Typography>
            <Typography sx={{ fontWeight: 'bold' }} data-testid="pos-recibo-total">
              {recibo.total} {recibo.codigoIso}
            </Typography>
          </Stack>
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          {recibo.pagos.map((p) => (
            <Stack key={p.idempotencyKey} direction="row" justifyContent="space-between">
              <Typography variant="body2">{p.nombre_metodo}</Typography>
              <Typography variant="body2">{toFixedStr(p.monto)} {p.codigo_iso}</Typography>
            </Stack>
          ))}
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2">Vuelto</Typography>
            <Typography variant="body2" data-testid="pos-recibo-vuelto">
              {recibo.vuelto} {recibo.codigoIso}
            </Typography>
          </Stack>
          <Divider sx={{ my: 1, borderStyle: 'dashed' }} />
          <Typography align="center" variant="body2">¡Gracias por su compra!</Typography>
        </Box>
      </DialogContent>
      <DialogActions className="pos-recibo-acciones">
        <Button startIcon={<PrintIcon />} onClick={() => window.print()} data-testid="pos-imprimir">
          Imprimir
        </Button>
        <Button variant="contained" onClick={onNuevaVenta} data-testid="pos-nueva-venta">
          Nueva venta
        </Button>
      </DialogActions>
    </Dialog>
  );
}
