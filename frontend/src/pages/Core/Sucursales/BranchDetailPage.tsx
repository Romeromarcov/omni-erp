import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { get, put } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

type Sucursal = {
  id_sucursal: string;
  nombre: string;
  codigo_sucursal: string;
  direccion: string;
  telefono: string;
  email_contacto: string;
  ubicacion_gps_json: string;
  activo: boolean;
  id_empresa: string;
};

const BranchDetailPage: React.FC = () => {
  const { id_sucursal } = useParams<{ id_sucursal: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const isEditRoute = location.pathname.endsWith('/edit');
  const [edit, setEdit] = useState(isEditRoute);
  const [form, setForm] = useState<Sucursal | null>(null);

  const { data: sucursal, isLoading } = useQuery<Sucursal>({
    queryKey: ['/core/sucursales/', id_sucursal],
    queryFn: () => get<Sucursal>(`/core/sucursales/${id_sucursal}/`),
    enabled: !!id_sucursal,
  });

  useEffect(() => {
    if (sucursal) {
      setForm(sucursal);
    }
  }, [sucursal]);

  useEffect(() => {
    setEdit(isEditRoute);
  }, [isEditRoute]);

  const updateMutation = useMutation({
    mutationFn: (data: Sucursal) => put<Sucursal>(`/core/sucursales/${id_sucursal}/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/sucursales/', id_sucursal] });
      queryClient.invalidateQueries({ queryKey: ['/core/sucursales/'] });
      setEdit(false);
      alert('Sucursal actualizada');
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
  if (!sucursal) return (
    <PageLayout maxWidth={480}>
      <Typography align="center" color="text.secondary" py={4}>No encontrada</Typography>
    </PageLayout>
  );

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Detalle de sucursal</Typography>
      {!edit ? (
        <Stack spacing={1.5}>
          <Typography><b>Nombre:</b> {sucursal.nombre}</Typography>
          <Typography><b>Código:</b> {sucursal.codigo_sucursal}</Typography>
          <Typography><b>Dirección:</b> {sucursal.direccion}</Typography>
          <Typography><b>Teléfono:</b> {sucursal.telefono}</Typography>
          <Typography><b>Email:</b> {sucursal.email_contacto}</Typography>
          <Typography><b>Ubicación GPS:</b> {sucursal.ubicacion_gps_json}</Typography>
          <Typography><b>Activo:</b> {sucursal.activo ? 'Sí' : 'No'}</Typography>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
            <Button variant="contained" onClick={() => setEdit(true)}>Editar</Button>
          </Stack>
        </Stack>
      ) : (
        <Box component="form" onSubmit={handleUpdate}>
          <Stack spacing={2}>
            <TextField label="Nombre" value={form?.nombre || ''} onChange={e => setForm(f => f ? { ...f, nombre: e.target.value } : f)} required fullWidth />
            <TextField label="Código" value={form?.codigo_sucursal || ''} onChange={e => setForm(f => f ? { ...f, codigo_sucursal: e.target.value } : f)} required fullWidth />
            <TextField label="Dirección" value={form?.direccion || ''} onChange={e => setForm(f => f ? { ...f, direccion: e.target.value } : f)} required fullWidth />
            <TextField label="Teléfono" value={form?.telefono || ''} onChange={e => setForm(f => f ? { ...f, telefono: e.target.value } : f)} required fullWidth />
            <TextField label="Email" value={form?.email_contacto || ''} onChange={e => setForm(f => f ? { ...f, email_contacto: e.target.value } : f)} fullWidth />
            <TextField label="Ubicación GPS (JSON)" value={form?.ubicacion_gps_json || ''} onChange={e => setForm(f => f ? { ...f, ubicacion_gps_json: e.target.value } : f)} fullWidth />
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

export default BranchDetailPage;
