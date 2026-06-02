import React from 'react';
import { Alert, Button, TextField } from '@mui/material';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, type LoginInput } from '../schemas/auth.schemas';
import PageLayout from './PageLayout';

interface LoginFormProps {
  onSubmit: (username: string, password: string) => void;
  loading?: boolean;
  error?: string;
}

const LoginForm: React.FC<LoginFormProps> = ({ onSubmit, loading, error }) => {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: { username: '', password: '' },
  });

  const submit = (values: LoginInput) => {
    onSubmit(values.username, values.password);
  };

  return (
    <PageLayout maxWidth={350}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Iniciar sesión</h2>
      <form onSubmit={handleSubmit(submit)} style={{ display: 'flex', flexDirection: 'column', gap: 18 }} noValidate>
        <TextField
          label="Usuario"
          {...register('username')}
          error={!!errors.username}
          helperText={errors.username?.message}
          fullWidth
        />
        <TextField
          label="Contraseña"
          type="password"
          {...register('password')}
          error={!!errors.password}
          helperText={errors.password?.message}
          fullWidth
        />
        {error && <Alert severity="error">{error}</Alert>}
        <Button type="submit" variant="contained" disabled={loading} fullWidth>
          {loading ? 'Ingresando...' : 'Ingresar'}
        </Button>
      </form>
    </PageLayout>
  );
};

export default LoginForm;
