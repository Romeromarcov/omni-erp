import React, { useState } from 'react';
import { Alert, Box, Button, TextField } from '@mui/material';

interface ProfileFormValues {
  first_name: string;
  last_name: string;
  email: string;
  id_sucursal_predeterminada: string;
}

interface ProfileFormProps {
  initialValues: ProfileFormValues;
  onSubmit: (values: ProfileFormValues) => void;
  loading?: boolean;
  error?: string;
}

const ProfileForm: React.FC<ProfileFormProps> = ({ initialValues, onSubmit, loading, error }) => {
  const [values, setValues] = useState(initialValues);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValues({ ...values, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values);
  };

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ maxWidth: 400, mx: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
      <TextField label="Nombre" name="first_name" value={values.first_name} onChange={handleChange} required fullWidth />
      <TextField label="Apellido" name="last_name" value={values.last_name} onChange={handleChange} required fullWidth />
      <TextField label="Email" name="email" value={values.email} onChange={handleChange} required fullWidth />
      <TextField label="Sucursal Predeterminada" name="id_sucursal_predeterminada" value={values.id_sucursal_predeterminada} onChange={handleChange} required fullWidth />
      {error && <Alert severity="error">{error}</Alert>}
      <Button type="submit" variant="contained" disabled={loading} fullWidth>
        {loading ? 'Guardando...' : 'Guardar cambios'}
      </Button>
    </Box>
  );
};

export default ProfileForm;
