import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  reembolsosGastoService,
  gastosService,
  type ReembolsoGasto,
  type ReembolsoGastoPayload,
  type EstadoReembolso,
  type Gasto,
} from '../../services/gastosService';
import { fetchMonedas } from '../../services/monedas';
import { fetchMetodosPagoEmpresaActivos } from '../../services/metodosPagoEmpresaActiva';
import { gastosKeys, finanzasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const ESTADOS: { value: EstadoReembolso | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'PAGADO', label: 'Pagado' },
  { value: 'ANULADO', label: 'Anulado' },
];

const ESTADO_COLOR: Record<string, 'warning' | 'success' | 'error'> = {
  pendiente: 'warning',
  pagado: 'success',
  anulado: 'error',
};

const hoy = () => new Date().toISOString().slice(0, 10);

interface FormState {
  id_gasto: string;
  monto_reembolso: string;
  fecha_reembolso: string;
  id_moneda: string;
  id_metodo_pago: string;
}

const formVacio = (): FormState => ({
  id_gasto: '',
  monto_reembolso: '',
  fecha_reembolso: hoy(),
  id_moneda: '',
  id_metodo_pago: '',
});

const ReembolsosPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState<EstadoReembolso | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: reembolsos = [], isLoading } = useQuery({
    queryKey: gastosKeys.reembolsos(empresaId, filtroEstado),
    queryFn: () =>
      reembolsosGastoService.getAll({
        empresa: empresaId || undefined,
        estado: filtroEstado || undefined,
      }),
  });

  const { data: gastos = [] } = useQuery<Gasto[]>({
    queryKey: gastosKeys.gastos(empresaId, 'APROBADO'),
    queryFn: () => gastosService.getAll({ empresa: empresaId || undefined, estado: 'APROBADO' }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: fetchMonedas,
  });

  const { data: metodos = [] } = useQuery({
    queryKey: finanzasKeys.metodosPagoEmpresaActivas(empresaId),
    queryFn: () => fetchMetodosPagoEmpresaActivos(empresaId),
    enabled: Boolean(empresaId),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gastosKeys.reembolsosAll() });

  const abrirCrear = () => {
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ReembolsoGastoPayload) => reembolsosGastoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar el reembolso.')),
  });

  const procesarPago = useMutation({
    mutationFn: (id: string) => reembolsosGastoService.procesarPago(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo procesar el pago.')),
  });

  const anular = useMutation({
    mutationFn: (id: string) => reembolsosGastoService.anular(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo anular el reembolso.')),
  });

  const handleGuardar = () => {
    if (!form.id_gasto || !form.monto_reembolso.trim() || !form.id_moneda || !form.id_metodo_pago) {
      setErrorMsg('Complete gasto, monto, moneda y método de pago.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_gasto: form.id_gasto,
      monto_reembolso: form.monto_reembolso.trim(),
      fecha_reembolso: form.fecha_reembolso,
      id_moneda: form.id_moneda,
      id_metodo_pago: form.id_metodo_pago,
      estado_reembolso: 'PENDIENTE',
    });
  };

  const handleProcesar = (r: ReembolsoGasto) => {
    if (window.confirm('¿Procesar el pago de este reembolso?')) {
      procesarPago.mutate(r.id_reembolso);
    }
  };

  const handleAnular = (r: ReembolsoGasto) => {
    if (window.confirm('¿Anular este reembolso?')) {
      anular.mutate(r.id_reembolso);
    }
  };

  const descripcionGasto = (id: string) =>
    gastos.find((g) => g.id_gasto === id)?.descripcion ?? id;

  const columns: Column<ReembolsoGasto>[] = [
    { key: 'fecha_reembolso', header: 'Fecha', render: (r) => r.fecha_reembolso },
    { key: 'id_gasto', header: 'Gasto', render: (r) => descripcionGasto(r.id_gasto) },
    { key: 'monto_reembolso', header: 'Monto', render: (r) => r.monto_reembolso },
    {
      key: 'estado_reembolso',
      header: 'Estado',
      render: (r) => <StatusChip value={r.estado_reembolso} colorMap={ESTADO_COLOR} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => {
        const pendiente = r.estado_reembolso === 'PENDIENTE';
        return (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              color="success"
              disabled={!pendiente || procesarPago.isPending}
              onClick={() => handleProcesar(r)}
            >
              Procesar pago
            </Button>
            <Button
              size="small"
              color="error"
              disabled={!pendiente || anular.isPending}
              onClick={() => handleAnular(r)}
            >
              Anular
            </Button>
          </Stack>
        );
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Reembolsos de gasto"
        subtitle="Reembolsos a empleados por gastos aprobados: registro, pago y anulación."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo reembolso
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <TextField
        select
        label="Estado"
        value={filtroEstado}
        onChange={(e) => setFiltroEstado(e.target.value as EstadoReembolso | '')}
        size="small"
        sx={{ mb: 2, minWidth: 220 }}
      >
        {ESTADOS.map((e) => (
          <MenuItem key={e.value || 'todos'} value={e.value}>
            {e.label}
          </MenuItem>
        ))}
      </TextField>

      <DataTable
        columns={columns}
        rows={reembolsos}
        getRowKey={(r) => r.id_reembolso}
        loading={isLoading}
        emptyMessage="Sin reembolsos. Registra el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nuevo reembolso</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Gasto aprobado"
              value={form.id_gasto}
              onChange={(e) => setForm((f) => ({ ...f, id_gasto: e.target.value }))}
              required
              helperText={gastos.length === 0 ? 'No hay gastos aprobados disponibles.' : ' '}
              fullWidth
            >
              {gastos.map((g) => (
                <MenuItem key={g.id_gasto} value={g.id_gasto}>
                  {g.descripcion} · {g.monto}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha del reembolso"
              type="date"
              value={form.fecha_reembolso}
              onChange={(e) => setForm((f) => ({ ...f, fecha_reembolso: e.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Monto a reembolsar"
              value={form.monto_reembolso}
              onChange={(e) => setForm((f) => ({ ...f, monto_reembolso: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Moneda"
              value={form.id_moneda}
              onChange={(e) => setForm((f) => ({ ...f, id_moneda: e.target.value }))}
              required
              fullWidth
            >
              {monedas.map((m) => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>
                  {m.codigo_iso} — {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Método de pago"
              value={form.id_metodo_pago}
              onChange={(e) => setForm((f) => ({ ...f, id_metodo_pago: e.target.value }))}
              required
              fullWidth
            >
              {metodos.map((m) => (
                <MenuItem key={m.id} value={String(m.metodo_pago ?? m.id)}>
                  {String(m.nombre ?? m.nombre_metodo)}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleGuardar} disabled={guardar.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
};

export default ReembolsosPage;
