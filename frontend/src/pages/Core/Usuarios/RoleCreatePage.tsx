import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { PageHeader } from '../../../components/ui';
import { createRol } from '../../../services/roles';
import { fetchEmpresas } from '../../../services/empresas';
import type { Empresa } from '../../../services/empresas';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';

type EmpresaApiResponse = Empresa[] | { results: Empresa[] };

const RoleCreatePage: React.FC = () => {
  const [form, setForm] = useState({
    nombre_rol: '',
    descripcion: '',
    activo: true,
    id_empresa: '',
  });
  const [message, setMessage] = useState('');
  const [empresaSearch, setEmpresaSearch] = useState('');
  const queryClient = useQueryClient();

  const { data: empresas = [] } = useQuery<EmpresaApiResponse, Error, Empresa[]>({
    queryKey: ['/core/empresas/'],
    queryFn: fetchEmpresas as () => Promise<EmpresaApiResponse>,
    select: toList,
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };

  const createMutation = useMutation({
    mutationFn: () => createRol(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/roles/'] });
      setMessage('Rol creado exitosamente');
      setForm({ nombre_rol: '', descripcion: '', activo: true, id_empresa: '' });
    },
    onError: () => {
      setMessage('Error al crear rol');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate();
  };

  const loading = createMutation.isPending;

  return (
    <PageLayout maxWidth={560}>
      <PageHeader title="Crear Nuevo Rol" />
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField name="nombre_rol" label="Nombre" value={form.nombre_rol} onChange={handleChange} required fullWidth />
          <TextField name="descripcion" label="Descripción" value={form.descripcion} onChange={handleChange} fullWidth />
          <FormControlLabel
            control={<Checkbox name="activo" checked={form.activo} onChange={handleChange} />}
            label="Activo"
          />
          <TextField
            label="Buscar empresa..."
            value={empresaSearch}
            onChange={e => setEmpresaSearch(e.target.value)}
            fullWidth
          />
          <TextField
            select
            name="id_empresa"
            label="Empresa"
            value={form.id_empresa}
            onChange={e => setForm(f => ({ ...f, id_empresa: e.target.value }))}
            required
            fullWidth
          >
            <MenuItem value="">Seleccione una empresa...</MenuItem>
            {empresas
              .filter(e =>
                e.nombre_legal.toLowerCase().includes(empresaSearch.toLowerCase()) ||
                e.nombre_comercial.toLowerCase().includes(empresaSearch.toLowerCase())
              )
              .map(e => (
                <MenuItem key={e.id_empresa} value={e.id_empresa}>
                  {e.nombre_legal} ({e.nombre_comercial})
                </MenuItem>
              ))}
          </TextField>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Creando...' : 'Crear rol'}
            </Button>
          </Stack>
          {message && (
            <Alert severity={message.includes('exitosamente') ? 'success' : 'error'}>{message}</Alert>
          )}
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default RoleCreatePage;
