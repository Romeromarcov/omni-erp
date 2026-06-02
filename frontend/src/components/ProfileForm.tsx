import React, { useEffect } from 'react';
import { Alert, Box, Button, TextField } from '@mui/material';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { profileSchema, type ProfileInput } from '../schemas/auth.schemas';

type ProfileFormValues = ProfileInput;

interface ProfileFormProps {
  initialValues: ProfileFormValues;
  onSubmit: (values: ProfileFormValues) => void;
  loading?: boolean;
  error?: string;
}

const ProfileForm: React.FC<ProfileFormProps> = ({ initialValues, onSubmit, loading, error }) => {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    mode: 'onBlur',
    defaultValues: initialValues,
  });

  // FE-HIGH-6: rehidratar con datos cargados sin pisar ediciones en curso.
  useEffect(() => {
    if (!isDirty) {
      reset(initialValues);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialValues]);

  return (
    <Box
      component="form"
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      sx={{ maxWidth: 400, mx: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}
    >
      <TextField
        label="Nombre"
        {...register('first_name')}
        error={!!errors.first_name}
        helperText={errors.first_name?.message}
        fullWidth
      />
      <TextField
        label="Apellido"
        {...register('last_name')}
        error={!!errors.last_name}
        helperText={errors.last_name?.message}
        fullWidth
      />
      <TextField
        label="Email"
        {...register('email')}
        error={!!errors.email}
        helperText={errors.email?.message}
        fullWidth
      />
      <TextField
        label="Sucursal Predeterminada"
        {...register('id_sucursal_predeterminada')}
        error={!!errors.id_sucursal_predeterminada}
        helperText={errors.id_sucursal_predeterminada?.message}
        fullWidth
      />
      {error && <Alert severity="error">{error}</Alert>}
      <Button type="submit" variant="contained" disabled={loading} fullWidth>
        {loading ? 'Guardando...' : 'Guardar cambios'}
      </Button>
    </Box>
  );
};

export default ProfileForm;
