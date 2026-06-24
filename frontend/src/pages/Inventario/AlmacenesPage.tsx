import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import TuneOutlined from '@mui/icons-material/TuneOutlined';
import { PageContainer, PageHeader, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  almacenesService,
  type Almacen,
  type AlmacenPayload,
} from '../../services/almacenesService';
import { almacenesKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

interface FormState {
  nombre_almacen: string;
  codigo_almacen: string;
  direccion: string;
}

const FORM_VACIO: FormState = { nombre_almacen: '', codigo_almacen: '', direccion: '' };

const AlmacenesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<Almacen | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: almacenes = [], isLoading } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: almacenesKeys.all() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (a: Almacen) => {
    setEditando(a);
    setForm({
      nombre_almacen: a.nombre_almacen,
      codigo_almacen: a.codigo_almacen ?? '',
      direccion: a.direccion ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: AlmacenPayload) =>
      editando
        ? almacenesService.update(editando.id_almacen, payload)
        : almacenesService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el almacén.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => almacenesService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el almacén.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_almacen.trim() || !form.codigo_almacen.trim()) {
      setErrorMsg('Complete nombre y código del almacén.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      nombre_almacen: form.nombre_almacen.trim(),
      codigo_almacen: form.codigo_almacen.trim(),
      direccion: form.direccion.trim() || null,
    });
  };

  const columns: Column<Almacen>[] = [
    { key: 'nombre', header: 'Nombre', render: (a) => a.nombre_almacen },
    { key: 'codigo', header: 'Código', render: (a) => a.codigo_almacen },
    { key: 'direccion', header: 'Dirección', render: (a) => a.direccion || '—' },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (a) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(a)}>
            Editar
          </Button>
          <Button
            size="small"
            startIcon={<TuneOutlined />}
            component={RouterLink}
            to={`/inventario/pasos-operacion?almacen=${a.id_almacen}`}
          >
            Pasos
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => eliminar.mutate(a.id_almacen)}
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
        title="Almacenes"
        subtitle="Gestiona los almacenes y configura, por cada uno, los pasos de recepción y entrega."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo almacén
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
        rows={almacenes}
        getRowKey={(a) => a.id_almacen}
        loading={isLoading}
        emptyMessage="Sin almacenes. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar almacén' : 'Nuevo almacén'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre"
              value={form.nombre_almacen}
              onChange={(e) => setForm((f) => ({ ...f, nombre_almacen: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Código"
              value={form.codigo_almacen}
              onChange={(e) => setForm((f) => ({ ...f, codigo_almacen: e.target.value }))}
              required
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

export default AlmacenesPage;
