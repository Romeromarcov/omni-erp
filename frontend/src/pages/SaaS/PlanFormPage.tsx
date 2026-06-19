import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert, Box, Button, Card, FormControlLabel, MenuItem, Stack, Switch, TextField,
} from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  fetchPlan, createPlan, updatePlan,
  PLAN_NIVELES, PLAN_SOPORTES,
  type PlanPayload,
} from '../../services/saasService';
import { planSchema, type PlanInput } from '../../schemas/saas.schemas';

const DEFAULTS: PlanInput = {
  nombre: '',
  nivel: 'STARTER',
  descripcion: '',
  precio_mensual: '0',
  precio_anual: '0',
  max_usuarios: 5,
  max_empresas: 1,
  max_documentos_mes: 100,
  permite_ia: false,
  permite_api: false,
  permite_reportes_avanzados: false,
  permite_multimoneda: false,
  soporte: 'email',
  activo: true,
};

const PlanFormPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id_plan } = useParams<{ id_plan: string }>();
  const isEdit = Boolean(id_plan);

  const {
    control, handleSubmit, reset, setError: setFormError,
    formState: { errors, isSubmitting },
  } = useForm<PlanInput>({
    resolver: zodResolver(planSchema),
    mode: 'onBlur',
    defaultValues: DEFAULTS,
  });

  const { data: existing, isLoading: loadingPlan } = useQuery({
    queryKey: ['saas/planes', 'detail', id_plan],
    queryFn: () => fetchPlan(id_plan as string),
    enabled: isEdit,
  });

  useEffect(() => {
    if (existing) {
      reset({
        nombre: existing.nombre,
        nivel: existing.nivel,
        descripcion: existing.descripcion ?? '',
        precio_mensual: existing.precio_mensual,
        precio_anual: existing.precio_anual,
        max_usuarios: existing.max_usuarios,
        max_empresas: existing.max_empresas,
        max_documentos_mes: existing.max_documentos_mes,
        permite_ia: existing.permite_ia,
        permite_api: existing.permite_api,
        permite_reportes_avanzados: existing.permite_reportes_avanzados,
        permite_multimoneda: existing.permite_multimoneda,
        soporte: existing.soporte,
        activo: existing.activo,
      });
    }
  }, [existing, reset]);

  const mutation = useMutation({
    mutationFn: (data: PlanPayload) =>
      isEdit ? updatePlan(id_plan as string, data) : createPlan(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saas/planes'] });
      navigate('/admin-saas/planes');
    },
    onError: (e: Error) =>
      setFormError('root', { message: e.message || 'No se pudo guardar el plan.' }),
  });

  const onSubmit = (data: PlanInput) => {
    mutation.mutate({ ...data, descripcion: data.descripcion ?? '' });
  };

  if (isEdit && loadingPlan) {
    return (
      <PageContainer>
        <PageHeader title="Editar plan" />
        <Box>Cargando…</Box>
      </PageContainer>
    );
  }

  return (
    <PageContainer maxWidth={760}>
      <PageHeader title={isEdit ? 'Editar plan' : 'Nuevo plan'} />

      {errors.root?.message && (
        <Alert severity="error" sx={{ mb: 2 }}>{errors.root.message}</Alert>
      )}

      <Card sx={{ p: 3 }}>
        <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
          <Stack spacing={2}>
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
              name="nivel"
              control={control}
              render={({ field }) => (
                <TextField {...field} select label="Nivel" fullWidth>
                  {PLAN_NIVELES.map((n) => (
                    <MenuItem key={n} value={n}>{n}</MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Controller
              name="descripcion"
              control={control}
              render={({ field }) => (
                <TextField {...field} label="Descripción" multiline minRows={2} fullWidth />
              )}
            />

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Controller
                name="precio_mensual"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    label="Precio mensual"
                    inputProps={{ inputMode: 'decimal' }}
                    fullWidth
                    error={!!errors.precio_mensual}
                    helperText={errors.precio_mensual?.message}
                  />
                )}
              />
              <Controller
                name="precio_anual"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    label="Precio anual"
                    inputProps={{ inputMode: 'decimal' }}
                    fullWidth
                    error={!!errors.precio_anual}
                    helperText={errors.precio_anual?.message}
                  />
                )}
              />
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Controller
                name="max_usuarios"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    label="Máx. usuarios (0 = ilimitado)"
                    type="number"
                    inputProps={{ min: 0 }}
                    fullWidth
                    error={!!errors.max_usuarios}
                    helperText={errors.max_usuarios?.message}
                  />
                )}
              />
              <Controller
                name="max_empresas"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    label="Máx. empresas (0 = ilimitado)"
                    type="number"
                    inputProps={{ min: 0 }}
                    fullWidth
                    error={!!errors.max_empresas}
                    helperText={errors.max_empresas?.message}
                  />
                )}
              />
              <Controller
                name="max_documentos_mes"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    label="Máx. docs/mes (0 = ilimitado)"
                    type="number"
                    inputProps={{ min: 0 }}
                    fullWidth
                    error={!!errors.max_documentos_mes}
                    helperText={errors.max_documentos_mes?.message}
                  />
                )}
              />
            </Stack>

            <Controller
              name="soporte"
              control={control}
              render={({ field }) => (
                <TextField {...field} select label="Soporte" fullWidth>
                  {PLAN_SOPORTES.map((s) => (
                    <MenuItem key={s} value={s}>{s}</MenuItem>
                  ))}
                </TextField>
              )}
            />

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1 }}>
              {([
                ['permite_ia', 'Permite IA / agentes'],
                ['permite_api', 'Permite API REST'],
                ['permite_reportes_avanzados', 'Reportes avanzados'],
                ['permite_multimoneda', 'Multimoneda'],
                ['activo', 'Activo'],
              ] as const).map(([name, label]) => (
                <Controller
                  key={name}
                  name={name}
                  control={control}
                  render={({ field }) => (
                    <FormControlLabel
                      control={
                        <Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />
                      }
                      label={label}
                    />
                  )}
                />
              ))}
            </Box>

            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button onClick={() => navigate('/admin-saas/planes')}>Cancelar</Button>
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

export default PlanFormPage;
