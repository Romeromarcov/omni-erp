/**
 * Sub-fase 1.G — Devolución desde el POS.
 *
 * Flujo mínimo de mostrador: buscar la venta por número (lector/teclado) →
 * seleccionar líneas/cantidades a devolver (capadas a lo disponible, con
 * decimal.js) → elegir almacén de reingreso y método de reembolso →
 * confirmar. El POST lleva una Idempotency-Key estable por intento (es
 * dinero: un reintento no duplica la devolución).
 */
import { useMemo, useRef, useState } from 'react';
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, Stack, TextField, Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import Decimal from 'decimal.js';
import { D, toFixedStr } from '../../../lib/decimal';
import { newIdempotencyKey } from '../../../lib/idempotency';
import { almacenesService } from '../../../services/almacenesService';
import type { MetodoPagoEmpresaActiva } from '../../../services/metodosPagoEmpresaActiva';
import {
  buscarVentaPorNumero,
  devolverVenta,
  getEstadoDevoluciones,
  type DevolucionCreada,
  type EstadoDevolucionesVenta,
} from '../../../services/devolucionesPos';

const MOTIVOS = ['CAMBIO_CLIENTE', 'DEFECTO', 'GARANTIA', 'ERROR_ENTREGA', 'VENCIMIENTO', 'OTRO'] as const;

export interface ReciboDevolucionData {
  resultado: DevolucionCreada;
  venta: EstadoDevolucionesVenta['venta'];
  items: Array<{ id_detalle: string; nombre: string; cantidad: string; precio: string }>;
  codigoIso: string;
}

interface Props {
  open: boolean;
  /** Moneda de despliegue del POS (informativa, p. ej. VES). */
  codigoIsoDocumento: string;
  metodos: MetodoPagoEmpresaActiva[];
  onClose: () => void;
  /** Devolución registrada: el POS muestra el recibo 80mm. */
  onRegistrada: (recibo: ReciboDevolucionData) => void;
}

/** Extrae un mensaje legible del Error JSON que construye services/api. */
function mensajeDeError(err: unknown): string | null {
  if (!(err instanceof Error)) return null;
  try {
    const parsed: unknown = JSON.parse(err.message);
    if (Array.isArray(parsed)) return parsed.map(String).join(' ');
    if (parsed && typeof parsed === 'object') {
      const valores = Object.values(parsed as Record<string, unknown>).flat();
      if (valores.length > 0) return valores.map(String).join(' ');
    }
  } catch {
    // mensaje no-JSON: se usa el genérico
  }
  return null;
}

export default function PosDevolucionDialog({
  open, codigoIsoDocumento, metodos, onClose, onRegistrada,
}: Props) {
  const { t } = useTranslation();
  // Clave estable por intento de devolución (se renueva al cambiar de venta).
  const idemKeyRef = useRef<string | null>(null);

  const [numero, setNumero] = useState('');
  const [estado, setEstado] = useState<EstadoDevolucionesVenta | null>(null);
  const [cantidades, setCantidades] = useState<Record<string, string>>({});
  const [idAlmacen, setIdAlmacen] = useState('');
  const [idMetodo, setIdMetodo] = useState('');
  const [motivo, setMotivo] = useState<string>('CAMBIO_CLIENTE');
  const [aviso, setAviso] = useState('');
  const [error, setError] = useState('');
  const [buscando, setBuscando] = useState(false);
  const [procesando, setProcesando] = useState(false);

  const { data: almacenes = [] } = useQuery({
    queryKey: ['pos', 'almacenes'],
    queryFn: () => almacenesService.getAll(),
    enabled: open,
  });
  // Un solo almacén (caso típico de mostrador): se preselecciona.
  const almacenEfectivo = idAlmacen || (almacenes.length === 1 ? almacenes[0].id_almacen : '');

  const buscar = async () => {
    const q = numero.trim();
    if (!q) return;
    setBuscando(true);
    setError('');
    setAviso('');
    setEstado(null);
    setCantidades({});
    try {
      const venta = await buscarVentaPorNumero(q);
      if (!venta) {
        setAviso(t('ventas.pos.devolucion.noEncontrada', { numero: q }));
        return;
      }
      const detalle = await getEstadoDevoluciones(venta.id_nota_venta);
      setEstado(detalle);
      idemKeyRef.current = newIdempotencyKey();
      if (!detalle.lineas.some((l) => D(l.cantidad_disponible).greaterThan(0))) {
        setAviso(t('ventas.pos.devolucion.nadaDevolvible'));
      }
    } catch (err) {
      setError(mensajeDeError(err) ?? t('ventas.pos.devolucion.errorRegistro'));
    } finally {
      setBuscando(false);
    }
  };

  const totalReembolso: Decimal = useMemo(() => {
    if (!estado) return new Decimal(0);
    return estado.lineas.reduce((acc, linea) => {
      const cantidad = D(cantidades[linea.id_detalle]);
      return cantidad.greaterThan(0) ? acc.plus(cantidad.times(D(linea.precio_unitario))) : acc;
    }, new Decimal(0));
  }, [estado, cantidades]);

  const confirmar = async () => {
    if (!estado) return;
    setError('');
    const lineas: Array<{ id_detalle: string; cantidad: string }> = [];
    for (const linea of estado.lineas) {
      const bruto = (cantidades[linea.id_detalle] ?? '').trim();
      if (!bruto) continue;
      const cantidad = D(bruto);
      if (cantidad.lessThanOrEqualTo(0)) continue;
      if (cantidad.greaterThan(D(linea.cantidad_disponible))) {
        setError(t('ventas.pos.devolucion.cantidadMaxima', {
          producto: linea.nombre_producto,
          max: linea.cantidad_disponible,
        }));
        return;
      }
      lineas.push({ id_detalle: linea.id_detalle, cantidad: cantidad.toString() });
    }
    if (lineas.length === 0) {
      setError(t('ventas.pos.devolucion.sinCantidades'));
      return;
    }
    if (!almacenEfectivo || !idMetodo) {
      setError(t('ventas.pos.devolucion.faltanDatos'));
      return;
    }
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    setProcesando(true);
    try {
      const resultado = await devolverVenta(
        estado.venta.id_nota_venta,
        { almacen_id: almacenEfectivo, id_metodo_pago: idMetodo, lineas, motivo },
        idemKeyRef.current,
      );
      const items = estado.lineas
        .filter((l) => lineas.some((x) => x.id_detalle === l.id_detalle))
        .map((l) => ({
          id_detalle: l.id_detalle,
          nombre: l.nombre_producto,
          cantidad: lineas.find((x) => x.id_detalle === l.id_detalle)?.cantidad ?? '0',
          precio: l.precio_unitario,
        }));
      onRegistrada({ resultado, venta: estado.venta, items, codigoIso: codigoIsoDocumento });
      reiniciar();
    } catch (err) {
      setError(mensajeDeError(err) ?? t('ventas.pos.devolucion.errorRegistro'));
    } finally {
      setProcesando(false);
    }
  };

  const reiniciar = () => {
    setNumero('');
    setEstado(null);
    setCantidades({});
    setAviso('');
    setError('');
    idemKeyRef.current = null;
  };

  const handleClose = () => {
    if (procesando) return;
    reiniciar();
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('ventas.pos.devolucion.titulo')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={1}>
            <TextField
              fullWidth size="small" autoFocus
              label={t('ventas.pos.devolucion.buscarLabel')}
              placeholder={t('ventas.pos.devolucion.buscarPlaceholder')}
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void buscar();
                }
              }}
              slotProps={{ htmlInput: { 'data-testid': 'pos-dev-numero' } }}
            />
            <Button variant="outlined" onClick={() => void buscar()} disabled={buscando} data-testid="pos-dev-buscar">
              {t('ventas.pos.devolucion.buscar')}
            </Button>
          </Stack>

          {aviso && <Alert severity="warning" data-testid="pos-dev-aviso">{aviso}</Alert>}

          {estado && (
            <>
              <Alert severity={estado.venta.fiscal ? 'info' : 'success'} data-testid="pos-dev-tipo-venta">
                {estado.venta.fiscal
                  ? t('ventas.pos.devolucion.fiscal', { numero: estado.venta.numero_factura ?? '' })
                  : t('ventas.pos.devolucion.noFiscal')}
              </Alert>
              <Box data-testid="pos-dev-lineas">
                {estado.lineas.map((linea) => (
                  <Stack key={linea.id_detalle} direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" noWrap>{linea.nombre_producto}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t('ventas.pos.devolucion.vendida', { cantidad: toFixedStr(linea.cantidad_vendida) })}
                        {' · '}
                        {t('ventas.pos.devolucion.devuelta', { cantidad: toFixedStr(linea.cantidad_devuelta) })}
                        {' · '}
                        {toFixedStr(linea.precio_unitario)} {codigoIsoDocumento}
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ width: 80, textAlign: 'right' }} data-testid={`pos-dev-disponible-${linea.id_detalle}`}>
                      {t('ventas.pos.devolucion.columnaDisponible')}: {toFixedStr(linea.cantidad_disponible)}
                    </Typography>
                    <TextField
                      size="small"
                      value={cantidades[linea.id_detalle] ?? ''}
                      onChange={(e) =>
                        setCantidades((prev) => ({ ...prev, [linea.id_detalle]: e.target.value }))
                      }
                      disabled={!D(linea.cantidad_disponible).greaterThan(0)}
                      slotProps={{
                        htmlInput: {
                          inputMode: 'decimal',
                          'aria-label': `${t('ventas.pos.devolucion.columnaCantidad')} ${linea.nombre_producto}`,
                          'data-testid': `pos-dev-cantidad-${linea.id_detalle}`,
                          style: { width: 64, textAlign: 'center' },
                        },
                      }}
                    />
                  </Stack>
                ))}
              </Box>
              <Divider />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  select fullWidth size="small"
                  label={t('ventas.pos.devolucion.almacen')}
                  value={almacenEfectivo}
                  onChange={(e) => setIdAlmacen(e.target.value)}
                  slotProps={{ select: { native: true }, htmlInput: { 'data-testid': 'pos-dev-almacen' }, inputLabel: { shrink: true } }}
                >
                  <option value="" />
                  {almacenes.map((a) => (
                    <option key={a.id_almacen} value={a.id_almacen}>{a.nombre_almacen}</option>
                  ))}
                </TextField>
                <TextField
                  select fullWidth size="small"
                  label={t('ventas.pos.devolucion.metodo')}
                  value={idMetodo}
                  onChange={(e) => setIdMetodo(e.target.value)}
                  slotProps={{ select: { native: true }, htmlInput: { 'data-testid': 'pos-dev-metodo' }, inputLabel: { shrink: true } }}
                >
                  <option value="" />
                  {metodos.map((m) => (
                    <option key={m.id} value={m.id}>{m.nombre_metodo}</option>
                  ))}
                </TextField>
                <TextField
                  select fullWidth size="small"
                  label={t('ventas.pos.devolucion.motivo')}
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  slotProps={{ select: { native: true }, htmlInput: { 'data-testid': 'pos-dev-motivo' }, inputLabel: { shrink: true } }}
                >
                  {MOTIVOS.map((m) => (
                    <option key={m} value={m}>{t(`ventas.pos.devolucion.motivos.${m}`)}</option>
                  ))}
                </TextField>
              </Stack>
              <Typography variant="h6" data-testid="pos-dev-total">
                {t('ventas.pos.devolucion.totalReembolso')}: {toFixedStr(totalReembolso)} {codigoIsoDocumento}
              </Typography>
              {estado.venta.fiscal && (
                <Typography variant="caption" color="text.secondary">
                  {t('ventas.pos.devolucion.ivaNota')}
                </Typography>
              )}
            </>
          )}

          {error && <Alert severity="error" data-testid="pos-dev-error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={procesando}>
          {t('ventas.pos.devolucion.cancelar')}
        </Button>
        <Button
          variant="contained"
          color="warning"
          disabled={!estado || procesando || !totalReembolso.greaterThan(0)}
          onClick={() => void confirmar()}
          data-testid="pos-dev-confirmar"
        >
          {procesando ? t('ventas.pos.devolucion.procesando') : t('ventas.pos.devolucion.confirmar')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
