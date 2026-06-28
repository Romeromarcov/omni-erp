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
  categoriasGastoService,
  type CategoriaGasto,
  type CategoriaGastoPayload,
} from '../../services/gastosService';
import { contabilidadService, type CuentaContable } from '../../services/contabilidadService';
import { gastosKeys, contabilidadKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

interface FormState {
  nombre_categoria: string;
  descripcion: string;
  id_cuenta_contable: string;
  requiere_factura: boolean;
  activo: boolean;
}

const FORM_VACIO: FormState = {
  nombre_categoria: '',
  descripcion: '',
  id_cuenta_contable: '',
  requiere_factura: false,
  activo: true,
};

const CategoriasGastoPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CategoriaGasto | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: categorias = [], isLoading } = useQuery({
    queryKey: gastosKeys.categorias(empresaId),
    queryFn: () => categoriasGastoService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: cuentas = [] } = useQuery<CuentaContable[]>({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: contabilidadService.getPlanCuentas,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: gastosKeys.categoriasAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CategoriaGasto) => {
    setEditando(c);
    setForm({
      nombre_categoria: c.nombre_categoria,
      descripcion: c.descripcion ?? '',
      id_cuenta_contable: c.id_cuenta_contable ?? '',
      requiere_factura: c.requiere_factura ?? false,
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CategoriaGastoPayload) =>
      editando
        ? categoriasGastoService.update(editando.id_categoria_gasto, payload)
        : categoriasGastoService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la categoría.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => categoriasGastoService.remove(id),
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
      id_cuenta_contable: form.id_cuenta_contable || null,
      requiere_factura: form.requiere_factura,
      activo: form.activo,
    });
  };

  const handleEliminar = (c: CategoriaGasto) => {
    if (window.confirm(`¿Eliminar la categoría "${c.nombre_categoria}"?`)) {
      eliminar.mutate(c.id_categoria_gasto);
    }
  };

  const nombreCuenta = (id?: string | null) => {
    if (!id) return '—';
    const cta = cuentas.find((c) => c.id_cuenta_contable === id);
    return cta ? `${cta.codigo_cuenta} — ${cta.nombre_cuenta}` : id;
  };

  const columns: Column<CategoriaGasto>[] = [
    { key: 'nombre_categoria', header: 'Categoría', render: (c) => c.nombre_categoria },
    { key: 'descripcion', header: 'Descripción', render: (c) => c.descripcion || '—' },
    {
      key: 'id_cuenta_contable',
      header: 'Cuenta contable',
      render: (c) => nombreCuenta(c.id_cuenta_contable),
    },
    {
      key: 'requiere_factura',
      header: 'Requiere factura',
      render: (c) => <StatusChip value={c.requiere_factura ?? false} />,
    },
    { key: 'activo', header: 'Activo', render: (c) => <StatusChip value={c.activo ?? true} /> },
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
        title="Categorías de gasto"
        subtitle="Catálogo de categorías de gasto y su cuenta contable de imputación."
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
        getRowKey={(c) => c.id_categoria_gasto}
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
            <TextField
              select
              label="Cuenta contable"
              value={form.id_cuenta_contable}
              onChange={(e) => setForm((f) => ({ ...f, id_cuenta_contable: e.target.value }))}
              helperText="Cuenta de gasto por defecto (opcional)."
              fullWidth
            >
              <MenuItem value="">— Sin cuenta —</MenuItem>
              {cuentas.map((c) => (
                <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                  {c.codigo_cuenta} — {c.nombre_cuenta}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.requiere_factura}
                  onChange={(e) => setForm((f) => ({ ...f, requiere_factura: e.target.checked }))}
                />
              }
              label="Requiere factura de respaldo"
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

export default CategoriasGastoPage;
