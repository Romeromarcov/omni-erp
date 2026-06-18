import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert, Box, Button, Card, Checkbox, FormControlLabel, FormGroup,
  MenuItem, Stack, Switch, TextField, Typography,
} from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  getProveedor, createProveedor, updateProveedor,
  type ConectorProveedorPayload,
} from '../../services/integrationHubService';
import {
  ESTADOS_PROVEEDOR, parseVersiones, proveedorIntegracionSchema,
  type ProveedorIntegracionInput,
} from '../../schemas/saas.schemas';

// Entidades sincronizables conocidas (espejo de EntidadSincronizada.TIPO_CHOICES).
const CAPACIDADES_DISPONIBLES = [
  'contactos', 'productos', 'pedidos_venta', 'pedidos_compra',
  'facturas_venta', 'pagos', 'inventario',
];

const DEFAULTS: ProveedorIntegracionInput = {
  codigo: '',
  nombre: '',
  descripcion: '',
  icono_url: '',
  estado: 'activo',
  orden: 100,
  capacidades: [],
  versionesText: '',
  requiere_url: true,
  requiere_db: false,
  activo: true,
};

const ProveedorIntegracionFormPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id_proveedor } = useParams<{ id_proveedor: string }>();
  const isEdit = Boolean(id_proveedor);

  const {
    control, handleSubmit, reset, setError: setFormError,
    formState: { errors, isSubmitting },
  } = useForm<ProveedorIntegracionInput>({
    resolver: zodResolver(proveedorIntegracionSchema),
    mode: 'onBlur',
    defaultValues: DEFAULTS,
  });

  const { data: existing, isLoading: loading } = useQuery({
    queryKey: ['integration-hub/proveedores-admin', 'detail', id_proveedor],
    queryFn: () => getProveedor(id_proveedor as string),
    enabled: isEdit,
  });

  useEffect(() => {
    if (existing) {
      reset({
        codigo: existing.codigo,
        nombre: existing.nombre,
        descripcion: existing.descripcion ?? '',
        icono_url: existing.icono_url ?? '',
        estado: existing.estado,
        orden: existing.orden ?? 100,
        capacidades: existing.capacidades ?? [],
        versionesText: (existing.versiones_soportadas ?? []).join(', '),
        requiere_url: existing.requiere_url ?? true,
        requiere_db: existing.requiere_db ?? false,
        activo: existing.activo ?? true,
      });
    }
  }, [existing, reset]);

  const mutation = useMutation({
    mutationFn: (data: ConectorProveedorPayload) =>
      isEdit ? updateProveedor(id_proveedor as string, data) : createProveedor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-hub/proveedores-admin'] });
      queryClient.invalidateQueries({ queryKey: ['/integration-hub/proveedores/'] });
      navigate('/admin-saas/proveedores');
    },
    onError: (e: Error) =>
      setFormError('root', { message: e.message || 'No se pudo guardar el proveedor.' }),
  });

  const onSubmit = (data: ProveedorIntegracionInput) => {
    mutation.mutate({
      codigo: data.codigo.trim().toLowerCase(),
      nombre: data.nombre.trim(),
      descripcion: data.descripcion ?? '',
      icono_url: data.icono_url ?? '',
      estado: data.estado,
      orden: data.orden,
      capacidades: data.capacidades,
      versiones_soportadas: parseVersiones(data.versionesText),
      requiere_url: data.requiere_url,
      requiere_db: data.requiere_db,
      activo: data.activo,
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

      {errors.root?.message && (
        <Alert severity="error" sx={{ mb: 2 }}>{errors.root.message}</Alert>
      )}

      <Card sx={{ p: 3 }}>
        <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
          <Stack spacing={2}>
            <Controller
              name="codigo"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label="Código del conector"
                  required
                  fullWidth
                  disabled={isEdit}
                  error={!!errors.codigo}
                  helperText={
                    errors.codigo?.message ??
                    (isEdit
                      ? 'El código no se edita: identifica al conector en el backend.'
                      : "Debe coincidir con un conector implementado (ej: 'odoo', 'google_sheets').")
                  }
                />
              )}
            />
            <Controller
              name="nombre"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label="Nombre"
                  required
                  fullWidth
                  error={!!errors.nombre}
                  helperText={errors.nombre?.message}
                />
              )}
            />
            <Controller
              name="descripcion"
              control={control}
              render={({ field }) => (
                <TextField {...field} label="Descripción" multiline minRows={2} fullWidth />
              )}
            />
            <Controller
              name="icono_url"
              control={control}
              render={({ field }) => (
                <TextField {...field} label="URL del ícono (opcional)" fullWidth />
              )}
            />

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Controller
                name="estado"
                control={control}
                render={({ field }) => (
                  <TextField {...field} select label="Estado" fullWidth>
                    {ESTADOS_PROVEEDOR.map((s) => (
                      <MenuItem key={s} value={s}>{s}</MenuItem>
                    ))}
                  </TextField>
                )}
              />
              <Controller
                name="orden"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    label="Orden"
                    type="number"
                    inputProps={{ min: 0 }}
                    fullWidth
                    error={!!errors.orden}
                    helperText={errors.orden?.message}
                  />
                )}
              />
            </Stack>

            <Controller
              name="versionesText"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label="Versiones soportadas (separadas por coma)"
                  placeholder="8, 9, 10, 11"
                  fullWidth
                />
              )}
            />

            <Box>
              <Typography variant="body2" fontWeight={600} mb={0.5}>
                Entidades soportadas
              </Typography>
              <Controller
                name="capacidades"
                control={control}
                render={({ field }) => (
                  <FormGroup row>
                    {CAPACIDADES_DISPONIBLES.map((cap) => (
                      <FormControlLabel
                        key={cap}
                        control={
                          <Checkbox
                            checked={field.value.includes(cap)}
                            onChange={() =>
                              field.onChange(
                                field.value.includes(cap)
                                  ? field.value.filter((c) => c !== cap)
                                  : [...field.value, cap],
                              )
                            }
                          />
                        }
                        label={cap}
                      />
                    ))}
                  </FormGroup>
                )}
              />
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1 }}>
              <Controller
                name="requiere_url"
                control={control}
                render={({ field }) => (
                  <FormControlLabel
                    control={<Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />}
                    label="Requiere URL del servidor"
                  />
                )}
              />
              <Controller
                name="requiere_db"
                control={control}
                render={({ field }) => (
                  <FormControlLabel
                    control={<Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />}
                    label="Requiere nombre de base de datos"
                  />
                )}
              />
              <Controller
                name="activo"
                control={control}
                render={({ field }) => (
                  <FormControlLabel
                    control={<Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />}
                    label="Activo"
                  />
                )}
              />
            </Box>

            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button onClick={() => navigate('/admin-saas/proveedores')}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={isSubmitting || mutation.isPending}>
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
