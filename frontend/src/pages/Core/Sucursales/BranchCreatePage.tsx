import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { getEmpresaId } from '../../../utils/empresa';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { sucursalSchema, type SucursalInput } from '../../../schemas/core.schemas';
import { Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';

const defaultValues: SucursalInput = {
  nombre: '',
  codigo_sucursal: '',
  direccion: '',
  telefono: '',
  email_contacto: '',
  ubicacion_gps_json: '',
  activo: true,
};

const BranchCreatePage: React.FC = () => {
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
  } = useForm<SucursalInput>({
    resolver: zodResolver(sucursalSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const createMutation = useMutation({
    mutationFn: (data: SucursalInput) =>
      post('/core/sucursales/', { ...data, id_empresa: id_empresa || '' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/sucursales/'] });
      navigate(`/empresas/${id_empresa}/sucursales`);
    },
    onError: () => snackbar.error('Error al crear sucursal'),
  });

  const onSubmit = handleSubmit((values) => createMutation.mutate(values));

  return (
    <PageLayout maxWidth={560}>
      <Typography variant="h5" mb={3}>Nueva sucursal</Typography>
      <Box component="form" onSubmit={onSubmit} noValidate>
        <Stack spacing={2}>
          <TextField
            label="Nombre"
            {...register('nombre')}
            error={!!errors.nombre}
            helperText={errors.nombre?.message}
            fullWidth
          />
          <TextField
            label="Código"
            {...register('codigo_sucursal')}
            error={!!errors.codigo_sucursal}
            helperText={errors.codigo_sucursal?.message}
            fullWidth
          />
          <TextField
            label="Dirección"
            {...register('direccion')}
            error={!!errors.direccion}
            helperText={errors.direccion?.message}
            fullWidth
            multiline
            minRows={2}
          />
          <TextField
            label="Teléfono"
            {...register('telefono')}
            error={!!errors.telefono}
            helperText={errors.telefono?.message}
            fullWidth
          />
          <TextField
            label="Email"
            type="email"
            {...register('email_contacto')}
            error={!!errors.email_contacto}
            helperText={errors.email_contacto?.message}
            fullWidth
          />
          <TextField
            label="Ubicación GPS (JSON)"
            {...register('ubicacion_gps_json')}
            error={!!errors.ubicacion_gps_json}
            helperText={errors.ubicacion_gps_json?.message}
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
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate(-1)}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Guardando…' : 'Crear sucursal'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default BranchCreatePage;
