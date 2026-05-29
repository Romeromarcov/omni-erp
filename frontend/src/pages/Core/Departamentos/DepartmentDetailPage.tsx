import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { get, put } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

interface Departamento {
  id_departamento: string;
  nombre_departamento: string;
  descripcion: string;
  activo: boolean;
}

const DepartmentDetailPage: React.FC = () => {
  const { id_departamento } = useParams<{ id_departamento: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState<Departamento | null>(null);

  const { data: departamento, isLoading } = useQuery<Departamento>({
    queryKey: ['/core/departamentos/', id_departamento],
    queryFn: () => get<Departamento>(`/core/departamentos/${id_departamento}/`),
    enabled: !!id_departamento,
  });

  useEffect(() => {
    if (departamento) {
      setForm(departamento);
    }
  }, [departamento]);

  const updateMutation = useMutation({
    mutationFn: (data: Departamento) => put<Departamento>(`/core/departamentos/${id_departamento}/`, data as unknown as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/departamentos/', id_departamento] });
      queryClient.invalidateQueries({ queryKey: ['/core/departamentos/'] });
      setEdit(false);
      alert('Departamento actualizado');
    },
    onError: () => {
      alert('Error al actualizar');
    },
  });

  const handleUpdate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    updateMutation.mutate(form);
  };

  if (isLoading) return (
    <PageLayout maxWidth={480}>
      <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
    </PageLayout>
  );
  if (!departamento) return (
    <PageLayout maxWidth={480}>
      <Typography align="center" color="text.secondary" py={4}>No encontrado</Typography>
    </PageLayout>
  );

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Detalle de departamento</Typography>
      {!edit ? (
        <Stack spacing={1.5}>
          <Typography><b>Nombre:</b> {departamento.nombre_departamento}</Typography>
          <Typography><b>Descripción:</b> {departamento.descripcion}</Typography>
          <Typography><b>Activo:</b> {departamento.activo ? 'Sí' : 'No'}</Typography>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
            <Button variant="contained" onClick={() => setEdit(true)}>Editar</Button>
          </Stack>
        </Stack>
      ) : (
        <Box component="form" onSubmit={handleUpdate}>
          <Stack spacing={2}>
            <TextField label="Nombre" value={form?.nombre_departamento || ''} onChange={e => setForm(f => f ? { ...f, nombre_departamento: e.target.value } : f)} required fullWidth />
            <TextField label="Descripción" value={form?.descripcion || ''} onChange={e => setForm(f => f ? { ...f, descripcion: e.target.value } : f)} required fullWidth />
            <TextField select label="Activo" value={form?.activo ? 'true' : 'false'} onChange={e => setForm(f => f ? { ...f, activo: e.target.value === 'true' } : f)} fullWidth>
              <MenuItem value="true">Sí</MenuItem>
              <MenuItem value="false">No</MenuItem>
            </TextField>
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button type="button" variant="outlined" onClick={() => setEdit(false)}>Cancelar</Button>
              <Button type="submit" variant="contained">Guardar</Button>
            </Stack>
          </Stack>
        </Box>
      )}
    </PageLayout>
  );
};

export default DepartmentDetailPage;
