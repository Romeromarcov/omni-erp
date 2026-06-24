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
  Stack,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  categoriasTicketService,
  type CategoriaTicket,
  type CategoriaTicketPayload,
} from '../../services/servicioClienteService';
import { servicioClienteKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

interface FormState {
  nombre_categoria: string;
  descripcion: string;
  activo: boolean;
}

const FORM_VACIO: FormState = {
  nombre_categoria: '',
  descripcion: '',
  activo: true,
};

const CategoriasTicketPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CategoriaTicket | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: categorias = [], isLoading } = useQuery({
    queryKey: servicioClienteKeys.categorias(empresaId),
    queryFn: () => categoriasTicketService.getAll({ empresa: empresaId || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: servicioClienteKeys.categoriasAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CategoriaTicket) => {
    setEditando(c);
    setForm({
      nombre_categoria: c.nombre_categoria,
      descripcion: c.descripcion ?? '',
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CategoriaTicketPayload) =>
      editando
        ? categoriasTicketService.update(editando.id_categoria_ticket, payload)
        : categoriasTicketService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la categoría.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => categoriasTicketService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la categoría.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_categoria.trim()) {
      setErrorMsg('Indique el nombre de la categoría.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      nombre_categoria: form.nombre_categoria.trim(),
      descripcion: form.descripcion.trim() || null,
      activo: form.activo,
    });
  };

  const handleEliminar = (c: CategoriaTicket) => {
    if (window.confirm(`¿Eliminar la categoría "${c.nombre_categoria}"?`)) {
      eliminar.mutate(c.id_categoria_ticket);
    }
  };

  const columns: Column<CategoriaTicket>[] = [
    { key: 'nombre_categoria', header: 'Categoría', render: (c) => c.nombre_categoria },
    { key: 'descripcion', header: 'Descripción', render: (c) => c.descripcion || '—' },
    { key: 'activo', header: 'Activa', render: (c) => <StatusChip value={c.activo ?? true} /> },
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
        title="Categorías de ticket"
        subtitle="Catálogo de categorías para clasificar los tickets de soporte."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nueva categoría
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
        rows={categorias}
        getRowKey={(c) => c.id_categoria_ticket}
        loading={isLoading}
        emptyMessage="Sin categorías. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar categoría' : 'Nueva categoría'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre"
              value={form.nombre_categoria}
              onChange={(e) => setForm((f) => ({ ...f, nombre_categoria: e.target.value }))}
              required
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

export default CategoriasTicketPage;
