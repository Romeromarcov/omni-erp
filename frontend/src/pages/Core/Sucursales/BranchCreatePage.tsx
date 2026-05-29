import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEmpresaId } from '../../../utils/empresa';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';

interface Sucursal {
  nombre: string;
  codigo_sucursal: string;
  direccion: string;
  telefono: string;
  email_contacto: string;
  ubicacion_gps_json: string;
  activo: boolean;
  id_empresa: string;
}

const BranchCreatePage: React.FC = () => {
  let { id_empresa } = useParams<{ id_empresa: string }>();
  if (!id_empresa) id_empresa = getEmpresaId() || '';
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Sucursal>({
    nombre: '',
    codigo_sucursal: '',
    direccion: '',
    telefono: '',
    email_contacto: '',
    ubicacion_gps_json: '',
    activo: true,
    id_empresa: id_empresa || '',
  });

  const createMutation = useMutation({
    mutationFn: (data: Sucursal) => post<Sucursal>('/core/sucursales/', data as unknown as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/sucursales/'] });
      navigate(`/empresas/${id_empresa}/sucursales`);
    },
    onError: () => alert('Error al crear sucursal'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(form);
  };

  return (
    <PageLayout maxWidth={560}>
      <Typography variant="h5" mb={3}>Nueva sucursal</Typography>
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField label="Nombre" value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} required fullWidth />
          <TextField label="Código" value={form.codigo_sucursal} onChange={e => setForm(f => ({ ...f, codigo_sucursal: e.target.value }))} required fullWidth />
          <TextField label="Dirección" value={form.direccion} onChange={e => setForm(f => ({ ...f, direccion: e.target.value }))} required fullWidth multiline minRows={2} />
          <TextField label="Teléfono" value={form.telefono} onChange={e => setForm(f => ({ ...f, telefono: e.target.value }))} required fullWidth />
          <TextField label="Email" type="email" value={form.email_contacto} onChange={e => setForm(f => ({ ...f, email_contacto: e.target.value }))} fullWidth />
          <TextField label="Ubicación GPS (JSON)" value={form.ubicacion_gps_json} onChange={e => setForm(f => ({ ...f, ubicacion_gps_json: e.target.value }))} fullWidth />
          <TextField select label="Activo" value={form.activo ? 'true' : 'false'} onChange={e => setForm(f => ({ ...f, activo: e.target.value === 'true' }))} fullWidth>
            <MenuItem value="true">Sí</MenuItem>
            <MenuItem value="false">No</MenuItem>
          </TextField>
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
