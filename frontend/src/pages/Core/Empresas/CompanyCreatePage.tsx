import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { post, get } from '../../../services/api';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';

interface Empresa {
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  id_moneda_base: string;
}

interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
}

type MonedaApiResponse = Moneda[] | { results: Moneda[] };

const CompanyCreatePage: React.FC = () => {
  const [empresa, setEmpresa] = useState<Empresa>({
    nombre_legal: '',
    nombre_comercial: '',
    identificador_fiscal: '',
    email_contacto: '',
    activo: true,
    id_moneda_base: '',
  });
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: monedas = [] } = useQuery<MonedaApiResponse, Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/activas/'],
    queryFn: () => get<MonedaApiResponse>('/finanzas/monedas/activas/'),
    select: toList,
  });

  const createMutation = useMutation({
    mutationFn: (data: Empresa) => post<Empresa>('/core/empresas/', { ...data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/empresas/'] });
      navigate('/empresas');
    },
    onError: () => alert('Error al crear empresa'),
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    if (name === 'activo') {
      setEmpresa({ ...empresa, activo: value === 'true' });
    } else {
      setEmpresa({ ...empresa, [name]: value });
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(empresa);
  };

  return (
    <PageLayout maxWidth={560}>
      <Typography variant="h5" mb={3}>Nueva empresa</Typography>
      {(!monedas || monedas.length === 0) && (
        <Alert severity="warning" sx={{ mb: 2 }}>No se encontraron monedas disponibles.</Alert>
      )}
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField name="nombre_legal" label="Nombre legal" value={empresa.nombre_legal} onChange={handleChange} required fullWidth />
          <TextField name="nombre_comercial" label="Nombre comercial" value={empresa.nombre_comercial} onChange={handleChange} required fullWidth />
          <TextField name="identificador_fiscal" label="Identificador fiscal" value={empresa.identificador_fiscal} onChange={handleChange} required fullWidth />
          <TextField name="email_contacto" type="email" label="Email contacto" value={empresa.email_contacto} onChange={handleChange} required fullWidth />
          <TextField select name="activo" label="Activo" value={empresa.activo ? 'true' : 'false'} onChange={handleChange} fullWidth>
            <MenuItem value="true">Sí</MenuItem>
            <MenuItem value="false">No</MenuItem>
          </TextField>
          <TextField select name="id_moneda_base" label="Moneda base" value={empresa.id_moneda_base} onChange={handleChange} required fullWidth>
            <MenuItem value="">Seleccione moneda</MenuItem>
            {(Array.isArray(monedas) ? monedas : []).map(m => (
              <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</MenuItem>
            ))}
          </TextField>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/empresas')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Guardando…' : 'Crear empresa'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default CompanyCreatePage;
