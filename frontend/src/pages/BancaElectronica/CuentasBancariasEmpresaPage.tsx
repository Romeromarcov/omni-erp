import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Checkbox,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  cuentasBancariasEmpresaService,
  type CuentaBancariaEmpresa,
  type CuentaBancariaEmpresaPayload,
  type TipoCuenta,
} from '../../services/bancaElectronicaService';
import { fetchMonedas } from '../../services/monedas';
import { bancaElectronicaKeys, finanzasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS_CUENTA: { value: TipoCuenta; label: string }[] = [
  { value: 'corriente', label: 'Corriente' },
  { value: 'ahorro', label: 'Ahorro' },
];

interface FormState {
  banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuenta;
  moneda: string;
  saldo_actual: string;
  activa: boolean;
}

const FORM_VACIO: FormState = {
  banco: '',
  numero_cuenta: '',
  tipo_cuenta: 'corriente',
  moneda: '',
  saldo_actual: '0',
  activa: true,
};

const CuentasBancariasEmpresaPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CuentaBancariaEmpresa | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: cuentas = [], isLoading } = useQuery({
    queryKey: bancaElectronicaKeys.cuentas(empresaId),
    queryFn: () =>
      cuentasBancariasEmpresaService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: () => fetchMonedas(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: bancaElectronicaKeys.cuentasAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CuentaBancariaEmpresa) => {
    setEditando(c);
    setForm({
      banco: c.banco,
      numero_cuenta: c.numero_cuenta,
      tipo_cuenta: c.tipo_cuenta,
      moneda: c.moneda,
      saldo_actual: c.saldo_actual ?? '0',
      activa: c.activa ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CuentaBancariaEmpresaPayload) =>
      editando
        ? cuentasBancariasEmpresaService.update(editando.id, payload)
        : cuentasBancariasEmpresaService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la cuenta.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => cuentasBancariasEmpresaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la cuenta.')),
  });

  const handleGuardar = () => {
    if (!form.banco.trim() || !form.numero_cuenta.trim() || !form.moneda) {
      setErrorMsg('Complete el banco, el número de cuenta y la moneda.');
      return;
    }
    const payload: CuentaBancariaEmpresaPayload = {
      empresa: empresaId,
      banco: form.banco.trim(),
      numero_cuenta: form.numero_cuenta.trim(),
      tipo_cuenta: form.tipo_cuenta,
      moneda: form.moneda,
      saldo_actual: form.saldo_actual.trim() || '0',
      activa: form.activa,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (c: CuentaBancariaEmpresa) => {
    if (window.confirm(`¿Eliminar la cuenta "${c.banco} - ${c.numero_cuenta}"?`)) {
      eliminar.mutate(c.id);
    }
  };

  const nombreMoneda = (id: string) => {
    const m = monedas.find((mo) => mo.id_moneda === id);
    return m ? m.codigo_iso : id;
  };

  const columns: Column<CuentaBancariaEmpresa>[] = [
    { key: 'banco', header: 'Banco', render: (c) => c.banco },
    { key: 'numero_cuenta', header: 'Número', render: (c) => c.numero_cuenta },
    {
      key: 'tipo_cuenta',
      header: 'Tipo',
      render: (c) => (c.tipo_cuenta === 'ahorro' ? 'Ahorro' : 'Corriente'),
    },
    { key: 'moneda', header: 'Moneda', render: (c) => nombreMoneda(c.moneda) },
    { key: 'saldo_actual', header: 'Saldo', render: (c) => c.saldo_actual },
    { key: 'activa', header: 'Activa', render: (c) => <StatusChip value={c.activa ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(c)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(c)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Banca Electrónica"
        subtitle="Cuentas bancarias de la empresa para banca electrónica."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nueva cuenta
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
        rows={cuentas}
        getRowKey={(c) => c.id}
        loading={isLoading}
        emptyMessage="Sin cuentas bancarias. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar cuenta' : 'Nueva cuenta'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Banco"
              value={form.banco}
              onChange={(e) => setForm((f) => ({ ...f, banco: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Número de cuenta"
              value={form.numero_cuenta}
              onChange={(e) => setForm((f) => ({ ...f, numero_cuenta: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Tipo de cuenta"
              value={form.tipo_cuenta}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_cuenta: e.target.value as TipoCuenta }))
              }
              fullWidth
            >
              {TIPOS_CUENTA.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Moneda"
              value={form.moneda}
              onChange={(e) => setForm((f) => ({ ...f, moneda: e.target.value }))}
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
              label="Saldo actual"
              value={form.saldo_actual}
              onChange={(e) => setForm((f) => ({ ...f, saldo_actual: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activa}
                  onChange={(e) => setForm((f) => ({ ...f, activa: e.target.checked }))}
                />
              }
              label="Activa"
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

export default CuentasBancariasEmpresaPage;
