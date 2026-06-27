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
import { PageContainer, PageHeader, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  movimientosInternosFondoService,
  fetchCajasEmpresa,
  type MovimientoInternoFondo,
  type MovimientoInternoFondoPayload,
  type CajaOption,
} from '../../services/gapsMenoresService';
import { fetchMonedas, type Moneda } from '../../services/monedas';
import { gapsMenoresKeys, finanzasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

interface FormState {
  caja_origen: string;
  caja_destino: string;
  monto: string;
  id_moneda: string;
  referencia_externa: string;
  descripcion: string;
}

const FORM_VACIO: FormState = {
  caja_origen: '',
  caja_destino: '',
  monto: '',
  id_moneda: '',
  referencia_externa: '',
  descripcion: '',
};

const MovimientosInternosFondoPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: movimientos = [], isLoading } = useQuery({
    queryKey: gapsMenoresKeys.movimientosInternos(),
    queryFn: () => movimientosInternosFondoService.getAll(),
  });

  const { data: cajas = [] } = useQuery({
    queryKey: finanzasKeys.cajasFisicas.list(empresaId),
    queryFn: () => fetchCajasEmpresa(empresaId),
    enabled: Boolean(empresaId),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.listFull(),
    queryFn: fetchMonedas,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gapsMenoresKeys.movimientosInternosAll() });

  const abrirCrear = () => {
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: MovimientoInternoFondoPayload) =>
      movimientosInternosFondoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar el movimiento.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: number) => movimientosInternosFondoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el movimiento.')),
  });

  const handleGuardar = () => {
    if (!form.caja_origen || !form.caja_destino || !form.monto.trim()) {
      setErrorMsg('Seleccione caja origen, caja destino e indique el monto.');
      return;
    }
    if (form.caja_origen === form.caja_destino) {
      setErrorMsg('La caja de origen y la de destino deben ser distintas.');
      return;
    }
    guardar.mutate({
      caja_origen: form.caja_origen,
      caja_destino: form.caja_destino,
      monto: form.monto.trim(),
      id_moneda: form.id_moneda || null,
      referencia_externa: form.referencia_externa.trim() || null,
      descripcion: form.descripcion.trim() || null,
    });
  };

  const nombreCaja = (id: string) =>
    cajas.find((c: CajaOption) => c.id_caja === id)?.nombre ?? id;

  const columns: Column<MovimientoInternoFondo>[] = [
    { key: 'fecha', header: 'Fecha', render: (m) => (m.fecha ? m.fecha.slice(0, 10) : '—') },
    { key: 'caja_origen', header: 'Origen', render: (m) => nombreCaja(m.caja_origen) },
    { key: 'caja_destino', header: 'Destino', render: (m) => nombreCaja(m.caja_destino) },
    { key: 'monto', header: 'Monto', render: (m) => m.monto },
    { key: 'descripcion', header: 'Descripción', render: (m) => m.descripcion ?? '—' },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (m) => (
        <Button
          size="small"
          color="error"
          disabled={eliminar.isPending}
          onClick={() => {
            if (window.confirm('¿Eliminar este movimiento interno?')) eliminar.mutate(m.id);
          }}
        >
          Eliminar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Movimientos Internos de Fondo"
        subtitle="Transferencias de fondos entre cajas de la empresa. El sistema genera los asientos de caja correspondientes."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo movimiento
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={movimientos}
        getRowKey={(m) => String(m.id)}
        loading={isLoading}
        emptyMessage="Sin movimientos internos. Registra el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nuevo movimiento interno</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Caja origen"
              value={form.caja_origen}
              onChange={(e) => setForm((f) => ({ ...f, caja_origen: e.target.value }))}
              required
              fullWidth
            >
              {cajas.map((c: CajaOption) => (
                <MenuItem key={c.id_caja} value={c.id_caja}>
                  {c.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Caja destino"
              value={form.caja_destino}
              onChange={(e) => setForm((f) => ({ ...f, caja_destino: e.target.value }))}
              required
              fullWidth
            >
              {cajas.map((c: CajaOption) => (
                <MenuItem key={c.id_caja} value={c.id_caja}>
                  {c.nombre}
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
                fullWidth
              >
                <MenuItem value="">—</MenuItem>
                {monedas.map((m: Moneda) => (
                  <MenuItem key={m.id_moneda} value={m.id_moneda}>
                    {m.codigo_iso} — {m.nombre}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              label="Referencia externa"
              value={form.referencia_externa}
              onChange={(e) => setForm((f) => ({ ...f, referencia_externa: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
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

export default MovimientosInternosFondoPage;
