import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { createUsuario } from '../../../services/users';
import PageLayout from '../../../components/PageLayout';
import { getEmpresaId } from '../../../utils/empresa';

const UserCreatePage: React.FC = () => {
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    is_active: true,
    es_superusuario_innova: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [message, setMessage] = useState('');
  const [emailError, setEmailError] = useState('');
  const id_empresa = getEmpresaId() || undefined;

  const createMutation = useMutation({
    mutationFn: (data: typeof form & { id_empresa?: string }) => createUsuario(data),
    onSuccess: () => {
      setMessage('Usuario creado exitosamente');
      setForm({ username: '', email: '', password: '', first_name: '', last_name: '', is_active: true, es_superusuario_innova: false });
      setConfirmPassword('');
      setEmailError('');
    },
    onError: () => {
      setMessage('Error al crear usuario');
    },
  });

  const loading = createMutation.isPending;

  const validateEmail = (email: string) => {
    // Simple regex for email validation
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
    if (name === 'email') {
      if (!validateEmail(value)) {
        setEmailError('Ingrese un email válido');
      } else {
        setEmailError('');
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== confirmPassword) {
      setMessage('Las contraseñas no coinciden');
      return;
    }
    if (!validateEmail(form.email)) {
      setEmailError('Ingrese un email válido');
      setMessage('');
      return;
    }
    createMutation.mutate({ ...form, id_empresa });
  };

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Crear Nuevo Usuario</Typography>
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField name="username" label="Username" value={form.username} onChange={handleChange} required fullWidth />
          <TextField
            name="email"
            label="Email"
            value={form.email}
            onChange={handleChange}
            required
            fullWidth
            error={!!emailError}
            helperText={emailError || undefined}
          />
          <TextField
            name="password"
            label="Password"
            type={showPassword ? 'text' : 'password'}
            value={form.password}
            onChange={handleChange}
            required
            fullWidth
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => setShowPassword(v => !v)} edge="end" tabIndex={-1}>
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          <TextField
            name="confirmPassword"
            label="Confirmar contraseña"
            type={showConfirmPassword ? 'text' : 'password'}
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
            required
            fullWidth
            error={!!(confirmPassword && form.password !== confirmPassword)}
            helperText={confirmPassword && form.password !== confirmPassword ? 'Las contraseñas no coinciden' : undefined}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => setShowConfirmPassword(v => !v)} edge="end" tabIndex={-1}>
                    {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          <TextField name="first_name" label="Nombre" value={form.first_name} onChange={handleChange} fullWidth />
          <TextField name="last_name" label="Apellido" value={form.last_name} onChange={handleChange} fullWidth />
          <FormControlLabel
            control={<Checkbox name="is_active" checked={form.is_active} onChange={handleChange} />}
            label="Activo"
          />
          {/* Superusuario checkbox removed as requested */}
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button type="submit" variant="contained" disabled={loading}>Crear usuario</Button>
          </Stack>
          {message && (
            <Alert severity={message.includes('exitosamente') ? 'success' : 'error'}>{message}</Alert>
          )}
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default UserCreatePage;
