import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, CircularProgress, FormControlLabel, Checkbox, Stack, TextField } from '@mui/material';
import { PageHeader } from '../../../components/ui';
import { fetchRol, updateRol } from '../../../services/roles';
import type { Rol } from '../../../services/roles';
import PageLayout from '../../../components/PageLayout';

const RoleDetailPage: React.FC = () => {
  const { id_rol } = useParams<{ id_rol: string }>();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<Rol>>({});
  const [message, setMessage] = useState('');

  const { data: rol, isLoading } = useQuery<Rol>({
    queryKey: ['/core/roles/', id_rol],
    queryFn: () => fetchRol(id_rol!),
    enabled: !!id_rol,
  });

  useEffect(() => {
    if (rol) {
      setForm(rol);
    }
  }, [rol]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Rol>) => updateRol(id_rol!, data),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['/core/roles/', id_rol] });
      queryClient.invalidateQueries({ queryKey: ['/core/roles/'] });
      setForm(updated);
      setMessage('Rol actualizado');
    },
    onError: () => {
      setMessage('Error al actualizar rol');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_rol) return;
    updateMutation.mutate(form);
  };

  if (isLoading) return (
    <PageLayout maxWidth={480}>
      <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
    </PageLayout>
  );
  if (!rol) return (
    <PageLayout maxWidth={480}>
      <Alert severity="error">Rol no encontrado</Alert>
    </PageLayout>
  );

  return (
    <PageLayout maxWidth={480}>
      <PageHeader title="Detalle/Edición de Rol" subtitle={rol.nombre_rol} />
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField name="nombre_rol" label="Nombre" value={form.nombre_rol || ''} onChange={handleChange} required fullWidth />
          <TextField name="descripcion" label="Descripción" value={form.descripcion || ''} onChange={handleChange} fullWidth />
          <FormControlLabel
            control={<Checkbox name="activo" checked={!!form.activo} onChange={handleChange} />}
            label="Activo"
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button type="submit" variant="contained" disabled={updateMutation.isPending}>Actualizar rol</Button>
          </Stack>
          {message && (
            <Alert severity={message.includes('actualizado') ? 'success' : 'error'}>{message}</Alert>
          )}
        </Stack>
      </Box>
      {/* Aquí iría la gestión de permisos asignados al rol */}
    </PageLayout>
  );
};

export default RoleDetailPage;
