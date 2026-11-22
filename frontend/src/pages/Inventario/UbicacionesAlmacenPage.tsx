import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import SwapHorizOutlined from '@mui/icons-material/SwapHorizOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  ubicacionesAlmacenService,
  type UbicacionAlmacen,
  type UbicacionAlmacenPayload,
  type TipoUbicacion,
} from '../../services/gapsMenoresService';
import {
  almacenesService,
  stockUbicacionesService,
  type Almacen,
  type StockUbicacion,
  type StockUbicacionPayload,
  type TransferirUbicacionPayload,
  type ReservarUbicacionPayload,
} from '../../services/almacenesService';
import { productoInventarioService, type Producto } from '../../services/inventarioService';
import { gapsMenoresKeys, almacenesKeys } from '../../lib/queryKeys';
import { D, parseDecimalStrict } from '../../lib/decimal';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';

const TIPOS: { value: TipoUbicacion; label: string }[] = [
  { value: 'ESTANTERIA', label: 'Estantería' },
  { value: 'PISO', label: 'Piso' },
  { value: 'REFRIGERADO', label: 'Refrigerado' },
  { value: 'CONGELADO', label: 'Congelado' },
  { value: 'EXTERIOR', label: 'Exterior' },
  { value: 'CUARENTENA', label: 'Cuarentena' },
  { value: 'DEVOLUCION', label: 'Devolución' },
  { value: 'PICKING', label: 'Picking' },
  { value: 'RECEPCION', label: 'Recepción' },
  { value: 'DESPACHO', label: 'Despacho' },
];

interface FormState {
  id_almacen: string;
  codigo_ubicacion: string;
  nombre_ubicacion: string;
  tipo_ubicacion: TipoUbicacion;
  pasillo: string;
  estante: string;
  nivel: string;
  posicion: string;
  capacidad_maxima: string;
  unidad_capacidad: string;
  activo: boolean;
  requiere_autorizacion: boolean;
  observaciones: string;
}

const FORM_VACIO: FormState = {
  id_almacen: '',
  codigo_ubicacion: '',
  nombre_ubicacion: '',
  tipo_ubicacion: 'ESTANTERIA',
  pasillo: '',
  estante: '',
  nivel: '',
  posicion: '',
  capacidad_maxima: '',
  unidad_capacidad: '',
  activo: true,
  requiere_autorizacion: false,
  observaciones: '',
};

const UbicacionesAlmacenPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  const [filtroAlmacen, setFiltroAlmacen] = useState('');

  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });

  return (
    <PageContainer>
      <PageHeader
        title="Ubicaciones de Almacén"
        subtitle="Ubicaciones físicas dentro de cada almacén (estanterías, picking, refrigerado…) y stock por ubicación."
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Ubicaciones" />
        <Tab label="Stock por Ubicación" />
      </Tabs>

      {tab === 0 && (
        <UbicacionesCrudTab
          almacenes={almacenes}
          filtroAlmacen={filtroAlmacen}
          onChangeFiltroAlmacen={setFiltroAlmacen}
        />
      )}
      {tab === 1 && (
        <StockUbicacionesTab
          almacenes={almacenes}
          filtroAlmacen={filtroAlmacen}
          onChangeFiltroAlmacen={setFiltroAlmacen}
        />
      )}
    </PageContainer>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Tab 0: CRUD Ubicaciones
// ─────────────────────────────────────────────────────────────────────────────

interface UbicacionesCrudTabProps {
  almacenes: Almacen[];
  filtroAlmacen: string;
  onChangeFiltroAlmacen: (v: string) => void;
}

const UbicacionesCrudTab: React.FC<UbicacionesCrudTabProps> = ({
  almacenes,
  filtroAlmacen,
  onChangeFiltroAlmacen,
}) => {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<UbicacionAlmacen | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: ubicaciones = [], isLoading } = useQuery({
    queryKey: gapsMenoresKeys.ubicaciones(filtroAlmacen || null),
    queryFn: () =>
      ubicacionesAlmacenService.getAll(filtroAlmacen ? { almacen: filtroAlmacen } : undefined),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: gapsMenoresKeys.ubicacionesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...FORM_VACIO, id_almacen: filtroAlmacen });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (u: UbicacionAlmacen) => {
    setEditando(u);
    setForm({
      id_almacen: u.id_almacen,
      codigo_ubicacion: u.codigo_ubicacion,
      nombre_ubicacion: u.nombre_ubicacion,
      tipo_ubicacion: u.tipo_ubicacion,
      pasillo: u.pasillo ?? '',
      estante: u.estante ?? '',
      nivel: u.nivel ?? '',
      posicion: u.posicion ?? '',
      capacidad_maxima: u.capacidad_maxima ?? '',
      unidad_capacidad: u.unidad_capacidad ?? '',
      activo: u.activo,
      requiere_autorizacion: u.requiere_autorizacion,
      observaciones: u.observaciones ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: UbicacionAlmacenPayload) =>
      editando
        ? ubicacionesAlmacenService.update(editando.id_ubicacion, payload)
        : ubicacionesAlmacenService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la ubicación.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => ubicacionesAlmacenService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la ubicación.')),
  });

  const handleGuardar = () => {
    if (!form.id_almacen || !form.codigo_ubicacion.trim() || !form.nombre_ubicacion.trim()) {
      setErrorMsg('Complete almacén, código y nombre de la ubicación.');
      return;
    }
    const payload: UbicacionAlmacenPayload = {
      id_empresa: getEmpresaId() || '',
      id_almacen: form.id_almacen,
      codigo_ubicacion: form.codigo_ubicacion.trim(),
      nombre_ubicacion: form.nombre_ubicacion.trim(),
      tipo_ubicacion: form.tipo_ubicacion,
      pasillo: form.pasillo.trim() || null,
      estante: form.estante.trim() || null,
      nivel: form.nivel.trim() || null,
      posicion: form.posicion.trim() || null,
      capacidad_maxima: form.capacidad_maxima.trim() || null,
      unidad_capacidad: form.unidad_capacidad.trim() || null,
      activo: form.activo,
      requiere_autorizacion: form.requiere_autorizacion,
      observaciones: form.observaciones.trim() || null,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (u: UbicacionAlmacen) => {
    if (window.confirm(`¿Eliminar la ubicación "${u.nombre_ubicacion}"?`)) {
      eliminar.mutate(u.id_ubicacion);
    }
  };

  const nombreAlmacen = (id: string) =>
    almacenes.find((a: Almacen) => a.id_almacen === id)?.nombre_almacen ?? id;

  const columns: Column<UbicacionAlmacen>[] = [
    { key: 'codigo_ubicacion', header: 'Código', render: (u) => u.codigo_ubicacion },
    { key: 'nombre_ubicacion', header: 'Nombre', render: (u) => u.nombre_ubicacion },
    { key: 'id_almacen', header: 'Almacén', render: (u) => nombreAlmacen(u.id_almacen) },
    {
      key: 'tipo_ubicacion',
      header: 'Tipo',
      render: (u) => TIPOS.find((t) => t.value === u.tipo_ubicacion)?.label ?? u.tipo_ubicacion,
    },
    {
      key: 'autorizacion',
      header: 'Autorización',
      render: (u) =>
        u.requiere_autorizacion ? <Chip label="Requiere autorización" size="small" color="warning" /> : '—',
    },
    { key: 'activo', header: 'Activa', render: (u) => <StatusChip value={u.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (u) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(u)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(u)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} flexWrap="wrap">
        <TextField
          select
          label="Almacén"
          value={filtroAlmacen}
          onChange={(e) => onChangeFiltroAlmacen(e.target.value)}
          size="small"
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {almacenes.map((a: Almacen) => (
            <MenuItem key={a.id_almacen} value={a.id_almacen}>
              {a.nombre_almacen}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva ubicación
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={ubicaciones}
        getRowKey={(u) => u.id_ubicacion}
        loading={isLoading}
        emptyMessage="Sin ubicaciones. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar ubicación' : 'Nueva ubicación'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Almacén"
              value={form.id_almacen}
              onChange={(e) => setForm((f) => ({ ...f, id_almacen: e.target.value }))}
              required
              fullWidth
            >
              {almacenes.map((a: Almacen) => (
                <MenuItem key={a.id_almacen} value={a.id_almacen}>
                  {a.nombre_almacen}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Código"
                value={form.codigo_ubicacion}
                onChange={(e) => setForm((f) => ({ ...f, codigo_ubicacion: e.target.value }))}
                required
                fullWidth
              />
              <TextField
                select
                label="Tipo"
                value={form.tipo_ubicacion}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tipo_ubicacion: e.target.value as TipoUbicacion }))
                }
                fullWidth
              >
                {TIPOS.map((t) => (
                  <MenuItem key={t.value} value={t.value}>
                    {t.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              label="Nombre"
              value={form.nombre_ubicacion}
              onChange={(e) => setForm((f) => ({ ...f, nombre_ubicacion: e.target.value }))}
              required
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Pasillo"
                value={form.pasillo}
                onChange={(e) => setForm((f) => ({ ...f, pasillo: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Estante"
                value={form.estante}
                onChange={(e) => setForm((f) => ({ ...f, estante: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Nivel"
                value={form.nivel}
                onChange={(e) => setForm((f) => ({ ...f, nivel: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Posición"
                value={form.posicion}
                onChange={(e) => setForm((f) => ({ ...f, posicion: e.target.value }))}
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Capacidad máxima"
                value={form.capacidad_maxima}
                onChange={(e) => setForm((f) => ({ ...f, capacidad_maxima: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
              <TextField
                label="Unidad capacidad"
                value={form.unidad_capacidad}
                onChange={(e) => setForm((f) => ({ ...f, unidad_capacidad: e.target.value }))}
                helperText="KG, M3, UNIDADES…"
                fullWidth
              />
            </Stack>
            <TextField
              label="Observaciones"
              value={form.observaciones}
              onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
              multiline
              minRows={2}
              fullWidth
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.requiere_autorizacion}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, requiere_autorizacion: e.target.checked }))
                  }
                />
              }
              label="Requiere autorización"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
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
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Tab 1: Stock por Ubicación + Transferencias + Reservas
// ─────────────────────────────────────────────────────────────────────────────

interface StockUbicacionesTabProps {
  almacenes: Almacen[];
  filtroAlmacen: string;
  onChangeFiltroAlmacen: (v: string) => void;
}

interface TransferirForm {
  id_almacen: string;
  id_ubicacion_origen: string;
  id_ubicacion_destino: string;
  id_producto: string;
  id_variante: string | null;
  cantidad: string;
  observaciones: string;
}

interface CargaForm {
  id_almacen: string;
  id_ubicacion: string;
  id_producto: string;
  cantidad_disponible: string;
}

interface ReservaForm {
  id_almacen: string;
  id_ubicacion: string;
  id_producto: string;
  id_variante: string | null;
  cantidad: string;
  liberar: boolean;
}

const StockUbicacionesTab: React.FC<StockUbicacionesTabProps> = ({
  almacenes,
  filtroAlmacen,
  onChangeFiltroAlmacen,
}) => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [errorMsg, setErrorMsg] = useState('');
  const [okMsg, setOkMsg] = useState('');

  const [transferirOpen, setTransferirOpen] = useState(false);
  const [transferirForm, setTransferirForm] = useState<TransferirForm>({
    id_almacen: filtroAlmacen,
    id_ubicacion_origen: '',
    id_ubicacion_destino: '',
    id_producto: '',
    id_variante: null,
    cantidad: '1',
    observaciones: '',
  });

  const [cargaOpen, setCargaOpen] = useState(false);
  const [cargaForm, setCargaForm] = useState<CargaForm>({
    id_almacen: filtroAlmacen,
    id_ubicacion: '',
    id_producto: '',
    cantidad_disponible: '0',
  });

  const [reservaOpen, setReservaOpen] = useState(false);
  const [reservaForm, setReservaForm] = useState<ReservaForm>({
    id_almacen: '',
    id_ubicacion: '',
    id_producto: '',
    id_variante: null,
    cantidad: '1',
    liberar: false,
  });

  const { data: stocks = [], isLoading } = useQuery({
    queryKey: almacenesKeys.stockUbicaciones(filtroAlmacen || null),
    queryFn: () => stockUbicacionesService.getAll(filtroAlmacen ? { almacen: filtroAlmacen } : undefined),
  });

  const { data: ubicaciones = [] } = useQuery({
    queryKey: gapsMenoresKeys.ubicaciones(null),
    queryFn: () => ubicacionesAlmacenService.getAll(),
  });

  const { data: productos = [] } = useQuery({
    queryKey: ['productos', empresaId],
    queryFn: () => productoInventarioService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: almacenesKeys.stockUbicacionesAll() });

  const almacenesConUbic = almacenes.filter((a) => Boolean(a.usa_ubicaciones));
  const almacenSeleccionado = almacenes.find((a) => a.id_almacen === filtroAlmacen);

  const crearStock = useMutation({
    mutationFn: (payload: StockUbicacionPayload) => stockUbicacionesService.create(payload),
    onSuccess: () => {
      setCargaOpen(false);
      setOkMsg('Stock inicial por ubicación registrado.');
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar el stock inicial.')),
  });

  const transferir = useMutation({
    mutationFn: (payload: TransferirUbicacionPayload) => stockUbicacionesService.transferir(payload),
    onSuccess: () => {
      setTransferirOpen(false);
      setOkMsg('Transferencia entre ubicaciones registrada correctamente.');
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo completar la transferencia.')),
  });

  const reservar = useMutation({
    mutationFn: (payload: ReservarUbicacionPayload) => stockUbicacionesService.reservar(payload),
    onSuccess: () => {
      setReservaOpen(false);
      setOkMsg('Reserva por ubicación actualizada.');
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo actualizar la reserva.')),
  });

  const abrirTransferir = (fila?: StockUbicacion) => {
    setErrorMsg('');
    setTransferirForm({
      id_almacen: fila?.id_almacen || filtroAlmacen || almacenesConUbic[0]?.id_almacen || '',
      id_ubicacion_origen: fila?.id_ubicacion || '',
      id_ubicacion_destino: '',
      id_producto: fila?.id_producto || '',
      id_variante: fila?.id_variante ?? null,
      cantidad: '1',
      observaciones: '',
    });
    setTransferirOpen(true);
  };

  const abrirCarga = () => {
    setErrorMsg('');
    setCargaForm({
      id_almacen: filtroAlmacen || (almacenesConUbic[0]?.id_almacen || ''),
      id_ubicacion: '',
      id_producto: '',
      cantidad_disponible: '0',
    });
    setCargaOpen(true);
  };

  const abrirReserva = (fila: StockUbicacion) => {
    setErrorMsg('');
    setReservaForm({
      id_almacen: fila.id_almacen,
      id_ubicacion: fila.id_ubicacion,
      id_producto: fila.id_producto,
      id_variante: fila.id_variante ?? null,
      cantidad: '1',
      liberar: false,
    });
    setReservaOpen(true);
  };

  const handleTransferir = () => {
    if (
      !transferirForm.id_almacen ||
      !transferirForm.id_ubicacion_origen ||
      !transferirForm.id_ubicacion_destino ||
      !transferirForm.id_producto
    ) {
      setErrorMsg('Complete almacén, ubicaciones origen/destino y producto.');
      return;
    }
    if (transferirForm.id_ubicacion_origen === transferirForm.id_ubicacion_destino) {
      setErrorMsg('La ubicación origen y destino deben ser distintas.');
      return;
    }
    const cantidadDec = parseDecimalStrict(transferirForm.cantidad);
    if (!cantidadDec || cantidadDec.lte(0)) {
      setErrorMsg('Ingrese una cantidad numérica válida mayor a cero.');
      return;
    }
    transferir.mutate({
      id_almacen: transferirForm.id_almacen,
      id_ubicacion_origen: transferirForm.id_ubicacion_origen,
      id_ubicacion_destino: transferirForm.id_ubicacion_destino,
      id_producto: transferirForm.id_producto,
      ...(transferirForm.id_variante ? { id_variante: transferirForm.id_variante } : {}),
      cantidad: transferirForm.cantidad.trim(),
      observaciones: transferirForm.observaciones.trim(),
    });
  };

  const handleCarga = () => {
    if (!cargaForm.id_almacen || !cargaForm.id_ubicacion || !cargaForm.id_producto) {
      setErrorMsg('Complete almacén, ubicación y producto.');
      return;
    }
    const dispDec = parseDecimalStrict(cargaForm.cantidad_disponible);
    if (!dispDec || dispDec.lt(0)) {
      setErrorMsg('Ingrese una cantidad disponible numérica mayor o igual a cero.');
      return;
    }
    crearStock.mutate({
      id_almacen: cargaForm.id_almacen,
      id_ubicacion: cargaForm.id_ubicacion,
      id_producto: cargaForm.id_producto,
      cantidad_disponible: cargaForm.cantidad_disponible.trim(),
    });
  };

  const handleReserva = () => {
    const cantDec = parseDecimalStrict(reservaForm.cantidad);
    if (!cantDec || cantDec.lte(0)) {
      setErrorMsg('Ingrese una cantidad numérica válida mayor a cero.');
      return;
    }
    reservar.mutate({
      id_almacen: reservaForm.id_almacen,
      id_ubicacion: reservaForm.id_ubicacion,
      id_producto: reservaForm.id_producto,
      ...(reservaForm.id_variante ? { id_variante: reservaForm.id_variante } : {}),
      cantidad: reservaForm.cantidad.trim(),
      liberar: reservaForm.liberar,
    });
  };

  const ubicacionesTransferir = ubicaciones.filter((u) => u.id_almacen === transferirForm.id_almacen);
  const ubicacionesCarga = ubicaciones.filter((u) => u.id_almacen === cargaForm.id_almacen);
  const ubOrigenObj = ubicaciones.find((u) => u.id_ubicacion === transferirForm.id_ubicacion_origen);
  const ubDestinoObj = ubicaciones.find((u) => u.id_ubicacion === transferirForm.id_ubicacion_destino);
  const requiereAutorizacionTransfer = Boolean(
    ubOrigenObj?.requiere_autorizacion || ubDestinoObj?.requiere_autorizacion,
  );

  const columns: Column<StockUbicacion>[] = [
    { key: 'almacen', header: 'Almacén', render: (s) => s.almacen_nombre ?? s.id_almacen },
    {
      key: 'ubicacion',
      header: 'Ubicación',
      render: (s) => (
        <Stack direction="row" spacing={1} alignItems="center">
          <span>
            {s.ubicacion_codigo ? `${s.ubicacion_codigo} · ${s.ubicacion_nombre ?? ''}` : s.id_ubicacion}
          </span>
          {s.requiere_autorizacion && <Chip label="Autorización" size="small" color="warning" />}
        </Stack>
      ),
    },
    {
      key: 'producto',
      header: 'Producto',
      render: (s) => {
        if (s.producto_nombre) return s.producto_sku ? `${s.producto_nombre} (${s.producto_sku})` : s.producto_nombre;
        return productos.find((p: Producto) => p.id_producto === s.id_producto)?.nombre_producto ?? s.id_producto;
      },
    },
    { key: 'disponible', header: 'Disponible', align: 'right', render: (s) => s.cantidad_disponible },
    { key: 'reservada', header: 'Reservada', align: 'right', render: (s) => s.cantidad_reservada },
    {
      key: 'libre',
      header: 'Libre',
      align: 'right',
      render: (s) => s.cantidad_libre ?? D(s.cantidad_disponible).minus(D(s.cantidad_reservada)).toFixed(4),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (s) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" startIcon={<SwapHorizOutlined />} onClick={() => abrirTransferir(s)}>
            Transferir
          </Button>
          <Button size="small" onClick={() => abrirReserva(s)}>
            Reservar / Liberar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} flexWrap="wrap">
        <TextField
          select
          label="Almacén"
          value={filtroAlmacen}
          onChange={(e) => onChangeFiltroAlmacen(e.target.value)}
          size="small"
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {almacenes.map((a: Almacen) => (
            <MenuItem key={a.id_almacen} value={a.id_almacen}>
              {a.nombre_almacen} {a.usa_ubicaciones ? '' : '(Simple)'}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<AddOutlined />} onClick={abrirCarga}>
            Carga inicial
          </Button>
          <Button variant="contained" startIcon={<SwapHorizOutlined />} onClick={() => abrirTransferir()}>
            Transferir entre ubicaciones
          </Button>
        </Stack>
      </Stack>

      {almacenSeleccionado && !almacenSeleccionado.usa_ubicaciones && (
        <Alert severity="info">
          El almacén <strong>{almacenSeleccionado.nombre_almacen}</strong> no tiene activado{' '}
          <code>usa_ubicaciones</code>. Actívalo en Almacenes para operar stock por ubicación.
        </Alert>
      )}
      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      {okMsg && (
        <Alert severity="success" onClose={() => setOkMsg('')}>
          {okMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={stocks}
        getRowKey={(s) => s.id_stock_ubicacion}
        loading={isLoading}
        emptyMessage="Sin stock registrado por ubicación."
      />

      {/* Dialog Transferir */}
      <Dialog open={transferirOpen} onClose={() => setTransferirOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Transferir entre ubicaciones</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {requiereAutorizacionTransfer && (
              <Alert severity="warning">
                Atención: una de las ubicaciones seleccionadas requiere autorización de supervisor (usuario staff de la
                empresa o superusuario).
              </Alert>
            )}
            <TextField
              select
              label="Almacén (con ubicaciones)"
              value={transferirForm.id_almacen}
              onChange={(e) =>
                setTransferirForm((f) => ({
                  ...f,
                  id_almacen: e.target.value,
                  id_ubicacion_origen: '',
                  id_ubicacion_destino: '',
                  id_variante: null,
                }))
              }
              fullWidth
            >
              {almacenesConUbic.map((a) => (
                <MenuItem key={a.id_almacen} value={a.id_almacen}>
                  {a.nombre_almacen}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                select
                label="Ubicación origen"
                value={transferirForm.id_ubicacion_origen}
                onChange={(e) => setTransferirForm((f) => ({ ...f, id_ubicacion_origen: e.target.value }))}
                fullWidth
              >
                {ubicacionesTransferir.map((u) => (
                  <MenuItem key={u.id_ubicacion} value={u.id_ubicacion}>
                    {u.codigo_ubicacion} — {u.nombre_ubicacion}
                    {u.requiere_autorizacion ? ' (Requiere autorización)' : ''}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Ubicación destino"
                value={transferirForm.id_ubicacion_destino}
                onChange={(e) => setTransferirForm((f) => ({ ...f, id_ubicacion_destino: e.target.value }))}
                fullWidth
              >
                {ubicacionesTransferir.map((u) => (
                  <MenuItem key={u.id_ubicacion} value={u.id_ubicacion}>
                    {u.codigo_ubicacion} — {u.nombre_ubicacion}
                    {u.requiere_autorizacion ? ' (Requiere autorización)' : ''}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              select
              label="Producto"
              value={transferirForm.id_producto}
              onChange={(e) => setTransferirForm((f) => ({ ...f, id_producto: e.target.value, id_variante: null }))}
              fullWidth
            >
              {productos.map((p) => (
                <MenuItem key={p.id_producto} value={p.id_producto}>
                  {p.nombre_producto}
                  {p.sku ? ` (${p.sku})` : ''}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Cantidad"
              value={transferirForm.cantidad}
              onChange={(e) => setTransferirForm((f) => ({ ...f, cantidad: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
            <TextField
              label="Observaciones"
              value={transferirForm.observaciones}
              onChange={(e) => setTransferirForm((f) => ({ ...f, observaciones: e.target.value }))}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTransferirOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleTransferir} disabled={transferir.isPending}>
            Confirmar transferencia
          </Button>
        </DialogActions>
      </Dialog>

      {/* Dialog Carga Inicial */}
      <Dialog open={cargaOpen} onClose={() => setCargaOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Carga inicial de stock por ubicación</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Almacén"
              value={cargaForm.id_almacen}
              onChange={(e) => setCargaForm((f) => ({ ...f, id_almacen: e.target.value, id_ubicacion: '' }))}
              fullWidth
            >
              {almacenesConUbic.map((a) => (
                <MenuItem key={a.id_almacen} value={a.id_almacen}>
                  {a.nombre_almacen}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Ubicación"
              value={cargaForm.id_ubicacion}
              onChange={(e) => setCargaForm((f) => ({ ...f, id_ubicacion: e.target.value }))}
              fullWidth
            >
              {ubicacionesCarga.map((u) => (
                <MenuItem key={u.id_ubicacion} value={u.id_ubicacion}>
                  {u.codigo_ubicacion} — {u.nombre_ubicacion}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Producto"
              value={cargaForm.id_producto}
              onChange={(e) => setCargaForm((f) => ({ ...f, id_producto: e.target.value }))}
              fullWidth
            >
              {productos.map((p) => (
                <MenuItem key={p.id_producto} value={p.id_producto}>
                  {p.nombre_producto}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Cantidad disponible"
              value={cargaForm.cantidad_disponible}
              onChange={(e) => setCargaForm((f) => ({ ...f, cantidad_disponible: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCargaOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleCarga} disabled={crearStock.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Dialog Reservar / Liberar */}
      <Dialog open={reservaOpen} onClose={() => setReservaOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Reservar o liberar stock en ubicación</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Operación"
              value={reservaForm.liberar ? 'liberar' : 'reservar'}
              onChange={(e) => setReservaForm((f) => ({ ...f, liberar: e.target.value === 'liberar' }))}
              fullWidth
            >
              <MenuItem value="reservar">Reservar</MenuItem>
              <MenuItem value="liberar">Liberar reserva</MenuItem>
            </TextField>
            <TextField
              label="Cantidad"
              value={reservaForm.cantidad}
              onChange={(e) => setReservaForm((f) => ({ ...f, cantidad: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReservaOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleReserva} disabled={reservar.isPending}>
            Aplicar
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
};

export default UbicacionesAlmacenPage;
