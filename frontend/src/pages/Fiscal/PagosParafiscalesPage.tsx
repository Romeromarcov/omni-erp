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
  pagosParafiscalesService,
  fetchCajasEmpresa,
  type PagoParafiscal,
  type PagoParafiscalPayload,
  type PagarParafiscalBody,
  type EstadoPagoParafiscal,
  type CajaOption,
} from '../../services/gapsMenoresService';
import { fetchMonedas, type Moneda } from '../../services/monedas';
import {
  fetchMetodosPagoEmpresaActivos,
  type MetodoPagoEmpresaActiva,
} from '../../services/metodosPagoEmpresaActiva';
import { gapsMenoresKeys, finanzasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const ESTADOS: { value: EstadoPagoParafiscal | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'pendiente', label: 'Pendiente' },
  { value: 'pagado', label: 'Pagado' },
  { value: 'anulado', label: 'Anulado' },
];

const ESTADO_COLOR: Record<string, 'warning' | 'success' | 'error' | 'default'> = {
  pendiente: 'warning',
  pagado: 'success',
  anulado: 'error',
};

const ahora = new Date();

interface FormState {
  contribucion: string;
  periodo_año: string;
  periodo_mes: string;
  monto: string;
  id_moneda: string;
}

const formVacio = (): FormState => ({
  contribucion: '',
  periodo_año: String(ahora.getFullYear()),
  periodo_mes: String(ahora.getMonth() + 1),
  monto: '',
  id_moneda: '',
});

interface PagarForm {
  metodo_pago: string;
  origen: 'caja' | 'cuenta_bancaria';
  caja: string;
  cuenta_bancaria: string;
  referencia: string;
}

const pagarVacio = (): PagarForm => ({
  metodo_pago: '',
  origen: 'caja',
  caja: '',
  cuenta_bancaria: '',
  referencia: '',
});

const PagosParafiscalesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState<EstadoPagoParafiscal | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FormState>(formVacio());
  const [pagarPago, setPagarPago] = useState<PagoParafiscal | null>(null);
  const [pagarForm, setPagarForm] = useState<PagarForm>(pagarVacio());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: pagos = [], isLoading } = useQuery({
    queryKey: gapsMenoresKeys.pagosParafiscales(filtroEstado || null),
    queryFn: () => pagosParafiscalesService.getAll({ estado: filtroEstado || undefined }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.listFull(),
    queryFn: fetchMonedas,
  });

  const { data: metodos = [] } = useQuery({
    queryKey: finanzasKeys.metodosPagoEmpresaActivas(empresaId),
    queryFn: () => fetchMetodosPagoEmpresaActivos(empresaId),
    enabled: Boolean(empresaId),
  });

  const { data: cajas = [] } = useQuery({
    queryKey: finanzasKeys.cajasFisicas.list(empresaId),
    queryFn: () => fetchCajasEmpresa(empresaId),
    enabled: Boolean(empresaId),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gapsMenoresKeys.pagosParafiscalesAll() });

  const abrirCrear = () => {
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: PagoParafiscalPayload) => pagosParafiscalesService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo declarar el período.')),
  });

  const pagar = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PagarParafiscalBody }) =>
      pagosParafiscalesService.pagar(id, body),
    onSuccess: () => {
      setPagarPago(null);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo ejecutar el pago.')),
  });

  const anular = useMutation({
    mutationFn: (id: string) => pagosParafiscalesService.anular(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo anular el pago.')),
  });

  const handleGuardar = () => {
    if (!form.contribucion.trim() || !form.monto.trim() || !form.id_moneda) {
      setErrorMsg('Indique la contribución, el monto y la moneda.');
      return;
    }
    guardar.mutate({
      contribucion: form.contribucion.trim(),
      periodo_año: Number(form.periodo_año),
      periodo_mes: Number(form.periodo_mes),
      monto: form.monto.trim(),
      id_moneda: form.id_moneda,
    });
  };

  const abrirPagar = (p: PagoParafiscal) => {
    setPagarPago(p);
    setPagarForm(pagarVacio());
    setErrorMsg('');
  };

  const handlePagar = () => {
    if (!pagarPago) return;
    if (!pagarForm.metodo_pago) {
      setErrorMsg('Seleccione el método de pago.');
      return;
    }
    const esCaja = pagarForm.origen === 'caja';
    if (esCaja && !pagarForm.caja) {
      setErrorMsg('Seleccione la caja de origen de fondos.');
      return;
    }
    if (!esCaja && !pagarForm.cuenta_bancaria) {
      setErrorMsg('Indique la cuenta bancaria de origen.');
      return;
    }
    const body: PagarParafiscalBody = {
      metodo_pago: pagarForm.metodo_pago,
      referencia: pagarForm.referencia.trim() || undefined,
    };
    if (esCaja) body.caja = pagarForm.caja;
    else body.cuenta_bancaria = pagarForm.cuenta_bancaria.trim();
    pagar.mutate({ id: pagarPago.id_pago_parafiscal, body });
  };

  const columns: Column<PagoParafiscal>[] = [
    {
      key: 'contribucion',
      header: 'Contribución',
      render: (p) => p.contribucion_codigo ?? p.contribucion_nombre ?? p.contribucion,
    },
    { key: 'periodo', header: 'Período', render: (p) => p.periodo },
    {
      key: 'monto',
      header: 'Monto',
      render: (p) => `${p.monto} ${p.moneda_codigo ?? ''}`.trim(),
    },
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
        return (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              color="success"
              disabled={!pendiente || pagar.isPending}
              onClick={() => abrirPagar(p)}
            >
              Pagar
            </Button>
            <Button
              size="small"
              color="error"
              disabled={!pendiente || anular.isPending}
              onClick={() => {
                if (window.confirm('¿Anular este pago parafiscal?'))
                  anular.mutate(p.id_pago_parafiscal);
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
        title="Pagos Parafiscales"
        subtitle="Contribuciones parafiscales (IVSS, INCES, FAOV): declara el período por pagar y ejecútalo desde caja o banco."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Declarar período
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
        onChange={(e) => setFiltroEstado(e.target.value as EstadoPagoParafiscal | '')}
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
        getRowKey={(p) => p.id_pago_parafiscal}
        loading={isLoading}
        emptyMessage="Sin pagos parafiscales. Declara el primer período."
      />

      {/* Alta: declarar período */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Declarar período parafiscal</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Contribución (UUID)"
              value={form.contribucion}
              onChange={(e) => setForm((f) => ({ ...f, contribucion: e.target.value }))}
              required
              helperText="Identificador de la contribución parafiscal (IVSS / INCES / FAOV)."
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Año"
                value={form.periodo_año}
                onChange={(e) => setForm((f) => ({ ...f, periodo_año: e.target.value }))}
                inputMode="numeric"
                required
                fullWidth
              />
              <TextField
                label="Mes"
                value={form.periodo_mes}
                onChange={(e) => setForm((f) => ({ ...f, periodo_mes: e.target.value }))}
                inputMode="numeric"
                required
                fullWidth
              />
            </Stack>
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleGuardar} disabled={guardar.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Acción: pagar */}
      <Dialog open={Boolean(pagarPago)} onClose={() => setPagarPago(null)} fullWidth maxWidth="sm">
        <DialogTitle>Ejecutar pago parafiscal</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Método de pago"
              value={pagarForm.metodo_pago}
              onChange={(e) => setPagarForm((f) => ({ ...f, metodo_pago: e.target.value }))}
              required
              fullWidth
            >
              {metodos.map((m: MetodoPagoEmpresaActiva) => (
                <MenuItem key={m.metodo_pago} value={m.metodo_pago}>
                  {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Origen de fondos"
              value={pagarForm.origen}
              onChange={(e) =>
                setPagarForm((f) => ({ ...f, origen: e.target.value as 'caja' | 'cuenta_bancaria' }))
              }
              fullWidth
            >
              <MenuItem value="caja">Caja</MenuItem>
              <MenuItem value="cuenta_bancaria">Cuenta bancaria</MenuItem>
            </TextField>
            {pagarForm.origen === 'caja' ? (
              <TextField
                select
                label="Caja"
                value={pagarForm.caja}
                onChange={(e) => setPagarForm((f) => ({ ...f, caja: e.target.value }))}
                required
                fullWidth
              >
                {cajas.map((c: CajaOption) => (
                  <MenuItem key={c.id_caja} value={c.id_caja}>
                    {c.nombre}
                  </MenuItem>
                ))}
              </TextField>
            ) : (
              <TextField
                label="Cuenta bancaria (UUID)"
                value={pagarForm.cuenta_bancaria}
                onChange={(e) =>
                  setPagarForm((f) => ({ ...f, cuenta_bancaria: e.target.value }))
                }
                required
                fullWidth
              />
            )}
            <TextField
              label="Referencia (opcional)"
              value={pagarForm.referencia}
              onChange={(e) => setPagarForm((f) => ({ ...f, referencia: e.target.value }))}
              helperText="Nº de planilla u operación."
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPagarPago(null)}>Cancelar</Button>
          <Button variant="contained" onClick={handlePagar} disabled={pagar.isPending}>
            Pagar
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
};

export default PagosParafiscalesPage;
