import AutoFixHighOutlined from '@mui/icons-material/AutoFixHighOutlined';
import CheckCircleOutline from '@mui/icons-material/CheckCircleOutline';
import UndoOutlined from '@mui/icons-material/UndoOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type Decimal from 'decimal.js';
import { useMemo, useRef, useState } from 'react';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { D, sumDecimals, toFixedStr } from '../../lib/decimal';
import { newIdempotencyKey } from '../../lib/idempotency';
import { finanzasKeys } from '../../lib/queryKeys';
import {
  conciliacionPagosService,
  type AsignacionPagoItem,
  type LineaConciliacionInput,
  type ObligacionAbiertaConciliacion,
  type OmitidaSinTasaItem,
  type PagoDisponibleConciliacion,
} from '../../services/conciliacionPagosService';
import { mensajeDeError } from '../../utils/api';
import { StatusChip } from '../ui';

export interface ConciliacionContactoDialogProps {
  open: boolean;
  contactoId: string | null;
  tipoOperacionFiltro?: 'INGRESO' | 'EGRESO' | '';
  pagoInicialId?: string | null;
  onClose: () => void;
  onSuccess?: () => void;
}

function docKeyOf(tipoDocumento: string, idDocumento: string): string {
  return `${tipoDocumento}:${idDocumento}`;
}

function parseDecimalStrict(raw: string): Decimal | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const unsigned = trimmed.startsWith('-') ? trimmed.slice(1) : trimmed;
  if (!unsigned) return null;
  const parts = unsigned.split('.');
  if (parts.length > 2) return null;
  if (parts.some((p) => p.length === 0 || !/^\d+$/.test(p))) return null;
  try {
    return D(trimmed);
  } catch {
    return null;
  }
}

function esObligacionCompatible(
  tipoOperacionPago: string,
  tipoDocumento: string,
): boolean {
  if (tipoOperacionPago === 'INGRESO') {
    return tipoDocumento === 'CUENTA_POR_COBRAR' || tipoDocumento === 'FACTURA_VENTA';
  }
  if (tipoOperacionPago === 'EGRESO') {
    return tipoDocumento === 'CUENTA_POR_PAGAR' || tipoDocumento === 'FACTURA_COMPRA';
  }
  return true;
}

function etiquetaTipoDocumento(tipo: string): string {
  switch (tipo) {
    case 'CUENTA_POR_COBRAR':
      return 'CxC';
    case 'FACTURA_VENTA':
      return 'Factura Venta';
    case 'CUENTA_POR_PAGAR':
      return 'CxP';
    case 'FACTURA_COMPRA':
      return 'Factura Compra';
    default:
      return tipo;
  }
}

interface InnerProps {
  contactoId: string;
  tipoOperacionFiltro: 'INGRESO' | 'EGRESO' | '';
  pagoInicialId: string | null;
  onClose: () => void;
  onSuccess?: () => void;
}

function ConciliacionContactoDialogContent({
  contactoId,
  tipoOperacionFiltro,
  pagoInicialId,
  onClose,
  onSuccess,
}: InnerProps) {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const [tab, setTab] = useState<'conciliar' | 'activas'>('conciliar');
  const [selectedPagoOverride, setSelectedPagoOverride] = useState('');
  const [montosMap, setMontosMap] = useState<Map<string, string>>(() => new Map());
  const [tasasFifoMap, setTasasFifoMap] = useState<Map<string, string>>(() => new Map());
  const [descripcion, setDescripcion] = useState('');
  const [omitidasSinTasa, setOmitidasSinTasa] = useState<OmitidaSinTasaItem[]>([]);
  const [motivosReversion, setMotivosReversion] = useState<Map<string, string>>(() => new Map());
  const [errorGeneral, setErrorGeneral] = useState('');

  // Clave idempotente por intento actual: reintentos idénticos mantienen la misma clave;
  // cualquier edición de pago, montos o descripción la resetea.
  const idempotencyKeyRef = useRef<string | null>(null);
  const revertKeysRef = useRef<Map<string, string>>(new Map());

  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: finanzasKeys.conciliacionContacto(contactoId, tipoOperacionFiltro),
    queryFn: () =>
      conciliacionPagosService.obtenerEstadoConciliacionContacto(
        contactoId,
        tipoOperacionFiltro || undefined,
      ),
  });

  const pagosDisponibles: PagoDisponibleConciliacion[] = useMemo(
    () => data?.pagos_disponibles ?? [],
    [data],
  );

  const pagoActivo: PagoDisponibleConciliacion | null = useMemo(() => {
    if (selectedPagoOverride) {
      const exacto = pagosDisponibles.find((p) => p.id_pago === selectedPagoOverride);
      if (exacto) return exacto;
    }
    if (pagoInicialId) {
      const inicial = pagosDisponibles.find((p) => p.id_pago === pagoInicialId);
      if (inicial) return inicial;
    }
    return pagosDisponibles[0] ?? null;
  }, [pagosDisponibles, selectedPagoOverride, pagoInicialId]);

  const obligacionesVisibles: ObligacionAbiertaConciliacion[] = useMemo(() => {
    const todas = data?.obligaciones_abiertas ?? [];
    if (!pagoActivo) return todas;
    return todas.filter((ob) => esObligacionCompatible(pagoActivo.tipo_operacion, ob.tipo_documento));
  }, [data, pagoActivo]);

  const analisisLineas = useMemo(() => {
    const erroresFila = new Map<string, string>();
    const lineasValidas: LineaConciliacionInput[] = [];
    const montosPositivos: Decimal[] = [];

    for (const ob of obligacionesVisibles) {
      const key = docKeyOf(ob.tipo_documento, ob.id_documento);
      const raw = montosMap.get(key) ?? '';
      if (!raw.trim()) continue;

      const parsed = parseDecimalStrict(raw);
      if (!parsed) {
        erroresFila.set(key, 'Monto inválido');
        continue;
      }
      if (parsed.lte(0)) {
        erroresFila.set(key, 'Debe ser mayor a 0');
        continue;
      }
      if (pagoActivo && ob.moneda_codigo === pagoActivo.moneda_codigo && parsed.gt(D(ob.saldo_pendiente))) {
        erroresFila.set(key, `Supera el saldo (${toFixedStr(ob.saldo_pendiente)})`);
        continue;
      }

      const tasa = tasasFifoMap.get(key);
      if (pagoActivo && tasa && ob.moneda_codigo !== pagoActivo.moneda_codigo) {
        const equiv = parsed.times(D(tasa));
        if (equiv.minus(D(ob.saldo_pendiente)).gt(D('0.01'))) {
          erroresFila.set(key, `Equivalente supera saldo (${toFixedStr(ob.saldo_pendiente)})`);
          continue;
        }
      }

      montosPositivos.push(parsed);
      lineasValidas.push({
        tipo_documento: ob.tipo_documento,
        id_documento: ob.id_documento,
        monto_asignado_pago: parsed.toFixed(4),
        ...(tasa ? { tasa_aplicada: tasa } : {}),
      });
    }

    const totalAsignar = sumDecimals(montosPositivos);
    const saldoPago = pagoActivo ? D(pagoActivo.saldo_disponible) : D(0);
    const saldoRestante = saldoPago.minus(totalAsignar);
    const excedePago = Boolean(pagoActivo) && totalAsignar.gt(saldoPago);

    return {
      erroresFila,
      lineasValidas,
      totalAsignar,
      saldoPago,
      saldoRestante,
      excedePago,
    };
  }, [obligacionesVisibles, montosMap, tasasFifoMap, pagoActivo]);

  const invalidarRelacionados = () => {
    void queryClient.invalidateQueries({ queryKey: finanzasKeys.conciliacionContactoAll() });
    void queryClient.invalidateQueries({ queryKey: finanzasKeys.asignacionesPagoAll() });
    void queryClient.invalidateQueries({ queryKey: ['cxc'] });
    void queryClient.invalidateQueries({ queryKey: ['cxp'] });
    void queryClient.invalidateQueries({ queryKey: ['finanzas'] });
    void queryClient.invalidateQueries({ queryKey: ['tesoreria'] });
  };

  const sugerirFifoMutation = useMutation({
    mutationFn: (idPago: string) => conciliacionPagosService.sugerirDistribucionPago(idPago),
    onSuccess: (res) => {
      const nextMontos = new Map<string, string>();
      const nextTasas = new Map<string, string>();
      for (const prop of res.propuestas) {
        const key = docKeyOf(prop.tipo_documento, prop.id_documento);
        nextMontos.set(key, prop.monto_asignado_pago);
        nextTasas.set(key, prop.tasa_aplicada);
      }
      setMontosMap(nextMontos);
      setTasasFifoMap(nextTasas);
      setOmitidasSinTasa(res.omitidas_sin_tasa);
      setErrorGeneral('');
      idempotencyKeyRef.current = null;
      if (res.propuestas.length === 0) {
        snackbar.info('No se encontraron documentos elegibles para distribución automática.');
      } else {
        snackbar.success(`Distribución FIFO sugerida en ${res.propuestas.length} documento(s).`);
      }
    },
    onError: (err) => {
      setErrorGeneral(mensajeDeError(err, 'No se pudo calcular la distribución FIFO.'));
    },
  });

  const conciliarMutation = useMutation({
    mutationFn: (vars: {
      idPago: string;
      asignaciones: LineaConciliacionInput[];
      descripcion: string;
      key: string;
    }) =>
      conciliacionPagosService.conciliarPagoDocumentos(
        vars.idPago,
        {
          asignaciones: vars.asignaciones,
          descripcion: vars.descripcion,
          generar_asiento: true,
        },
        vars.key,
      ),
    onSuccess: (res) => {
      setMontosMap(new Map());
      setTasasFifoMap(new Map());
      setDescripcion('');
      setOmitidasSinTasa([]);
      setErrorGeneral('');
      idempotencyKeyRef.current = null;
      invalidarRelacionados();
      snackbar.success(`Conciliación aplicada (${res.asignaciones.length} asignación(es)).`);
      onSuccess?.();
    },
    onError: (err) => {
      setErrorGeneral(mensajeDeError(err, 'No se pudo aplicar la conciliación.'));
    },
  });

  const revertirMutation = useMutation({
    mutationFn: (vars: { idAsignacion: string; motivo: string; key: string }) =>
      conciliacionPagosService.revertirAsignacionPago(vars.idAsignacion, vars.motivo, vars.key),
    onSuccess: (_res, vars) => {
      revertKeysRef.current.delete(vars.idAsignacion);
      setErrorGeneral('');
      invalidarRelacionados();
      snackbar.success('Asignación revertida correctamente.');
      onSuccess?.();
    },
    onError: (err) => {
      setErrorGeneral(mensajeDeError(err, 'No se pudo revertir la asignación.'));
    },
  });

  const handlePagoChange = (nuevoPagoId: string) => {
    setSelectedPagoOverride(nuevoPagoId);
    setMontosMap(new Map());
    setTasasFifoMap(new Map());
    setOmitidasSinTasa([]);
    setErrorGeneral('');
    idempotencyKeyRef.current = null;
  };

  const handleMontoChange = (docKey: string, value: string) => {
    setErrorGeneral('');
    idempotencyKeyRef.current = null;
    setMontosMap((prev) => {
      const next = new Map(prev);
      if (value.trim() === '') {
        next.delete(docKey);
      } else {
        next.set(docKey, value);
      }
      return next;
    });
  };

  const handleDescripcionChange = (value: string) => {
    setErrorGeneral('');
    idempotencyKeyRef.current = null;
    setDescripcion(value);
  };

  const handleAplicarConciliacion = () => {
    if (!pagoActivo || analisisLineas.lineasValidas.length === 0) return;
    const attemptKey = idempotencyKeyRef.current ?? newIdempotencyKey();
    idempotencyKeyRef.current = attemptKey;
    conciliarMutation.mutate({
      idPago: pagoActivo.id_pago,
      asignaciones: analisisLineas.lineasValidas,
      descripcion,
      key: attemptKey,
    });
  };

  const handleMotivoChange = (idAsignacion: string, value: string) => {
    setErrorGeneral('');
    revertKeysRef.current.delete(idAsignacion);
    setMotivosReversion((prev) => {
      const next = new Map(prev);
      next.set(idAsignacion, value);
      return next;
    });
  };

  const handleRevertir = (asig: AsignacionPagoItem) => {
    const existingKey = revertKeysRef.current.get(asig.id_asignacion) ?? newIdempotencyKey();
    revertKeysRef.current.set(asig.id_asignacion, existingKey);
    const motivo = motivosReversion.get(asig.id_asignacion) ?? '';
    revertirMutation.mutate({
      idAsignacion: asig.id_asignacion,
      motivo,
      key: existingKey,
    });
  };

  const saldosPorMoneda = data ? Object.values(data.saldo_a_favor.total_por_moneda) : [];
  const asignacionesActivas = data?.asignaciones_activas ?? [];

  const puedeAplicar =
    Boolean(pagoActivo) &&
    analisisLineas.lineasValidas.length > 0 &&
    analisisLineas.erroresFila.size === 0 &&
    analisisLineas.totalAsignar.gt(0) &&
    !analisisLineas.excedePago &&
    !conciliarMutation.isPending;

  return (
    <>
      <DialogTitle>
        <Stack spacing={1}>
          <Typography variant="h6" component="span">
            Conciliación de Pagos — {data?.contacto.nombre ?? 'Cargando...'}
          </Typography>
          {data?.contacto.rif && (
            <Typography variant="body2" color="text.secondary">
              RIF / Documento: {data.contacto.rif}
            </Typography>
          )}
          {saldosPorMoneda.length > 0 && (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {saldosPorMoneda.map((s) => (
                <Chip
                  key={s.moneda_id}
                  size="small"
                  color="primary"
                  variant="outlined"
                  label={`${s.codigo_iso}: Cobro ${toFixedStr(s.INGRESO)} | Pago ${toFixedStr(s.EGRESO)} (${s.cantidad_pagos} disp.)`}
                />
              ))}
            </Stack>
          )}
        </Stack>
      </DialogTitle>

      <DialogContent dividers>
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
            <CircularProgress />
          </Box>
        )}

        {isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {mensajeDeError(error, 'Error al cargar el estado de conciliación del contacto.')}
          </Alert>
        )}

        {errorGeneral && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorGeneral}
          </Alert>
        )}

        {data && (
          <>
            <Tabs
              value={tab}
              onChange={(_e, val: 'conciliar' | 'activas') => setTab(val)}
              sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
            >
              <Tab value="conciliar" label="Conciliar pagos" />
              <Tab
                value="activas"
                label={`Asignaciones activas (${asignacionesActivas.length})`}
              />
            </Tabs>

            {tab === 'conciliar' && (
              <Stack spacing={2}>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={2}
                  alignItems={{ xs: 'stretch', sm: 'center' }}
                >
                  <FormControl fullWidth size="small" disabled={pagosDisponibles.length === 0}>
                    <InputLabel id="conciliacion-pago-select-label">Pago disponible</InputLabel>
                    <Select
                      labelId="conciliacion-pago-select-label"
                      label="Pago disponible"
                      value={pagoActivo?.id_pago ?? ''}
                      onChange={(e) => handlePagoChange(e.target.value)}
                    >
                      {pagosDisponibles.map((p) => (
                        <MenuItem key={p.id_pago} value={p.id_pago}>
                          {p.tipo_operacion} · {p.referencia || p.id_pago.slice(0, 8)} · Disponible:{' '}
                          {toFixedStr(p.saldo_disponible)} {p.moneda_codigo} (de {toFixedStr(p.monto)})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <Button
                    variant="outlined"
                    startIcon={<AutoFixHighOutlined />}
                    disabled={!pagoActivo || sugerirFifoMutation.isPending}
                    onClick={() => pagoActivo && sugerirFifoMutation.mutate(pagoActivo.id_pago)}
                    sx={{ whiteSpace: 'nowrap' }}
                  >
                    {sugerirFifoMutation.isPending ? 'Calculando...' : 'Distribuir FIFO'}
                  </Button>
                </Stack>

                {pagosDisponibles.length === 0 && (
                  <Alert severity="info">
                    Este contacto no tiene pagos con saldo disponible para conciliar.
                  </Alert>
                )}

                {omitidasSinTasa.length > 0 && (
                  <Alert severity="warning">
                    Documentos omitidos en FIFO por falta de tasa de cambio:{' '}
                    {omitidasSinTasa
                      .map((o) => `${etiquetaTipoDocumento(o.tipo_documento)} ${o.id_documento.slice(0, 8)} (${o.moneda_codigo})`)
                      .join(', ')}
                    .
                  </Alert>
                )}

                {analisisLineas.excedePago && pagoActivo && (
                  <Alert severity="error">
                    El total a asignar ({toFixedStr(analisisLineas.totalAsignar)} {pagoActivo.moneda_codigo}) supera el saldo disponible del pago ({toFixedStr(analisisLineas.saldoPago)} {pagoActivo.moneda_codigo}).
                  </Alert>
                )}

                <Table size="small" aria-label="Obligaciones abiertas para conciliar">
                  <TableHead>
                    <TableRow>
                      <TableCell>Tipo</TableCell>
                      <TableCell>Documento</TableCell>
                      <TableCell>Vencimiento</TableCell>
                      <TableCell>Moneda</TableCell>
                      <TableCell align="right">Saldo pendiente</TableCell>
                      <TableCell align="right">
                        Monto a asignar ({pagoActivo?.moneda_codigo ?? 'pago'})
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {obligacionesVisibles.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} align="center">
                          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                            No hay obligaciones abiertas compatibles para conciliar.
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      obligacionesVisibles.map((ob) => {
                        const key = docKeyOf(ob.tipo_documento, ob.id_documento);
                        const valor = montosMap.get(key) ?? '';
                        const errorFila = analisisLineas.erroresFila.get(key);
                        return (
                          <TableRow key={key} hover>
                            <TableCell>{etiquetaTipoDocumento(ob.tipo_documento)}</TableCell>
                            <TableCell>{ob.numero_documento || ob.id_documento.slice(0, 8)}</TableCell>
                            <TableCell>{ob.fecha_vencimiento}</TableCell>
                            <TableCell>{ob.moneda_codigo}</TableCell>
                            <TableCell align="right">{toFixedStr(ob.saldo_pendiente)}</TableCell>
                            <TableCell align="right" sx={{ width: 200 }}>
                              <TextField
                                size="small"
                                fullWidth
                                placeholder="0.00"
                                value={valor}
                                disabled={!pagoActivo}
                                error={Boolean(errorFila)}
                                helperText={errorFila}
                                inputProps={{
                                  'aria-label': `Monto para ${ob.numero_documento || ob.id_documento}`,
                                  inputMode: 'decimal',
                                }}
                                onChange={(e) => handleMontoChange(key, e.target.value)}
                              />
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>

                {pagoActivo && (
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={2}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    sx={{ p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }}
                  >
                    <Typography variant="body2">
                      Disponible del pago:{' '}
                      <strong>
                        {toFixedStr(analisisLineas.saldoPago)} {pagoActivo.moneda_codigo}
                      </strong>
                    </Typography>
                    <Typography variant="body2">
                      Total a aplicar:{' '}
                      <strong>
                        {toFixedStr(analisisLineas.totalAsignar)} {pagoActivo.moneda_codigo}
                      </strong>
                    </Typography>
                    <Typography
                      variant="body2"
                      color={analisisLineas.excedePago ? 'error.main' : 'text.primary'}
                    >
                      Saldo restante:{' '}
                      <strong>
                        {toFixedStr(analisisLineas.saldoRestante)} {pagoActivo.moneda_codigo}
                      </strong>
                    </Typography>
                  </Stack>
                )}

                <TextField
                  size="small"
                  fullWidth
                  label="Descripción o nota de conciliación (opcional)"
                  value={descripcion}
                  onChange={(e) => handleDescripcionChange(e.target.value)}
                />
              </Stack>
            )}

            {tab === 'activas' && (
              <Table size="small" aria-label="Asignaciones activas del contacto">
                <TableHead>
                  <TableRow>
                    <TableCell>Documento</TableCell>
                    <TableCell>Ref. Pago</TableCell>
                    <TableCell align="right">Asignado (Pago)</TableCell>
                    <TableCell align="right">Asignado (Doc.)</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell>Motivo reversión</TableCell>
                    <TableCell align="right">Acción</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {asignacionesActivas.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center">
                        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                          No hay asignaciones activas registradas para este contacto.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    asignacionesActivas.map((asig) => (
                      <TableRow key={asig.id_asignacion} hover>
                        <TableCell>
                          {etiquetaTipoDocumento(asig.tipo_documento)} ·{' '}
                          {asig.id_documento.slice(0, 8)}
                        </TableCell>
                        <TableCell>{asig.pago_referencia || asig.id_pago.slice(0, 8)}</TableCell>
                        <TableCell align="right">
                          {toFixedStr(asig.monto_asignado_pago)}
                        </TableCell>
                        <TableCell align="right">
                          {toFixedStr(asig.monto_asignado_documento)} {asig.moneda_documento_codigo}
                        </TableCell>
                        <TableCell>
                          <StatusChip value={asig.estado} />
                        </TableCell>
                        <TableCell sx={{ width: 200 }}>
                          <TextField
                            size="small"
                            fullWidth
                            placeholder="Motivo (opcional)"
                            value={motivosReversion.get(asig.id_asignacion) ?? ''}
                            inputProps={{
                              'aria-label': `Motivo reversión ${asig.id_asignacion}`,
                            }}
                            onChange={(e) => handleMotivoChange(asig.id_asignacion, e.target.value)}
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                            color="warning"
                            variant="outlined"
                            startIcon={<UndoOutlined />}
                            disabled={revertirMutation.isPending}
                            onClick={() => handleRevertir(asig)}
                          >
                            Revertir
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        {tab === 'conciliar' && (
          <Button
            variant="contained"
            startIcon={<CheckCircleOutline />}
            disabled={!puedeAplicar}
            onClick={handleAplicarConciliacion}
          >
            {conciliarMutation.isPending ? 'Aplicando...' : 'Aplicar Conciliación'}
          </Button>
        )}
      </DialogActions>
    </>
  );
}

export default function ConciliacionContactoDialog({
  open,
  contactoId,
  tipoOperacionFiltro = '',
  pagoInicialId = null,
  onClose,
  onSuccess,
}: ConciliacionContactoDialogProps) {
  return (
    <Dialog open={open && Boolean(contactoId)} onClose={onClose} maxWidth="lg" fullWidth>
      {open && contactoId && (
        <ConciliacionContactoDialogContent
          key={`${contactoId}-${tipoOperacionFiltro}-${pagoInicialId ?? ''}`}
          contactoId={contactoId}
          tipoOperacionFiltro={tipoOperacionFiltro}
          pagoInicialId={pagoInicialId}
          onClose={onClose}
          onSuccess={onSuccess}
        />
      )}
    </Dialog>
  );
}
