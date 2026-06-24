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
  clientesService,
  contactosClienteService,
  direccionesClienteService,
  type Cliente,
  type ClientePayload,
  type ContactoCliente,
  type ContactoClientePayload,
  type DireccionCliente,
  type DireccionClientePayload,
  type TipoCliente,
  type TipoDireccion,
} from '../../services/clientesService';
import { crmKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS_CLIENTE: { value: TipoCliente; label: string }[] = [
  { value: 'CONTADO', label: 'Contado' },
  { value: 'CREDITO', label: 'Crédito' },
];

const TIPOS_DIRECCION: { value: TipoDireccion; label: string }[] = [
  { value: 'FISCAL', label: 'Fiscal' },
  { value: 'COMERCIAL', label: 'Comercial' },
  { value: 'ENTREGA', label: 'Entrega' },
  { value: 'FACTURACION', label: 'Facturación' },
  { value: 'OTRA', label: 'Otra' },
];

interface FormState {
  razon_social: string;
  nombre_comercial: string;
  rif: string;
  direccion: string;
  telefono: string;
  email: string;
  tipo_cliente: TipoCliente;
  limite_credito: string;
  dias_credito: string;
}

const FORM_VACIO: FormState = {
  razon_social: '',
  nombre_comercial: '',
  rif: '',
  direccion: '',
  telefono: '',
  email: '',
  tipo_cliente: 'CONTADO',
  limite_credito: '0',
  dias_credito: '0',
};

const ClientesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [busqueda, setBusqueda] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<Cliente | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<Cliente | null>(null);

  const { data: clientes = [], isLoading } = useQuery({
    queryKey: crmKeys.clientes(empresaId, busqueda),
    queryFn: () =>
      clientesService.getAll({
        empresa: empresaId || undefined,
        search: busqueda.trim() || undefined,
      }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: crmKeys.clientesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: Cliente) => {
    setEditando(c);
    setForm({
      razon_social: c.razon_social,
      nombre_comercial: c.nombre_comercial ?? '',
      rif: c.rif,
      direccion: c.direccion ?? '',
      telefono: c.telefono ?? '',
      email: c.email ?? '',
      tipo_cliente: c.tipo_cliente ?? 'CONTADO',
      limite_credito: c.limite_credito ?? '0',
      dias_credito: String(c.dias_credito ?? 0),
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ClientePayload) =>
      editando
        ? clientesService.update(editando.id_cliente, payload)
        : clientesService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el cliente.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => clientesService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el cliente.')),
  });

  const handleGuardar = () => {
    if (!form.razon_social.trim() || !form.rif.trim()) {
      setErrorMsg('Complete la razón social y el RIF.');
      return;
    }
    const esCredito = form.tipo_cliente === 'CREDITO';
    const payload: ClientePayload = {
      id_empresa: empresaId,
      razon_social: form.razon_social.trim(),
      nombre_comercial: form.nombre_comercial.trim() || null,
      rif: form.rif.trim(),
      direccion: form.direccion.trim() || null,
      telefono: form.telefono.trim() || null,
      email: form.email.trim() || null,
      tipo_cliente: form.tipo_cliente,
      // Crédito y días solo aplican a clientes de crédito; contado siempre 0.
      limite_credito: esCredito ? form.limite_credito.trim() || '0' : '0',
      dias_credito: esCredito ? Number(form.dias_credito) || 0 : 0,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (c: Cliente) => {
    if (window.confirm(`¿Eliminar el cliente "${c.razon_social}"?`)) {
      eliminar.mutate(c.id_cliente);
    }
  };

  const columns: Column<Cliente>[] = [
    { key: 'razon_social', header: 'Razón social', render: (c) => c.razon_social },
    { key: 'rif', header: 'RIF', render: (c) => c.rif },
    { key: 'nombre_comercial', header: 'Nombre comercial', render: (c) => c.nombre_comercial || '—' },
    { key: 'telefono', header: 'Teléfono', render: (c) => c.telefono || '—' },
    { key: 'tipo', header: 'Tipo', render: (c) => c.tipo_cliente || 'CONTADO' },
    { key: 'activo', header: 'Activo', render: (c) => <StatusChip value={c.activo ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(c)}>
            Detalle
          </Button>
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

  const esCredito = form.tipo_cliente === 'CREDITO';

  return (
    <PageContainer>
      <PageHeader
        title="Clientes"
        subtitle="Maestro de clientes (CRM): datos fiscales, crédito, contactos y direcciones."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo cliente
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
        rows={clientes}
        getRowKey={(c) => c.id_cliente}
        loading={isLoading}
        emptyMessage="Sin clientes. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar cliente' : 'Nuevo cliente'}</DialogTitle>
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
              select
              label="Tipo de cliente"
              value={form.tipo_cliente}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_cliente: e.target.value as TipoCliente }))
              }
              fullWidth
            >
              {TIPOS_CLIENTE.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            {esCredito && (
              <>
                <TextField
                  label="Límite de crédito"
                  value={form.limite_credito}
                  onChange={(e) => setForm((f) => ({ ...f, limite_credito: e.target.value }))}
                  inputMode="decimal"
                  helperText="0 = sin límite definido."
                  fullWidth
                />
                <TextField
                  label="Días de crédito"
                  value={form.dias_credito}
                  onChange={(e) => setForm((f) => ({ ...f, dias_credito: e.target.value }))}
                  inputMode="numeric"
                  fullWidth
                />
              </>
            )}
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
        {detalle && <DetalleCliente cliente={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle del cliente (crédito, historial, contactos, direcciones) ──────────

interface DetalleClienteProps {
  cliente: Cliente;
  onClose: () => void;
}

const DetalleCliente: React.FC<DetalleClienteProps> = ({ cliente, onClose }) => {
  const clienteId = cliente.id_cliente;

  const { data: credito } = useQuery({
    queryKey: crmKeys.creditoDisponible(clienteId),
    queryFn: () => clientesService.creditoDisponible(clienteId),
  });
  const { data: historial } = useQuery({
    queryKey: crmKeys.historialVentas(clienteId),
    queryFn: () => clientesService.historialVentas(clienteId),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{cliente.razon_social}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {cliente.rif} · {cliente.tipo_cliente || 'CONTADO'}
      </Typography>

      <Divider />

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Crédito disponible
        </Typography>
        {credito?.credito_disponible == null ? (
          <Typography variant="body2" color="text.secondary">
            {credito?.detalle || 'Cliente de contado.'}
          </Typography>
        ) : (
          <Typography variant="body2">
            Disponible: {credito.credito_disponible} · Límite: {credito.limite_credito} · Saldo
            pendiente: {credito.saldo_pendiente}
            {credito.bloqueado ? ' · BLOQUEADO' : ''}
          </Typography>
        )}
      </Box>

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Historial de ventas
        </Typography>
        {!historial || historial.pedidos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin pedidos registrados.
          </Typography>
        ) : (
          <Stack spacing={0.5}>
            {historial.pedidos.slice(0, 10).map((p) => (
              <Typography key={p.id_pedido} variant="body2">
                {p.numero_pedido} · {p.fecha_pedido} · {p.estado}
              </Typography>
            ))}
          </Stack>
        )}
      </Box>

      <Divider />

      <ContactosCliente clienteId={clienteId} empresaId={cliente.id_empresa || ''} />

      <Divider />

      <DireccionesCliente clienteId={clienteId} empresaId={cliente.id_empresa || ''} />
    </Stack>
  );
};

// ── Contactos (CRUD inline) ───────────────────────────────────────────────────

interface ContactoForm {
  nombre_contacto: string;
  apellido_contacto: string;
  cargo: string;
  telefono_movil: string;
  email_contacto: string;
  es_contacto_principal: boolean;
}

const CONTACTO_VACIO: ContactoForm = {
  nombre_contacto: '',
  apellido_contacto: '',
  cargo: '',
  telefono_movil: '',
  email_contacto: '',
  es_contacto_principal: false,
};

const ContactosCliente: React.FC<{ clienteId: string; empresaId: string }> = ({
  clienteId,
  empresaId,
}) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ContactoForm>(CONTACTO_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: contactos = [] } = useQuery({
    queryKey: crmKeys.contactos(clienteId),
    queryFn: () => contactosClienteService.getAll({ cliente: clienteId }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: crmKeys.contactos(clienteId) });

  const reset = () => {
    setForm(CONTACTO_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: ContactoClientePayload) =>
      editId
        ? contactosClienteService.update(editId, payload)
        : contactosClienteService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar el contacto.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => contactosClienteService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar el contacto.')),
  });

  const editar = (c: ContactoCliente) => {
    setEditId(c.id_contacto);
    setForm({
      nombre_contacto: c.nombre_contacto,
      apellido_contacto: c.apellido_contacto,
      cargo: c.cargo ?? '',
      telefono_movil: c.telefono_movil ?? '',
      email_contacto: c.email_contacto,
      es_contacto_principal: c.es_contacto_principal,
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.nombre_contacto.trim() || !form.apellido_contacto.trim() || !form.email_contacto.trim()) {
      setError('Complete nombre, apellido y email del contacto.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_cliente: clienteId,
      nombre_contacto: form.nombre_contacto.trim(),
      apellido_contacto: form.apellido_contacto.trim(),
      cargo: form.cargo.trim() || null,
      telefono_directo: null,
      telefono_movil: form.telefono_movil.trim() || null,
      email_contacto: form.email_contacto.trim(),
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
                {c.nombre_contacto} {c.apellido_contacto}
                {c.cargo ? ` · ${c.cargo}` : ''} · {c.email_contacto}
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
            value={form.nombre_contacto}
            onChange={(e) => setForm((f) => ({ ...f, nombre_contacto: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="Apellido"
            value={form.apellido_contacto}
            onChange={(e) => setForm((f) => ({ ...f, apellido_contacto: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
        <TextField
          label="Email"
          type="email"
          value={form.email_contacto}
          onChange={(e) => setForm((f) => ({ ...f, email_contacto: e.target.value }))}
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
            label="Móvil"
            value={form.telefono_movil}
            onChange={(e) => setForm((f) => ({ ...f, telefono_movil: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
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

// ── Direcciones (CRUD inline) ─────────────────────────────────────────────────

interface DireccionForm {
  tipo_direccion: TipoDireccion;
  direccion_completa: string;
  ciudad: string;
  estado_provincia: string;
  es_direccion_principal: boolean;
}

const DIRECCION_VACIA: DireccionForm = {
  tipo_direccion: 'FISCAL',
  direccion_completa: '',
  ciudad: '',
  estado_provincia: '',
  es_direccion_principal: false,
};

const DireccionesCliente: React.FC<{ clienteId: string; empresaId: string }> = ({
  clienteId,
  empresaId,
}) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<DireccionForm>(DIRECCION_VACIA);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: direcciones = [] } = useQuery({
    queryKey: crmKeys.direcciones(clienteId),
    queryFn: () => direccionesClienteService.getAll({ cliente: clienteId }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: crmKeys.direcciones(clienteId) });

  const reset = () => {
    setForm(DIRECCION_VACIA);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: DireccionClientePayload) =>
      editId
        ? direccionesClienteService.update(editId, payload)
        : direccionesClienteService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar la dirección.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => direccionesClienteService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar la dirección.')),
  });

  const editar = (d: DireccionCliente) => {
    setEditId(d.id_direccion);
    setForm({
      tipo_direccion: d.tipo_direccion,
      direccion_completa: d.direccion_completa,
      ciudad: d.ciudad,
      estado_provincia: d.estado_provincia,
      es_direccion_principal: d.es_direccion_principal,
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.direccion_completa.trim() || !form.ciudad.trim() || !form.estado_provincia.trim()) {
      setError('Complete dirección, ciudad y estado/provincia.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      id_cliente: clienteId,
      tipo_direccion: form.tipo_direccion,
      direccion_completa: form.direccion_completa.trim(),
      ciudad: form.ciudad.trim(),
      estado_provincia: form.estado_provincia.trim(),
      codigo_postal: null,
      pais: 'Venezuela',
      telefono: null,
      persona_contacto: null,
      es_direccion_principal: form.es_direccion_principal,
      observaciones: null,
    });
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Direcciones
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Stack spacing={1} sx={{ mb: 2 }}>
        {direcciones.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin direcciones.
          </Typography>
        ) : (
          direcciones.map((d) => (
            <Stack
              key={d.id_direccion}
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="body2">
                {d.tipo_direccion} · {d.direccion_completa} · {d.ciudad}, {d.estado_provincia}
                {d.es_direccion_principal ? ' · Principal' : ''}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_direccion)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>
      <Stack spacing={1}>
        <TextField
          select
          label="Tipo de dirección"
          value={form.tipo_direccion}
          onChange={(e) =>
            setForm((f) => ({ ...f, tipo_direccion: e.target.value as TipoDireccion }))
          }
          size="small"
          fullWidth
        >
          {TIPOS_DIRECCION.map((t) => (
            <MenuItem key={t.value} value={t.value}>
              {t.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label="Dirección completa"
          value={form.direccion_completa}
          onChange={(e) => setForm((f) => ({ ...f, direccion_completa: e.target.value }))}
          size="small"
          multiline
          minRows={2}
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <TextField
            label="Ciudad"
            value={form.ciudad}
            onChange={(e) => setForm((f) => ({ ...f, ciudad: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label="Estado/Provincia"
            value={form.estado_provincia}
            onChange={(e) => setForm((f) => ({ ...f, estado_provincia: e.target.value }))}
            size="small"
            fullWidth
          />
        </Stack>
        <FormControlLabel
          control={
            <Checkbox
              checked={form.es_direccion_principal}
              onChange={(e) =>
                setForm((f) => ({ ...f, es_direccion_principal: e.target.checked }))
              }
            />
          }
          label="Dirección principal"
        />
        <Stack direction="row" spacing={1}>
          <Button
            variant="contained"
            size="small"
            onClick={handleGuardar}
            disabled={guardar.isPending}
          >
            {editId ? 'Actualizar dirección' : 'Agregar dirección'}
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

export default ClientesPage;
