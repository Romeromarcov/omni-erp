/**
 * Captura — CxC Lubrikca (Fase 6b).
 *
 * Lista los pedidos del espejo y permite (1) recalcular el motor del pedido y
 * (2) vincular un pago del mismo cliente contra el pedido. La vinculación usa
 * registrarVinculacionSchema; los 400 de campo se muestran en el form y el
 * resto como error general. Tras vincular/recalcular se invalidan pedidos y
 * bandeja.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CalculateOutlined from '@mui/icons-material/CalculateOutlined';
import LinkOutlined from '@mui/icons-material/LinkOutlined';
import { cxcLubrikcaService } from '../../services/cxcLubrikcaService';
import type { Pedido, Pago } from '../../services/cxcLubrikcaService';
import {
  registrarVinculacionSchema,
  type RegistrarVinculacionInput,
} from '../../schemas/cxcLubrikca.schemas';
import { cxcLubrikcaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

export default function CapturaPage() {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [pedidoVincular, setPedidoVincular] = useState<Pedido | null>(null);
  const [errorGeneral, setErrorGeneral] = useState('');

  const { data: pedidos = [], isLoading } = useQuery({
    queryKey: cxcLubrikcaKeys.pedidosAll(),
    queryFn: () => cxcLubrikcaService.listPedidos(),
  });

  const { data: pagos = [] } = useQuery({
    queryKey: ['cxc-lubrikca', 'pagos'],
    queryFn: () => cxcLubrikcaService.listPagos(),
  });

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<RegistrarVinculacionInput>({
    resolver: zodResolver(registrarVinculacionSchema),
    defaultValues: { pedido: '', pago: '', monto_aplicado: '', hora_pago_confirmada: '' },
  });

  // Pagos del mismo cliente que el pedido y aún no vinculados.
  const pagosDelCliente = useMemo<Pago[]>(() => {
    if (!pedidoVincular) return [];
    return pagos.filter(
      (p) => !p.vinculado && p.cliente_externo_id === pedidoVincular.cliente_externo_id,
    );
  }, [pagos, pedidoVincular]);

  const recalcular = useMutation({
    mutationFn: (id: string) => cxcLubrikcaService.recalcularPedido(id),
    onSuccess: () => {
      snackbar.success('Pedido recalculado.');
      queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.pedidosAll() });
      queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.bandejaAll() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, 'No se pudo recalcular el pedido.'));
    },
  });

  const vincular = useMutation({
    mutationFn: (input: RegistrarVinculacionInput) =>
      cxcLubrikcaService.registrarVinculacion({
        pedido: pedidoVincular!.id,
        pago: input.pago,
        monto_aplicado: input.monto_aplicado,
        hora_pago_confirmada: input.hora_pago_confirmada,
        es_tasa_heredada: input.es_tasa_heredada ?? false,
      }),
    onSuccess: () => {
      snackbar.success('Pago vinculado al pedido.');
      cerrar();
      queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.pedidosAll() });
      queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.bandejaAll() });
      queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.vinculacionesAll() });
    },
    onError: (err: unknown) => {
      // Mapea errores 400 de campo conocidos al form; el resto al banner general.
      try {
        const parsed = JSON.parse((err as Error).message) as Record<string, unknown>;
        if (parsed && typeof parsed === 'object') {
          for (const campo of ['pago', 'monto_aplicado', 'hora_pago_confirmada'] as const) {
            if (campo in parsed) {
              // eslint-disable-next-line security/detect-object-injection -- `campo` proviene de una lista literal constante, no de input
              const valor = parsed[campo];
              const msg = Array.isArray(valor) ? valor.join(' ') : String(valor);
              setError(campo, { type: 'server', message: msg });
              return;
            }
          }
        }
      } catch {
        // body no-JSON
      }
      setErrorGeneral(mensajeDeError(err, 'No se pudo vincular el pago.'));
    },
  });

  function abrirVincular(pedido: Pedido) {
    setPedidoVincular(pedido);
    setErrorGeneral('');
    reset({
      pedido: pedido.id,
      pago: '',
      monto_aplicado: '',
      hora_pago_confirmada: '',
    });
  }

  function cerrar() {
    setPedidoVincular(null);
    setErrorGeneral('');
  }

  const columns: Column<Pedido>[] = [
    { key: 'so', header: 'Pedido (SO)', render: (p) => p.so_id },
    { key: 'cliente', header: 'Cliente', render: (p) => p.cliente_nombre || '—' },
    { key: 'monto', header: 'Monto total', align: 'right', render: (p) => money(p.monto_total) },
    { key: 'entrega', header: 'Entrega', render: (p) => <StatusChip value={p.estado_entrega} /> },
    { key: 'facturada', header: 'Facturada', render: (p) => <StatusChip value={p.facturada} /> },
    {
      key: 'motor',
      header: 'Motor',
      align: 'right',
      render: (p) =>
        p.bandeja ? (
          <Typography component="span" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {money(p.bandeja.total_motor)}
            {p.bandeja.candidata_a_cierre ? ' ✓' : ''}
          </Typography>
        ) : (
          '—'
        ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (p) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button
            size="small"
            startIcon={<CalculateOutlined />}
            disabled={recalcular.isPending}
            onClick={() => recalcular.mutate(p.id)}
          >
            Recalcular
          </Button>
          <Button
            size="small"
            variant="contained"
            startIcon={<LinkOutlined />}
            onClick={() => abrirVincular(p)}
          >
            Vincular pago
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader title="Captura" subtitle="Pedidos del espejo: recálculo del motor y vinculación de pagos" />
      <DataTable
        columns={columns}
        rows={pedidos}
        getRowKey={(p) => p.id}
        loading={isLoading}
        emptyMessage="No hay pedidos sincronizados."
      />

      <Dialog
        open={!!pedidoVincular}
        onClose={() => !vincular.isPending && cerrar()}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Vincular pago</DialogTitle>
        <form onSubmit={handleSubmit((input) => vincular.mutate(input))} noValidate>
          <DialogContent>
            {pedidoVincular && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Pedido {pedidoVincular.so_id} · {pedidoVincular.cliente_nombre || 'Cliente'}
              </Typography>
            )}
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2}>
              <TextField
                select
                label="Pago"
                fullWidth
                defaultValue=""
                error={!!errors.pago}
                helperText={
                  errors.pago?.message ||
                  (pagosDelCliente.length === 0 ? 'No hay pagos sin vincular para este cliente.' : undefined)
                }
                {...register('pago')}
              >
                {pagosDelCliente.map((pago) => (
                  <MenuItem key={pago.id} value={pago.id}>
                    {pago.pago_id} · {money(pago.monto)} {pago.moneda}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Monto aplicado"
                fullWidth
                required
                inputMode="decimal"
                error={!!errors.monto_aplicado}
                helperText={errors.monto_aplicado?.message}
                {...register('monto_aplicado')}
              />
              <TextField
                label="Hora del pago confirmada"
                type="datetime-local"
                fullWidth
                required
                InputLabelProps={{ shrink: true }}
                error={!!errors.hora_pago_confirmada}
                helperText={errors.hora_pago_confirmada?.message}
                {...register('hora_pago_confirmada')}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrar} disabled={vincular.isPending}>
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={vincular.isPending}
              startIcon={vincular.isPending ? <CircularProgress size={16} /> : undefined}
            >
              Vincular
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
