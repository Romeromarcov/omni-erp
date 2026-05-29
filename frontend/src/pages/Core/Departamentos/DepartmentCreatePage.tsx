import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEmpresaId } from '../../../utils/empresa';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';

interface Departamento {
  nombre_departamento: string;
  descripcion: string;
  activo: boolean;
  id_empresa: string;
}

const DepartmentCreatePage: React.FC = () => {
  let { id_empresa } = useParams<{ id_empresa: string }>();
  if (!id_empresa) id_empresa = getEmpresaId() || '';
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Departamento>({
    nombre_departamento: '',
    descripcion: '',
    activo: true,
    id_empresa: id_empresa || '',
  });

  const createMutation = useMutation({
    mutationFn: (data: Departamento) => post<Departamento>('/core/departamentos/', data as unknown as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/departamentos/'] });
      navigate(`/empresas/${id_empresa}/departamentos`);
    },
    onError: () => alert('Error al crear departamento'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(form);
  };

  return (
    <PageLayout maxWidth={560}>
      <Typography variant="h5" mb={3}>Nuevo departamento</Typography>
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField label="Nombre" value={form.nombre_departamento} onChange={e => setForm(f => ({ ...f, nombre_departamento: e.target.value }))} required fullWidth />
          <TextField label="Descripción" value={form.descripcion} onChange={e => setForm(f => ({ ...f, descripcion: e.target.value }))} required fullWidth multiline minRows={3} />
          <TextField select label="Activo" value={form.activo ? 'true' : 'false'} onChange={e => setForm(f => ({ ...f, activo: e.target.value === 'true' }))} fullWidth>
            <MenuItem value="true">Sí</MenuItem>
            <MenuItem value="false">No</MenuItem>
          </TextField>
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
