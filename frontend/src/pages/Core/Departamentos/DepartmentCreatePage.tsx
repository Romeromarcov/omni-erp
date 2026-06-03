import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { getEmpresaId } from '../../../utils/empresa';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { departamentoSchema, type DepartamentoInput } from '../../../schemas/core.schemas';
import { Box, Button, MenuItem, Stack, TextField } from '@mui/material';
import { PageHeader } from '../../../components/ui';

const defaultValues: DepartamentoInput = {
  nombre_departamento: '',
  descripcion: '',
  activo: true,
};

const DepartmentCreatePage: React.FC = () => {
  let { id_empresa } = useParams<{ id_empresa: string }>();
  if (!id_empresa) id_empresa = getEmpresaId() || '';
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<DepartamentoInput>({
    resolver: zodResolver(departamentoSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const createMutation = useMutation({
    mutationFn: (data: DepartamentoInput) =>
      post('/core/departamentos/', { ...data, id_empresa: id_empresa || '' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/departamentos/'] });
      navigate(`/empresas/${id_empresa}/departamentos`);
    },
    onError: () => snackbar.error('Error al crear departamento'),
  });

  const onSubmit = handleSubmit((values) => createMutation.mutate(values));

  return (
    <PageLayout maxWidth={560}>
      <PageHeader title="Nuevo departamento" />
      <Box component="form" onSubmit={onSubmit} noValidate>
        <Stack spacing={2}>
          <TextField
            label="Nombre"
            {...register('nombre_departamento')}
            error={!!errors.nombre_departamento}
            helperText={errors.nombre_departamento?.message}
            fullWidth
          />
          <TextField
            label="Descripción"
            {...register('descripcion')}
            error={!!errors.descripcion}
            helperText={errors.descripcion?.message}
            fullWidth
            multiline
            minRows={3}
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
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate(-1)}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Guardando…' : 'Crear departamento'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default DepartmentCreatePage;
