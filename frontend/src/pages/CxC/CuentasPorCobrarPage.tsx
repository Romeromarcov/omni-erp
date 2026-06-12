/**
 * Listado de Cuentas por Cobrar con registro de abonos.
 *
 * Gap E2E (PR #76): la UI de cobranza no tenía formulario de abono — el flujo
 * solo era posible vía API. Esta página lista las CxC y permite abonar contra
 * POST /api/cxc/abonos-cxc/ (contrato P0-2: cuenta_por_cobrar, monto,
 * descripcion) con react-hook-form + zod y errores 400 visibles.
 */
import { useState } from 'react';
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
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import PaymentsOutlined from '@mui/icons-material/PaymentsOutlined';
import { cuentasPorCobrarService } from '../../services/cuentasPorCobrarService';
import type { CuentaPorCobrar } from '../../services/cuentasPorCobrarService';
import { abonoCxcSchema, type AbonoCxcInput } from '../../schemas/cxc.schemas';
import { mensajeDeError } from '../../utils/api';
import { cxcKeys } from '../../lib/queryKeys';
import { useSnackbar } from '../../contexts/feedbackTypes';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

export default function CuentasPorCobrarPage() {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [page, setPage] = useState(1);
  const [cxcSeleccionada, setCxcSeleccionada] = useState<CuentaPorCobrar | null>(null);
  const [errorGeneral, setErrorGeneral] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: cxcKeys.cuentas(page),
    queryFn: () => cuentasPorCobrarService.getAllPaginated(page, PAGE_SIZE),
  });

  const cuentas = data?.results ?? [];
  const count = data?.count ?? 0;

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<AbonoCxcInput>({
    resolver: zodResolver(abonoCxcSchema),
    defaultValues: { monto: '', descripcion: '' },
  });

  const abonoMutation = useMutation({
    mutationFn: (input: AbonoCxcInput) =>
      cuentasPorCobrarService.crearAbono({
        cuenta_por_cobrar: cxcSeleccionada!.id,
        monto: input.monto,
        descripcion: input.descripcion || '',
      }),
    onSuccess: () => {
      snackbar.success('Abono registrado correctamente.');
      cerrarModal();
      // El saldo de la CxC y el dashboard de cartera cambian con el abono.
      queryClient.invalidateQueries({ queryKey: cxcKeys.cuentasAll() });
      queryClient.invalidateQueries({ queryKey: cxcKeys.carteraAll() });
    },
    onError: (err: unknown) => {
      // Errores 400 de campo del backend (p. ej. monto > saldo) visibles en el form.
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
      setErrorGeneral(mensajeDeError(err, 'Error al registrar el abono.'));
    },
  });

  function abrirModal(cxc: CuentaPorCobrar) {
    setCxcSeleccionada(cxc);
    setErrorGeneral('');
    reset({ monto: '', descripcion: '' });
  }

  function cerrarModal() {
    setCxcSeleccionada(null);
    setErrorGeneral('');
  }

  const columns: Column<CuentaPorCobrar>[] = [
    {
      key: 'cliente',
      header: 'Cliente',
      render: (c) => (
        <>
          <Typography variant="body2" fontWeight={600}>
            {c.cliente_nombre || c.cliente_ref || '—'}
          </Typography>
          {c.descripcion && (
            <Typography variant="caption" color="text.secondary">
              {c.descripcion}
            </Typography>
          )}
        </>
      ),
    },
    { key: 'emision', header: 'Emisión', render: (c) => c.fecha_emision },
    { key: 'vencimiento', header: 'Vencimiento', render: (c) => c.fecha_vencimiento },
    { key: 'monto', header: 'Monto', align: 'right', render: (c) => money(c.monto) },
    {
      key: 'saldo',
      header: 'Saldo pendiente',
      align: 'right',
      render: (c) => (
        <Typography component="span" fontWeight={700} sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {money(c.saldo_pendiente)}
        </Typography>
      ),
    },
    { key: 'estado', header: 'Estado', render: (c) => <StatusChip value={c.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (c) => (
        <Button
          size="small"
          variant="contained"
          startIcon={<PaymentsOutlined />}
          disabled={c.estado === 'pagada' || parseFloat(c.saldo_pendiente) <= 0}
          onClick={() => abrirModal(c)}
        >
          Abonar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Cuentas por Cobrar"
        subtitle="Listado de CxC y registro de abonos"
      />
      <DataTable
        columns={columns}
        rows={cuentas}
        getRowKey={(c) => String(c.id)}
        loading={isLoading}
        emptyMessage="No hay cuentas por cobrar registradas."
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />

      <Dialog open={!!cxcSeleccionada} onClose={() => !abonoMutation.isPending && cerrarModal()} fullWidth maxWidth="xs">
        <DialogTitle>Registrar abono</DialogTitle>
        <form onSubmit={handleSubmit((input) => abonoMutation.mutate(input))} noValidate>
          <DialogContent>
            {cxcSeleccionada && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {cxcSeleccionada.cliente_nombre || cxcSeleccionada.cliente_ref || 'Cliente'} · saldo
                pendiente {money(cxcSeleccionada.saldo_pendiente)}
              </Typography>
            )}
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2}>
              <TextField
                label="Monto"
                fullWidth
                required
                inputMode="decimal"
                error={!!errors.monto}
                helperText={errors.monto?.message}
                {...register('monto')}
              />
              <TextField
                label="Descripción"
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
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={abonoMutation.isPending}
              startIcon={abonoMutation.isPending ? <CircularProgress size={16} /> : undefined}
            >
              Registrar abono
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
