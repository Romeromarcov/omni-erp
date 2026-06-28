import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  proveedoresService,
  contactosProveedorService,
  cuentasBancariasProveedorService,
  type Proveedor,
  type ProveedorPayload,
  type ContactoProveedor,
  type ContactoProveedorPayload,
  type CuentaBancariaProveedor,
  type CuentaBancariaProveedorPayload,
  type TipoCuentaBancaria,
} from '../../services/proveedoresService';
import { fetchMonedas } from '../../services/monedas';
import { proveedoresKeys, finanzasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS_CUENTA: { value: TipoCuentaBancaria; label: string }[] = [
  { value: 'CORRIENTE', label: 'Corriente' },
  { value: 'AHORRO', label: 'Ahorro' },
  { value: 'VISTA', label: 'Vista' },
  { value: 'PLAZO_FIJO', label: 'Plazo Fijo' },
];

interface FormState {
  razon_social: string;
  nombre_comercial: string;
  rif: string;
  direccion: string;
  telefono: string;
  email: string;
  referencia_externa: string;
}

const FORM_VACIO: FormState = {
  razon_social: '',
  nombre_comercial: '',
  rif: '',
  direccion: '',
  telefono: '',
  email: '',
  referencia_externa: '',
};

const ProveedoresPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [busqueda, setBusqueda] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<Proveedor | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<Proveedor | null>(null);

  const { data: proveedores = [], isLoading } = useQuery({
    queryKey: proveedoresKeys.proveedores(empresaId, busqueda),
    queryFn: () =>
      proveedoresService.getAll({
        empresa: empresaId || undefined,
        search: busqueda.trim() || undefined,
      }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: proveedoresKeys.proveedoresAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (p: Proveedor) => {
    setEditando(p);
    setForm({
      razon_social: p.razon_social,
      nombre_comercial: p.nombre_comercial ?? '',
      rif: p.rif,
      direccion: p.direccion ?? '',
      telefono: p.telefono ?? '',
      email: p.email ?? '',
      referencia_externa: p.referencia_externa ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ProveedorPayload) =>
      editando
        ? proveedoresService.update(editando.id_proveedor, payload)
        : proveedoresService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el proveedor.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => proveedoresService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el proveedor.')),
  });

  const handleGuardar = () => {
    if (!form.razon_social.trim() || !form.rif.trim()) {
      setErrorMsg('Complete la razón social y el RIF.');
      return;
    }
    const payload: ProveedorPayload = {
      id_empresa: empresaId,
      razon_social: form.razon_social.trim(),
      nombre_comercial: form.nombre_comercial.trim() || null,
      rif: form.rif.trim(),
      direccion: form.direccion.trim() || null,
      telefono: form.telefono.trim() || null,
      email: form.email.trim() || null,
      referencia_externa: form.referencia_externa.trim() || null,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (p: Proveedor) => {
    if (window.confirm(`¿Eliminar el proveedor "${p.razon_social}"?`)) {
      eliminar.mutate(p.id_proveedor);
    }
  };

  const columns: Column<Proveedor>[] = [
    { key: 'razon_social', header: 'Razón social', render: (p) => p.razon_social },
    { key: 'rif', header: 'RIF', render: (p) => p.rif },
    {
      key: 'nombre_comercial',
      header: 'Nombre comercial',
      render: (p) => p.nombre_comercial || '—',
    },
    { key: 'telefono', header: 'Teléfono', render: (p) => p.telefono || '—' },
    { key: 'email', header: 'Email', render: (p) => p.email || '—' },
    { key: 'activo', header: 'Activo', render: (p) => <StatusChip value={p.activo ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(p)}>
            Detalle
          </Button>
          <Button size="small" onClick={() => abrirEditar(p)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(p)}
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
        title="Proveedores"
        subtitle="Maestro de proveedores: datos fiscales, contactos y cuentas bancarias para pagos."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo proveedor
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <TextField
        label="Buscar"
        placeholder="Razón social o RIF…"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        size="small"
        sx={{ mb: 2, maxWidth: 360 }}
        fullWidth
      />

      <DataTable
        columns={columns}
        rows={proveedores}
        getRowKey={(p) => p.id_proveedor}
        loading={isLoading}
        emptyMessage="Sin proveedores. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar proveedor' : 'Nuevo proveedor'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Razón social"
              value={form.razon_social}
              onChange={(e) => setForm((f) => ({ ...f, razon_social: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="RIF"
              value={form.rif}
              onChange={(e) => setForm((f) => ({ ...f, rif: e.target.value }))}
              required
              helperText="Formato: Letra-Números (p. ej. J-12345678)."
              fullWidth
            />
            <TextField
              label="Nombre comercial"
              value={form.nombre_comercial}
              onChange={(e) => setForm((f) => ({ ...f, nombre_comercial: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Teléfono"
              value={form.telefono}
              onChange={(e) => setForm((f) => ({ ...f, telefono: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Dirección"
              value={form.direccion}
              onChange={(e) => setForm((f) => ({ ...f, direccion: e.target.value }))}
              multiline
              minRows={2}
              fullWidth
            />
            <TextField
              label="Referencia externa"
              value={form.referencia_externa}
              onChange={(e) => setForm((f) => ({ ...f, referencia_externa: e.target.value }))}
              helperText="Código del proveedor en un sistema externo (opcional)."
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

      <Drawer
        anchor="right"
        open={Boolean(detalle)}
        onClose={() => setDetalle(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 520 }, p: 3 } } }}
      >
        {detalle && <DetalleProveedor proveedor={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle del proveedor (contactos, cuentas bancarias) ──────────────────────

interface DetalleProveedorProps {
  proveedor: Proveedor;
  onClose: () => void;
}

const DetalleProveedor: React.FC<DetalleProveedorProps> = ({ proveedor, onClose }) => {
  const proveedorId = proveedor.id_proveedor;

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{proveedor.razon_social}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {proveedor.rif}
        {proveedor.email ? ` · ${proveedor.email}` : ''}
        {proveedor.telefono ? ` · ${proveedor.telefono}` : ''}
      </Typography>

      <Divider />

      <ContactosProveedor proveedorId={proveedorId} />

      <Divider />

      <CuentasBancariasProveedor proveedorId={proveedorId} />
    </Stack>
  );
};

// ── Contactos (CRUD inline) ───────────────────────────────────────────────────

interface ContactoForm {
  nombre: string;
  apellido: string;
  cargo: string;
  telefono: string;
  email: string;
  area_responsabilidad: string;
  es_contacto_principal: boolean;
}

const CONTACTO_VACIO: ContactoForm = {
  nombre: '',
  apellido: '',
  cargo: '',
  telefono: '',
  email: '',
  area_responsabilidad: '',
  es_contacto_principal: false,
};

const ContactosProveedor: React.FC<{ proveedorId: string }> = ({ proveedorId }) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ContactoForm>(CONTACTO_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: contactos = [] } = useQuery({
    queryKey: proveedoresKeys.contactos(proveedorId),
    queryFn: () => contactosProveedorService.getAll({ proveedor: proveedorId }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: proveedoresKeys.contactos(proveedorId) });

  const reset = () => {
    setForm(CONTACTO_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: ContactoProveedorPayload) =>
      editId
        ? contactosProveedorService.update(editId, payload)
        : contactosProveedorService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el contacto.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => contactosProveedorService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el contacto.')),
  });

  const editar = (c: ContactoProveedor) => {
    setEditId(c.id_contacto);
    setForm({
      nombre: c.nombre,
      apellido: c.apellido,
      cargo: c.cargo ?? '',
      telefono: c.telefono ?? '',
      email: c.email ?? '',
      area_responsabilidad: c.area_responsabilidad ?? '',
      es_contacto_principal: c.es_contacto_principal,
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.nombre.trim() || !form.apellido.trim()) {
      setError('Complete nombre y apellido del contacto.');
      return;
    }
    guardar.mutate({
      id_proveedor: proveedorId,
      nombre: form.nombre.trim(),
      apellido: form.apellido.trim(),
      cargo: form.cargo.trim() || null,
      telefono: form.telefono.trim() || null,
      email: form.email.trim() || null,
      area_responsabilidad: form.area_responsabilidad.trim() || null,
      es_contacto_principal: form.es_contacto_principal,
      observaciones: null,
    });
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Contactos
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Stack spacing={1} sx={{ mb: 2 }}>
        {contactos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin contactos.
          </Typography>
        ) : (
          contactos.map((c) => (
            <Stack
              key={c.id_contacto}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {c.nombre} {c.apellido}
                {c.cargo ? ` · ${c.cargo}` : ''}
                {c.email ? ` · ${c.email}` : ''}
                {c.es_contacto_principal ? ' · Principal' : ''}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(c)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(c.id_contacto)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Nombre"
            value={form.nombre}
            onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="Apellido"
            value={form.apellido}
            onChange={(e) => setForm((f) => ({ ...f, apellido: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
        <TextField
          label="Email"
          type="email"
          value={form.email}
          onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <TextField
            label="Cargo"
            value={form.cargo}
            onChange={(e) => setForm((f) => ({ ...f, cargo: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="Teléfono"
            value={form.telefono}
            onChange={(e) => setForm((f) => ({ ...f, telefono: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
        <TextField
          label="Área de responsabilidad"
          value={form.area_responsabilidad}
          onChange={(e) => setForm((f) => ({ ...f, area_responsabilidad: e.target.value }))}
          size="small"
          fullWidth
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={form.es_contacto_principal}
              onChange={(e) =>
                setForm((f) => ({ ...f, es_contacto_principal: e.target.checked }))
              }
            />
          }
          label="Contacto principal"
        />
        <Stack direction="row" spacing={1}>
          <Button
            variant="contained"
            size="small"
            onClick={handleGuardar}
            disabled={guardar.isPending}
          >
            {editId ? 'Actualizar contacto' : 'Agregar contacto'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Box>
  );
};

// ── Cuentas bancarias (CRUD inline) ───────────────────────────────────────────

interface CuentaForm {
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuentaBancaria;
  moneda: string;
  titular_cuenta: string;
  identificacion_titular: string;
  es_cuenta_principal: boolean;
}

const CUENTA_VACIA: CuentaForm = {
  nombre_banco: '',
  numero_cuenta: '',
  tipo_cuenta: 'CORRIENTE',
  moneda: '',
  titular_cuenta: '',
  identificacion_titular: '',
  es_cuenta_principal: false,
};

const CuentasBancariasProveedor: React.FC<{ proveedorId: string }> = ({ proveedorId }) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CuentaForm>(CUENTA_VACIA);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: cuentas = [] } = useQuery({
    queryKey: proveedoresKeys.cuentasBancarias(proveedorId),
    queryFn: () => cuentasBancariasProveedorService.getAll({ proveedor: proveedorId }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: fetchMonedas,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: proveedoresKeys.cuentasBancarias(proveedorId) });

  const reset = () => {
    setForm(CUENTA_VACIA);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: CuentaBancariaProveedorPayload) =>
      editId
        ? cuentasBancariasProveedorService.update(editId, payload)
        : cuentasBancariasProveedorService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar la cuenta.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => cuentasBancariasProveedorService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar la cuenta.')),
  });

  const editar = (c: CuentaBancariaProveedor) => {
    setEditId(c.id_cuenta_bancaria);
    setForm({
      nombre_banco: c.nombre_banco,
      numero_cuenta: c.numero_cuenta,
      tipo_cuenta: c.tipo_cuenta,
      moneda: c.moneda,
      titular_cuenta: c.titular_cuenta ?? '',
      identificacion_titular: c.identificacion_titular ?? '',
      es_cuenta_principal: c.es_cuenta_principal,
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.nombre_banco.trim() || !form.numero_cuenta.trim() || !form.moneda.trim()) {
      setError('Complete banco, número de cuenta y moneda.');
      return;
    }
    guardar.mutate({
      id_proveedor: proveedorId,
      nombre_banco: form.nombre_banco.trim(),
      numero_cuenta: form.numero_cuenta.trim(),
      tipo_cuenta: form.tipo_cuenta,
      moneda: form.moneda,
      titular_cuenta: form.titular_cuenta.trim() || null,
      identificacion_titular: form.identificacion_titular.trim() || null,
      es_cuenta_principal: form.es_cuenta_principal,
      observaciones: null,
    });
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Cuentas bancarias
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Stack spacing={1} sx={{ mb: 2 }}>
        {cuentas.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin cuentas bancarias.
          </Typography>
        ) : (
          cuentas.map((c) => (
            <Stack
              key={c.id_cuenta_bancaria}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {c.nombre_banco} · {c.numero_cuenta} · {c.tipo_cuenta}
                {c.es_cuenta_principal ? ' · Principal' : ''}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(c)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(c.id_cuenta_bancaria)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Banco"
            value={form.nombre_banco}
            onChange={(e) => setForm((f) => ({ ...f, nombre_banco: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="Número de cuenta"
            value={form.numero_cuenta}
            onChange={(e) => setForm((f) => ({ ...f, numero_cuenta: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
        <Stack direction="row" spacing={1}>
          <TextField
            select
            label="Tipo de cuenta"
            value={form.tipo_cuenta}
            onChange={(e) =>
              setForm((f) => ({ ...f, tipo_cuenta: e.target.value as TipoCuentaBancaria }))
            }
            size="small"
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
            size="small"
            fullWidth
          >
            {monedas.map((m) => (
              <MenuItem key={m.id_moneda} value={m.id_moneda}>
                {m.codigo_iso} — {m.nombre}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Titular"
            value={form.titular_cuenta}
            onChange={(e) => setForm((f) => ({ ...f, titular_cuenta: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="Identificación titular"
            value={form.identificacion_titular}
            onChange={(e) =>
              setForm((f) => ({ ...f, identificacion_titular: e.target.value }))
            }
            size="small"
            fullWidth
          />
        </Stack>
        <FormControlLabel
          control={
            <Checkbox
              checked={form.es_cuenta_principal}
              onChange={(e) =>
                setForm((f) => ({ ...f, es_cuenta_principal: e.target.checked }))
              }
            />
          }
          label="Cuenta principal"
        />
        <Stack direction="row" spacing={1}>
          <Button
            variant="contained"
            size="small"
            onClick={handleGuardar}
            disabled={guardar.isPending}
          >
            {editId ? 'Actualizar cuenta' : 'Agregar cuenta'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Box>
  );
};

export default ProveedoresPage;
