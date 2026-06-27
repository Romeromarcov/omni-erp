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
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';
import {
  pagosTercerosService,
  type PagoTercero,
  type PagoTerceroPayload,
  type EstadoPagoTercero,
} from '../../../services/gapsMenoresService';
import { proveedoresService, type Proveedor } from '../../../services/proveedoresService';
import { fetchMonedas, type Moneda } from '../../../services/monedas';
import { gapsMenoresKeys, proveedoresKeys, finanzasKeys } from '../../../lib/queryKeys';
import { getEmpresaId } from '../../../utils/empresa';
import { mensajeDeError } from '../../../utils/api';

const ESTADOS: { value: EstadoPagoTercero | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'pendiente', label: 'Pendiente' },
  { value: 'abonado', label: 'Abonado' },
  { value: 'reintegro_pendiente', label: 'Reintegro pendiente' },
  { value: 'reintegrado', label: 'Reintegrado' },
  { value: 'anulado', label: 'Anulado' },
];

const ESTADO_COLOR: Record<string, 'warning' | 'success' | 'error' | 'info' | 'default'> = {
  pendiente: 'warning',
  abonado: 'success',
  reintegro_pendiente: 'info',
  reintegrado: 'success',
  anulado: 'error',
};

const hoy = () => new Date().toISOString().slice(0, 10);

interface FormState {
  id_proveedor: string;
  id_moneda: string;
  monto: string;
  referencia_zelle: string;
  fecha: string;
  concepto: string;
}

const formVacio = (): FormState => ({
  id_proveedor: '',
  id_moneda: '',
  monto: '',
  referencia_zelle: '',
  fecha: hoy(),
  concepto: '',
});

const PagosTercerosPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState<EstadoPagoTercero | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: pagos = [], isLoading } = useQuery({
    queryKey: gapsMenoresKeys.pagosTerceros(filtroEstado || null),
    queryFn: () => pagosTercerosService.getAll({ estado: filtroEstado || undefined }),
  });

  const { data: proveedores = [] } = useQuery({
    queryKey: proveedoresKeys.proveedores(empresaId, null),
    queryFn: () => proveedoresService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.listFull(),
    queryFn: fetchMonedas,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gapsMenoresKeys.pagosTercerosAll() });

  const abrirCrear = () => {
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: PagoTerceroPayload) => pagosTercerosService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar el pago.')),
  });

  const anular = useMutation({
    mutationFn: (id: string) => pagosTercerosService.anular(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo anular el pago.')),
  });

  const abonar = useMutation({
    mutationFn: ({ id, cxp }: { id: string; cxp: string }) => pagosTercerosService.abonar(id, cxp),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo abonar el pago.')),
  });

  const solicitarReintegro = useMutation({
    mutationFn: (id: string) => pagosTercerosService.solicitarReintegro(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo solicitar el reintegro.')),
  });

  const marcarReintegrado = useMutation({
    mutationFn: (id: string) => pagosTercerosService.marcarReintegrado(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo marcar el reintegro.')),
  });

  const handleGuardar = () => {
    if (!form.id_moneda || !form.monto.trim()) {
      setErrorMsg('Indique la moneda y el monto del cobro.');
      return;
    }
    guardar.mutate({
      id_proveedor: form.id_proveedor || null,
      id_moneda: form.id_moneda,
      monto: form.monto.trim(),
      referencia_zelle: form.referencia_zelle.trim() || null,
      fecha: form.fecha,
      concepto: form.concepto.trim() || null,
    });
  };

  const handleAbonar = (p: PagoTercero) => {
    const cxp = window.prompt('UUID de la CxP del proveedor a abonar:');
    if (cxp && cxp.trim()) abonar.mutate({ id: p.id_pago_tercero, cxp: cxp.trim() });
  };

  const columns: Column<PagoTercero>[] = [
    { key: 'fecha', header: 'Fecha', render: (p) => p.fecha },
    {
      key: 'proveedor',
      header: 'Proveedor',
      render: (p) => p.proveedor_nombre ?? '— (sin asociar)',
    },
    {
      key: 'monto',
      header: 'Monto',
      render: (p) => `${p.monto} ${p.moneda_codigo ?? ''}`.trim(),
    },
    { key: 'referencia_zelle', header: 'Ref. Zelle', render: (p) => p.referencia_zelle ?? '—' },
    {
      key: 'estado',
      header: 'Estado',
      render: (p) => (
        <StatusChip
          value={p.estado}
          label={ESTADOS.find((e) => e.value === p.estado)?.label ?? p.estado}
          colorMap={ESTADO_COLOR}
        />
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => {
        const pendiente = p.estado === 'pendiente';
        const reintegroPendiente = p.estado === 'reintegro_pendiente';
        return (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              color="success"
              disabled={!pendiente || abonar.isPending}
              onClick={() => handleAbonar(p)}
            >
              Abonar
            </Button>
            <Button
              size="small"
              disabled={!pendiente || solicitarReintegro.isPending}
              onClick={() => solicitarReintegro.mutate(p.id_pago_tercero)}
            >
              Reintegro
            </Button>
            <Button
              size="small"
              disabled={!reintegroPendiente || marcarReintegrado.isPending}
              onClick={() => marcarReintegrado.mutate(p.id_pago_tercero)}
            >
              Marcar reintegrado
            </Button>
            <Button
              size="small"
              color="error"
              disabled={!pendiente || anular.isPending}
              onClick={() => {
                if (window.confirm('¿Anular este pago de tercero?'))
                  anular.mutate(p.id_pago_tercero);
              }}
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
        title="Pagos de Terceros"
        subtitle="Cobros recibidos por Zelle a nombre de terceros: abónalos a una CxP o solicita su reintegro."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo cobro
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
        onChange={(e) => setFiltroEstado(e.target.value as EstadoPagoTercero | '')}
        size="small"
        sx={{ mb: 2, minWidth: 240 }}
      >
        {ESTADOS.map((e) => (
          <MenuItem key={e.value || 'todos'} value={e.value}>
            {e.label}
          </MenuItem>
        ))}
      </TextField>

      <DataTable
        columns={columns}
        rows={pagos}
        getRowKey={(p) => p.id_pago_tercero}
        loading={isLoading}
        emptyMessage="Sin pagos de terceros. Registra el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nuevo cobro de tercero</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Proveedor (opcional)"
              value={form.id_proveedor}
              onChange={(e) => setForm((f) => ({ ...f, id_proveedor: e.target.value }))}
              helperText="Puede asociarse después con la acción correspondiente."
              fullWidth
            >
              <MenuItem value="">— Sin asociar</MenuItem>
              {proveedores.map((p: Proveedor) => (
                <MenuItem key={p.id_proveedor} value={p.id_proveedor}>
                  {p.razon_social}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Monto"
                value={form.monto}
                onChange={(e) => setForm((f) => ({ ...f, monto: e.target.value }))}
                inputMode="decimal"
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
                {monedas.map((m: Moneda) => (
                  <MenuItem key={m.id_moneda} value={m.id_moneda}>
                    {m.codigo_iso} — {m.nombre}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha"
                type="date"
                value={form.fecha}
                onChange={(e) => setForm((f) => ({ ...f, fecha: e.target.value }))}
                slotProps={{ inputLabel: { shrink: true } }}
                fullWidth
              />
              <TextField
                label="Referencia Zelle"
                value={form.referencia_zelle}
                onChange={(e) => setForm((f) => ({ ...f, referencia_zelle: e.target.value }))}
                fullWidth
              />
            </Stack>
            <TextField
              label="Concepto"
              value={form.concepto}
              onChange={(e) => setForm((f) => ({ ...f, concepto: e.target.value }))}
              multiline
              minRows={2}
              fullWidth
            />
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

export default PagosTercerosPage;
