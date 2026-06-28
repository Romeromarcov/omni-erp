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
  articulosConocimientoService,
  categoriasTicketService,
  type BaseConocimientoArticulo,
  type BaseConocimientoArticuloPayload,
  type VisibilidadArticulo,
  type CategoriaTicket,
} from '../../services/servicioClienteService';
import { servicioClienteKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const VISIBILIDAD_LABEL: Record<VisibilidadArticulo, string> = {
  INTERNA: 'Interna',
  PUBLICA: 'Pública',
};

const VISIBILIDAD_COLOR: Record<string, 'default' | 'success'> = {
  interna: 'default',
  pública: 'success',
};

interface FormState {
  titulo: string;
  contenido: string;
  id_categoria_ticket: string;
  palabras_clave: string;
  visibilidad: VisibilidadArticulo;
  activo: boolean;
}

const FORM_VACIO: FormState = {
  titulo: '',
  contenido: '',
  id_categoria_ticket: '',
  palabras_clave: '',
  visibilidad: 'INTERNA',
  activo: true,
};

const BaseConocimientoPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroVisibilidad, setFiltroVisibilidad] = useState<VisibilidadArticulo | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<BaseConocimientoArticulo | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: articulos = [], isLoading } = useQuery({
    queryKey: servicioClienteKeys.articulos(empresaId, filtroVisibilidad),
    queryFn: () =>
      articulosConocimientoService.getAll({
        empresa: empresaId || undefined,
        visibilidad: filtroVisibilidad || undefined,
      }),
  });

  const { data: categorias = [] } = useQuery<CategoriaTicket[]>({
    queryKey: servicioClienteKeys.categoriasActivas(),
    queryFn: () => categoriasTicketService.activas(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: servicioClienteKeys.articulosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (a: BaseConocimientoArticulo) => {
    setEditando(a);
    setForm({
      titulo: a.titulo,
      contenido: a.contenido,
      id_categoria_ticket: a.id_categoria_ticket ?? '',
      palabras_clave: a.palabras_clave ?? '',
      visibilidad: a.visibilidad,
      activo: a.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: BaseConocimientoArticuloPayload) =>
      editando
        ? articulosConocimientoService.update(editando.id_articulo, payload)
        : articulosConocimientoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el artículo.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => articulosConocimientoService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el artículo.')),
  });

  const handleGuardar = () => {
    if (!form.titulo.trim() || !form.contenido.trim()) {
      setErrorMsg('Indique el título y el contenido.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      titulo: form.titulo.trim(),
      contenido: form.contenido.trim(),
      id_categoria_ticket: form.id_categoria_ticket || null,
      palabras_clave: form.palabras_clave.trim() || null,
      visibilidad: form.visibilidad,
      activo: form.activo,
    });
  };

  const handleEliminar = (a: BaseConocimientoArticulo) => {
    if (window.confirm(`¿Eliminar el artículo "${a.titulo}"?`)) {
      eliminar.mutate(a.id_articulo);
    }
  };

  const nombreCategoria = (id?: string | null) => {
    if (!id) return '—';
    return categorias.find((c) => c.id_categoria_ticket === id)?.nombre_categoria ?? id;
  };

  const columns: Column<BaseConocimientoArticulo>[] = [
    { key: 'titulo', header: 'Título', render: (a) => a.titulo },
    {
      key: 'id_categoria_ticket',
      header: 'Categoría',
      render: (a) => nombreCategoria(a.id_categoria_ticket),
    },
    {
      key: 'visibilidad',
      header: 'Visibilidad',
      render: (a) => (
        <StatusChip
          value={a.visibilidad}
          label={VISIBILIDAD_LABEL[a.visibilidad]}
          colorMap={VISIBILIDAD_COLOR}
        />
      ),
    },
    { key: 'activo', header: 'Activo', render: (a) => <StatusChip value={a.activo ?? true} /> },
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
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(a)}
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
        title="Base de conocimiento"
        subtitle="Artículos de ayuda internos y públicos para la mesa de soporte."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo artículo
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
        label="Visibilidad"
        value={filtroVisibilidad}
        onChange={(e) => setFiltroVisibilidad(e.target.value as VisibilidadArticulo | '')}
        size="small"
        sx={{ mb: 2, minWidth: 220 }}
      >
        <MenuItem value="">Todas</MenuItem>
        <MenuItem value="INTERNA">Interna</MenuItem>
        <MenuItem value="PUBLICA">Pública</MenuItem>
      </TextField>

      <DataTable
        columns={columns}
        rows={articulos}
        getRowKey={(a) => a.id_articulo}
        loading={isLoading}
        emptyMessage="Sin artículos. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar artículo' : 'Nuevo artículo'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Título"
              value={form.titulo}
              onChange={(e) => setForm((f) => ({ ...f, titulo: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Contenido"
              value={form.contenido}
              onChange={(e) => setForm((f) => ({ ...f, contenido: e.target.value }))}
              required
              multiline
              minRows={4}
              fullWidth
            />
            <TextField
              select
              label="Categoría"
              value={form.id_categoria_ticket}
              onChange={(e) => setForm((f) => ({ ...f, id_categoria_ticket: e.target.value }))}
              fullWidth
            >
              <MenuItem value="">— Sin categoría —</MenuItem>
              {categorias.map((c) => (
                <MenuItem key={c.id_categoria_ticket} value={c.id_categoria_ticket}>
                  {c.nombre_categoria}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Palabras clave"
              value={form.palabras_clave}
              onChange={(e) => setForm((f) => ({ ...f, palabras_clave: e.target.value }))}
              helperText="Separadas por comas (opcional)."
              fullWidth
            />
            <TextField
              select
              label="Visibilidad"
              value={form.visibilidad}
              onChange={(e) => setForm((f) => ({ ...f, visibilidad: e.target.value as VisibilidadArticulo }))}
              fullWidth
            >
              <MenuItem value="INTERNA">Interna</MenuItem>
              <MenuItem value="PUBLICA">Pública</MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Activo"
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

export default BaseConocimientoPage;
