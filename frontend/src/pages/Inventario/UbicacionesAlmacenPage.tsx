import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  ubicacionesAlmacenService,
  type UbicacionAlmacen,
  type UbicacionAlmacenPayload,
  type TipoUbicacion,
} from '../../services/gapsMenoresService';
import { almacenesService, type Almacen } from '../../services/almacenesService';
import { gapsMenoresKeys, almacenesKeys } from '../../lib/queryKeys';
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
  const queryClient = useQueryClient();
  const [filtroAlmacen, setFiltroAlmacen] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<UbicacionAlmacen | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });

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
    <PageContainer>
      <PageHeader
        title="Ubicaciones de Almacén"
        subtitle="Ubicaciones físicas dentro de cada almacén (estanterías, picking, refrigerado…)."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nueva ubicación
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
        label="Almacén"
        value={filtroAlmacen}
        onChange={(e) => setFiltroAlmacen(e.target.value)}
        size="small"
        sx={{ mb: 2, minWidth: 260 }}
      >
        <MenuItem value="">Todos</MenuItem>
        {almacenes.map((a: Almacen) => (
          <MenuItem key={a.id_almacen} value={a.id_almacen}>
            {a.nombre_almacen}
          </MenuItem>
        ))}
      </TextField>

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
    </PageContainer>
  );
};

export default UbicacionesAlmacenPage;
