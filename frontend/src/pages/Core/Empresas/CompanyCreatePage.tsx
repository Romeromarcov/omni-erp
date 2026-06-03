import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { post, get } from '../../../services/api';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { finanzasKeys } from '../../../lib/queryKeys';
import { empresaSchema, type EmpresaInput } from '../../../schemas/core.schemas';
import { Alert, Box, Button, MenuItem, Stack, TextField } from '@mui/material';
import { PageHeader } from '../../../components/ui';

interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
}

type MonedaApiResponse = Moneda[] | { results: Moneda[] };

const defaultValues: EmpresaInput = {
  nombre_legal: '',
  nombre_comercial: '',
  identificador_fiscal: '',
  email_contacto: '',
  activo: true,
  id_moneda_base: '',
};

const CompanyCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<EmpresaInput>({
    resolver: zodResolver(empresaSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const { data: monedas = [] } = useQuery<MonedaApiResponse, Error, Moneda[]>({
    queryKey: finanzasKeys.monedas.activas(),
    queryFn: () => get<MonedaApiResponse>('/finanzas/monedas/activas/'),
    select: toList,
  });

  const createMutation = useMutation({
    mutationFn: (data: EmpresaInput) => post('/core/empresas/', { ...data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/empresas/'] });
      navigate('/empresas');
    },
    onError: () => snackbar.error('Error al crear empresa'),
  });

  const onSubmit = handleSubmit((values) => createMutation.mutate(values));

  return (
    <PageLayout maxWidth={560}>
      <PageHeader title="Nueva empresa" />
      {(!monedas || monedas.length === 0) && (
        <Alert severity="warning" sx={{ mb: 2 }}>No se encontraron monedas disponibles.</Alert>
      )}
      <Box component="form" onSubmit={onSubmit} noValidate>
        <Stack spacing={2}>
          <TextField
            label="Nombre legal"
            {...register('nombre_legal')}
            error={!!errors.nombre_legal}
            helperText={errors.nombre_legal?.message}
            fullWidth
          />
          <TextField
            label="Nombre comercial"
            {...register('nombre_comercial')}
            error={!!errors.nombre_comercial}
            helperText={errors.nombre_comercial?.message}
            fullWidth
          />
          <TextField
            label="Identificador fiscal"
            {...register('identificador_fiscal')}
            error={!!errors.identificador_fiscal}
            helperText={errors.identificador_fiscal?.message}
            fullWidth
          />
          <TextField
            type="email"
            label="Email contacto"
            {...register('email_contacto')}
            error={!!errors.email_contacto}
            helperText={errors.email_contacto?.message}
            fullWidth
          />
          <Controller
            name="activo"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Activo"
                value={field.value ? 'true' : 'false'}
                onChange={(e) => field.onChange(e.target.value === 'true')}
                fullWidth
              >
                <MenuItem value="true">Sí</MenuItem>
                <MenuItem value="false">No</MenuItem>
              </TextField>
            )}
          />
          <Controller
            name="id_moneda_base"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Moneda base"
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                error={!!errors.id_moneda_base}
                helperText={errors.id_moneda_base?.message}
                fullWidth
              >
                <MenuItem value="">Seleccione moneda</MenuItem>
                {(Array.isArray(monedas) ? monedas : []).map((m) => (
                  <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</MenuItem>
                ))}
              </TextField>
            )}
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/empresas')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Guardando…' : 'Crear empresa'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default CompanyCreatePage;
