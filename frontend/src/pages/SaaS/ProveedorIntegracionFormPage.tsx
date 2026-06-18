import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Card, Checkbox, FormControlLabel, FormGroup,
  MenuItem, Stack, Switch, TextField, Typography,
} from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  getProveedor, createProveedor, updateProveedor,
  type ConectorProveedorPayload, type ProveedorEstado,
} from '../../services/integrationHubService';

const ESTADOS: ProveedorEstado[] = ['activo', 'beta', 'proximamente'];

// Entidades sincronizables conocidas (espejo de EntidadSincronizada.TIPO_CHOICES).
const CAPACIDADES_DISPONIBLES = [
  'contactos', 'productos', 'pedidos_venta', 'pedidos_compra',
  'facturas_venta', 'pagos', 'inventario',
];

const EMPTY: ConectorProveedorPayload = {
  codigo: '',
  nombre: '',
  descripcion: '',
  icono_url: '',
  capacidades: [],
  versiones_soportadas: [],
  requiere_url: true,
  requiere_db: false,
  estado: 'activo',
  activo: true,
  orden: 100,
};

const CODIGO_RE = /^[a-z0-9_]+$/;

const ProveedorIntegracionFormPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id_proveedor } = useParams<{ id_proveedor: string }>();
  const isEdit = Boolean(id_proveedor);

  const [form, setForm] = useState<ConectorProveedorPayload>(EMPTY);
  const [versionesText, setVersionesText] = useState('');
  const [error, setError] = useState('');

  const { data: existing, isLoading: loading } = useQuery({
    queryKey: ['integration-hub/proveedores-admin', 'detail', id_proveedor],
    queryFn: () => getProveedor(id_proveedor as string),
    enabled: isEdit,
  });

  useEffect(() => {
    if (existing) {
      setForm({
        codigo: existing.codigo,
        nombre: existing.nombre,
        descripcion: existing.descripcion,
        icono_url: existing.icono_url,
        capacidades: existing.capacidades,
        versiones_soportadas: existing.versiones_soportadas,
        requiere_url: existing.requiere_url ?? true,
        requiere_db: existing.requiere_db ?? false,
        estado: existing.estado,
        activo: existing.activo ?? true,
        orden: existing.orden ?? 100,
      });
      setVersionesText((existing.versiones_soportadas ?? []).join(', '));
    }
  }, [existing]);

  const mutation = useMutation({
    mutationFn: (data: ConectorProveedorPayload) =>
      isEdit ? updateProveedor(id_proveedor as string, data) : createProveedor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-hub/proveedores-admin'] });
      queryClient.invalidateQueries({ queryKey: ['/integration-hub/proveedores/'] });
      navigate('/admin-saas/proveedores');
    },
    onError: (e: Error) => setError(e.message || 'No se pudo guardar el proveedor.'),
  });

  const set = <K extends keyof ConectorProveedorPayload>(key: K, value: ConectorProveedorPayload[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const toggleCapacidad = (cap: string) =>
    setForm((f) => ({
      ...f,
      capacidades: f.capacidades.includes(cap)
        ? f.capacidades.filter((c) => c !== cap)
        : [...f.capacidades, cap],
    }));

  const validate = (): string | null => {
    const codigo = form.codigo.trim().toLowerCase();
    if (!codigo) return 'El código es obligatorio.';
    if (!CODIGO_RE.test(codigo)) {
      return "El código solo admite minúsculas, números y guion bajo (ej: 'odoo', 'google_sheets').";
    }
    if (!form.nombre.trim()) return 'El nombre es obligatorio.';
    return null;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setError('');
    const versiones = versionesText
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean);
    mutation.mutate({
      ...form,
      codigo: form.codigo.trim().toLowerCase(),
      versiones_soportadas: versiones,
    });
  };

  if (isEdit && loading) {
    return (
      <PageContainer>
        <PageHeader title="Editar proveedor" />
        <Box>Cargando…</Box>
      </PageContainer>
    );
  }

  return (
    <PageContainer maxWidth={760}>
      <PageHeader title={isEdit ? 'Editar proveedor' : 'Nuevo proveedor'} />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Card sx={{ p: 3 }}>
        <Box component="form" onSubmit={handleSubmit}>
          <Stack spacing={2}>
            <TextField
              label="Código del conector"
              value={form.codigo}
              onChange={(e) => set('codigo', e.target.value)}
              required
              fullWidth
              disabled={isEdit}
              helperText={
                isEdit
                  ? 'El código no se edita: identifica al conector en el backend.'
                  : "Debe coincidir con un conector implementado (ej: 'odoo', 'google_sheets')."
              }
            />
            <TextField
              label="Nombre"
              value={form.nombre}
              onChange={(e) => set('nombre', e.target.value)}
              required
              fullWidth
            />
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => set('descripcion', e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
            <TextField
              label="URL del ícono (opcional)"
              value={form.icono_url}
              onChange={(e) => set('icono_url', e.target.value)}
              fullWidth
            />

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                select
                label="Estado"
                value={form.estado}
                onChange={(e) => set('estado', e.target.value as ProveedorEstado)}
                fullWidth
              >
                {ESTADOS.map((s) => (
                  <MenuItem key={s} value={s}>{s}</MenuItem>
                ))}
              </TextField>
              <TextField
                label="Orden"
                type="number"
                value={form.orden}
                onChange={(e) => set('orden', Number(e.target.value))}
                inputProps={{ min: 0 }}
                fullWidth
              />
            </Stack>

            <TextField
              label="Versiones soportadas (separadas por coma)"
              value={versionesText}
              onChange={(e) => setVersionesText(e.target.value)}
              placeholder="8, 9, 10, 11"
              fullWidth
            />

            <Box>
              <Typography variant="body2" fontWeight={600} mb={0.5}>
                Entidades soportadas
              </Typography>
              <FormGroup row>
                {CAPACIDADES_DISPONIBLES.map((cap) => (
                  <FormControlLabel
                    key={cap}
                    control={
                      <Checkbox
                        checked={form.capacidades.includes(cap)}
                        onChange={() => toggleCapacidad(cap)}
                      />
                    }
                    label={cap}
                  />
                ))}
              </FormGroup>
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1 }}>
              <FormControlLabel
                control={<Switch checked={!!form.requiere_url} onChange={(e) => set('requiere_url', e.target.checked)} />}
                label="Requiere URL del servidor"
              />
              <FormControlLabel
                control={<Switch checked={!!form.requiere_db} onChange={(e) => set('requiere_db', e.target.checked)} />}
                label="Requiere nombre de base de datos"
              />
              <FormControlLabel
                control={<Switch checked={!!form.activo} onChange={(e) => set('activo', e.target.checked)} />}
                label="Activo"
              />
            </Box>

            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button onClick={() => navigate('/admin-saas/proveedores')}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={mutation.isPending}>
                {mutation.isPending ? 'Guardando…' : 'Guardar'}
              </Button>
            </Stack>
          </Stack>
        </Box>
      </Card>
    </PageContainer>
  );
};

export default ProveedorIntegracionFormPage;
