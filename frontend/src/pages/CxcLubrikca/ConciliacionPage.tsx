/**
 * Conciliación — CxC Lubrikca (Fase 6b).
 *
 * Lista las conciliaciones (semáforo motor-vs-factura) y permite conciliar un
 * pedido facturado (Dialog → POST conciliaciones/conciliar {pedido}) y marcar
 * una conciliación como revisada (POST conciliaciones/{id}/revisar). Arriba se
 * muestran las KPIs del resumen de cartera.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import RuleOutlined from '@mui/icons-material/RuleOutlined';
import FactCheckOutlined from '@mui/icons-material/FactCheckOutlined';
import { cxcLubrikcaService } from '../../services/cxcLubrikcaService';
import type { Conciliacion, Pedido } from '../../services/cxcLubrikcaService';
import { conciliarSchema, type ConciliarInput } from '../../schemas/cxcLubrikca.schemas';
import { cxcLubrikcaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip, KpiCard } from '../../components/ui';
import type { Column } from '../../components/ui';

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

const RESULTADO_COLOR: Record<string, 'success' | 'warning' | 'error'> = {
  verde: 'success',
  amarillo: 'warning',
  rojo: 'error',
};

export default function ConciliacionPage() {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [errorGeneral, setErrorGeneral] = useState('');

  const { data: conciliaciones = [], isLoading } = useQuery({
    queryKey: cxcLubrikcaKeys.conciliacionesAll(),
    queryFn: () => cxcLubrikcaService.listConciliaciones(),
  });

  const { data: resumen } = useQuery({
    queryKey: cxcLubrikcaKeys.resumen(),
    queryFn: () => cxcLubrikcaService.getResumen(),
  });

  const { data: pedidos = [] } = useQuery({
    queryKey: cxcLubrikcaKeys.pedidosAll(),
    queryFn: () => cxcLubrikcaService.listPedidos(),
  });

  // Solo los pedidos facturados se pueden conciliar.
  const pedidosFacturados = useMemo<Pedido[]>(
    () => pedidos.filter((p) => p.facturada),
    [pedidos],
  );

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<ConciliarInput>({
    resolver: zodResolver(conciliarSchema),
    defaultValues: { pedido: '' },
  });

  const invalidar = () => {
    queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.conciliacionesAll() });
    queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.resumen() });
  };

  const conciliar = useMutation({
    mutationFn: (input: ConciliarInput) => cxcLubrikcaService.conciliar({ pedido: input.pedido }),
    onSuccess: () => {
      snackbar.success('Pedido conciliado.');
      cerrar();
      invalidar();
    },
    onError: (err: unknown) => {
      try {
        const parsed = JSON.parse((err as Error).message) as Record<string, unknown>;
        if (parsed && typeof parsed === 'object' && 'pedido' in parsed) {
          const valor = parsed.pedido;
          const msg = Array.isArray(valor) ? valor.join(' ') : String(valor);
          setError('pedido', { type: 'server', message: msg });
          return;
        }
      } catch {
        // body no-JSON
      }
      setErrorGeneral(mensajeDeError(err, 'No se pudo conciliar el pedido.'));
    },
  });

  const revisar = useMutation({
    mutationFn: (id: string) => cxcLubrikcaService.revisarConciliacion(id),
    onSuccess: () => {
      snackbar.success('Conciliación marcada como revisada.');
      invalidar();
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, 'No se pudo marcar como revisada.'));
    },
  });

  function abrir() {
    setErrorGeneral('');
    reset({ pedido: '' });
    setDialogOpen(true);
  }

  function cerrar() {
    setDialogOpen(false);
    setErrorGeneral('');
  }

  const columns: Column<Conciliacion>[] = [
    { key: 'pedido', header: 'Pedido', render: (c) => c.pedido },
    { key: 'motor', header: 'Total motor', align: 'right', render: (c) => money(c.total_motor) },
    { key: 'facturado', header: 'Facturado', align: 'right', render: (c) => money(c.monto_facturado) },
    { key: 'ncs', header: 'NCs', align: 'right', render: (c) => money(c.ncs) },
    { key: 'diferencia', header: 'Diferencia', align: 'right', render: (c) => money(c.diferencia) },
    {
      key: 'resultado',
      header: 'Resultado',
      render: (c) => (
        <StatusChip
          value={c.resultado}
          colorMap={RESULTADO_COLOR}
        />
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (c) => (
        <Button
          size="small"
          startIcon={<FactCheckOutlined />}
          disabled={revisar.isPending || c.revisado_por != null}
          onClick={() => revisar.mutate(c.id)}
        >
          {c.revisado_por != null ? 'Revisado' : 'Marcar revisado'}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Conciliación"
        subtitle="Semáforo motor vs. factura"
        actions={
          <Button variant="contained" startIcon={<RuleOutlined />} onClick={abrir}>
            Conciliar pedido
          </Button>
        }
      />

      {resumen && (
        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
            mb: 3,
          }}
        >
          <KpiCard label="Verde" value={resumen.por_resultado.verde} tone="success" />
          <KpiCard label="Amarillo" value={resumen.por_resultado.amarillo} tone="warning" />
          <KpiCard label="Rojo" value={resumen.por_resultado.rojo} tone="error" />
          <KpiCard
            label="Facturados sin conciliar"
            value={resumen.facturados_sin_conciliar}
            tone="tint"
          />
        </Box>
      )}

      <DataTable
        columns={columns}
        rows={conciliaciones}
        getRowKey={(c) => c.id}
        loading={isLoading}
        emptyMessage="No hay conciliaciones registradas."
      />

      <Dialog open={dialogOpen} onClose={() => !conciliar.isPending && cerrar()} fullWidth maxWidth="xs">
        <DialogTitle>Conciliar pedido</DialogTitle>
        <form onSubmit={handleSubmit((input) => conciliar.mutate(input))} noValidate>
          <DialogContent>
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2}>
              <TextField
                select
                label="Pedido facturado"
                fullWidth
                defaultValue=""
                error={!!errors.pedido}
                helperText={
                  errors.pedido?.message ||
                  (pedidosFacturados.length === 0 ? 'No hay pedidos facturados.' : undefined)
                }
                {...register('pedido')}
              >
                {pedidosFacturados.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.so_id} · {p.cliente_nombre || 'Cliente'}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrar} disabled={conciliar.isPending}>
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={conciliar.isPending}
              startIcon={conciliar.isPending ? <CircularProgress size={16} /> : undefined}
            >
              Conciliar
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
