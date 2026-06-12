/**
 * Cuentas por Pagar (workstream F): listado con saldos, filtro por estado,
 * aging de cartera de proveedores y registro de abonos.
 *
 * El abono (RHF + zod, patrón del modal de abonos CxC del PR #79) envía la
 * cabecera `Idempotency-Key` (PR #86): se genera un UUID por intento de submit
 * y se REÚSA en los reintentos del mismo intento (mismo payload), de modo que
 * un doble click o un retry de red nunca duplique el abono. Si el usuario
 * cambia el monto/descripción, es una operación nueva → clave nueva.
 */
import { useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import PaymentsOutlined from '@mui/icons-material/PaymentsOutlined';
import { cuentasPorPagarService } from '../../services/cuentasPorPagarService';
import type { AgingCxPResponse, CuentaPorPagar } from '../../services/cuentasPorPagarService';
import { abonoCxpSchema, type AbonoCxpInput } from '../../schemas/cxp.schemas';
import { cxpKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { D, toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import AgingBars, { type AgingBar } from '../../components/ui/AgingBars';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

const ESTADOS = ['PENDIENTE', 'PARCIAL', 'VENCIDA', 'PAGADA', 'ANULADA'] as const;

function buildAgingBars(aging: AgingCxPResponse, t: (k: string) => string): AgingBar[] {
  const total = D(aging.total_general);
  const buckets: Array<{ key: string; label: string; monto: string }> = [
    { key: 'corriente', label: t('cxp.aging.corriente'), monto: aging.corriente.monto },
    { key: 'dias_1_30', label: t('cxp.aging.dias1a30'), monto: aging.dias_1_30.monto },
    { key: 'dias_31_60', label: t('cxp.aging.dias31a60'), monto: aging.dias_31_60.monto },
    { key: 'dias_61_90', label: t('cxp.aging.dias61a90'), monto: aging.dias_61_90.monto },
    { key: 'dias_90_mas', label: t('cxp.aging.dias90mas'), monto: aging.dias_90_mas.monto },
  ];
  return buckets.map((b) => ({
    key: b.key,
    label: b.label,
    amount: toFixedStr(b.monto),
    // Porcentaje solo para el ancho visual de la barra (no es dinero).
    pct: total.greaterThan(0) ? D(b.monto).dividedBy(total).times(100).toNumber() : 0,
    gradient: 'linear-gradient(90deg, #7c3aed, #db2777)',
  }));
}

export default function CuentasPorPagarPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [page, setPage] = useState(1);
  const [estado, setEstado] = useState('');
  const [cxpSeleccionada, setCxpSeleccionada] = useState<CuentaPorPagar | null>(null);
  const [errorGeneral, setErrorGeneral] = useState('');
  const empresaId = getEmpresaId() || '';

  // Idempotency-Key por intento: misma clave para reintentos del MISMO payload,
  // clave nueva si cambia la operación (otra CxP u otro monto/descripción).
  const intentoRef = useRef<{ firma: string; clave: string } | null>(null);
  function claveIdempotencia(firma: string): string {
    if (intentoRef.current?.firma !== firma) {
      intentoRef.current = { firma, clave: crypto.randomUUID() };
    }
    return intentoRef.current.clave;
  }

  const { data, isLoading } = useQuery({
    queryKey: cxpKeys.cuentas(page, estado || null),
    queryFn: () => cuentasPorPagarService.getAllPaginated(page, PAGE_SIZE, estado ? { estado } : {}),
  });

  const { data: aging } = useQuery({
    queryKey: cxpKeys.aging(empresaId),
    queryFn: () => cuentasPorPagarService.getAging(empresaId),
    enabled: !!empresaId,
  });

  const cuentas = data?.results ?? [];
  const count = data?.count ?? 0;

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<AbonoCxpInput>({
    resolver: zodResolver(abonoCxpSchema),
    defaultValues: { monto: '', descripcion: '' },
  });

  const abonoMutation = useMutation({
    mutationFn: (input: AbonoCxpInput) => {
      const cxpId = cxpSeleccionada!.id_cxp;
      const payload = { monto: input.monto, descripcion: input.descripcion || '' };
      const firma = JSON.stringify({ cxpId, ...payload });
      return cuentasPorPagarService.abonar(cxpId, payload, claveIdempotencia(firma));
    },
    onSuccess: () => {
      snackbar.success(t('cxp.abono.ok'));
      intentoRef.current = null;
      cerrarModal();
      // El abono cambia saldo, estado y el aging.
      void queryClient.invalidateQueries({ queryKey: cxpKeys.cuentasAll() });
      void queryClient.invalidateQueries({ queryKey: cxpKeys.agingAll() });
    },
    onError: (err: unknown) => {
      // Errores 400 de campo (p. ej. monto > saldo) visibles en el formulario;
      // 422 = clave reusada con otro payload; 409 = operación en curso.
      try {
        const parsed = JSON.parse((err as Error).message) as Record<string, unknown>;
        if (parsed && typeof parsed === 'object' && 'monto' in parsed) {
          const msg = Array.isArray(parsed.monto) ? parsed.monto.join(' ') : String(parsed.monto);
          setError('monto', { type: 'server', message: msg });
          return;
        }
      } catch {
        // body no-JSON: cae al mensaje general
      }
      setErrorGeneral(mensajeDeError(err, t('cxp.abono.error')));
    },
  });

  function abrirModal(cxp: CuentaPorPagar) {
    setCxpSeleccionada(cxp);
    setErrorGeneral('');
    intentoRef.current = null;
    reset({ monto: '', descripcion: '' });
  }

  function cerrarModal() {
    setCxpSeleccionada(null);
    setErrorGeneral('');
  }

  const columns: Column<CuentaPorPagar>[] = [
    {
      key: 'documento',
      header: t('cxp.lista.documento'),
      render: (c) => (
        <>
          <Typography variant="body2" fontWeight={600}>
            {c.referencia_externa || `CxP-${c.id_cxp.slice(0, 8)}`}
          </Typography>
          {c.observaciones && (
            <Typography variant="caption" color="text.secondary">
              {c.observaciones}
            </Typography>
          )}
        </>
      ),
    },
    { key: 'emision', header: t('cxp.lista.emision'), render: (c) => c.fecha_emision },
    { key: 'vencimiento', header: t('cxp.lista.vencimiento'), render: (c) => c.fecha_vencimiento },
    {
      key: 'monto',
      header: t('cxp.lista.montoTotal'),
      align: 'right',
      render: (c) => toFixedStr(c.monto_total),
    },
    {
      key: 'pendiente',
      header: t('cxp.lista.saldoPendiente'),
      align: 'right',
      render: (c) => (
        <Typography component="span" fontWeight={700} sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {toFixedStr(c.monto_pendiente)}
        </Typography>
      ),
    },
    { key: 'estado', header: t('cxp.lista.estado'), render: (c) => <StatusChip value={c.estado} /> },
    {
      key: 'acciones',
      header: t('common.actions'),
      align: 'right',
      render: (c) => (
        <Button
          size="small"
          variant="contained"
          startIcon={<PaymentsOutlined />}
          disabled={c.estado === 'PAGADA' || c.estado === 'ANULADA' || !D(c.monto_pendiente).greaterThan(0)}
          onClick={() => abrirModal(c)}
        >
          {t('cxp.abono.abonar')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader title={t('cxp.title')} subtitle={t('cxp.subtitle')} />

      {aging && (
        <Paper variant="outlined" sx={{ p: 3, mb: 2, maxWidth: 560 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('cxp.aging.title')} · {t('cxp.aging.total')}: {toFixedStr(aging.total_general)}
          </Typography>
          <AgingBars bars={buildAgingBars(aging, t)} />
        </Paper>
      )}

      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label={t('cxp.lista.filtroEstado')}
          value={estado}
          onChange={(e) => {
            setEstado(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">{t('cxp.lista.todos')}</MenuItem>
          {ESTADOS.map((e) => (
            <MenuItem key={e} value={e}>
              {e}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <DataTable
        columns={columns}
        rows={cuentas}
        getRowKey={(c) => c.id_cxp}
        loading={isLoading}
        emptyMessage={t('cxp.lista.empty')}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />

      <Dialog
        open={!!cxpSeleccionada}
        onClose={() => !abonoMutation.isPending && cerrarModal()}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>{t('cxp.abono.title')}</DialogTitle>
        <form onSubmit={handleSubmit((input) => abonoMutation.mutate(input))} noValidate>
          <DialogContent>
            {cxpSeleccionada && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {cxpSeleccionada.referencia_externa || `CxP-${cxpSeleccionada.id_cxp.slice(0, 8)}`} ·{' '}
                {t('cxp.lista.saldoPendiente')}: {toFixedStr(cxpSeleccionada.monto_pendiente)}
              </Typography>
            )}
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2}>
              <TextField
                label={t('cxp.abono.monto')}
                fullWidth
                required
                inputMode="decimal"
                error={!!errors.monto}
                helperText={errors.monto?.message}
                {...register('monto')}
              />
              <TextField
                label={t('cxp.abono.descripcion')}
                fullWidth
                multiline
                rows={2}
                error={!!errors.descripcion}
                helperText={errors.descripcion?.message}
                {...register('descripcion')}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrarModal} disabled={abonoMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={abonoMutation.isPending}
              startIcon={abonoMutation.isPending ? <CircularProgress size={16} /> : undefined}
            >
              {t('cxp.abono.registrar')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
