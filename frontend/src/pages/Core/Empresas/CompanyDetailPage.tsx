import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put } from '../../../services/api';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { Alert, Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';

interface Empresa {
  id_empresa: string;
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  fecha_registro: string;
  id_moneda_base: string;
}

interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
}

type MonedaApiResponse = Moneda[] | { results: Moneda[] };

const CompanyDetailPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const cleanId = id_empresa?.replace(':', '') || '';

  const [localEmpresa, setLocalEmpresa] = useState<Empresa | null>(null);

  const { data: empresaData, isLoading: loadingEmpresa } = useQuery<Empresa>({
    queryKey: ['/core/empresas/', cleanId],
    queryFn: () => get<Empresa>(`/core/empresas/${cleanId}/`),
    enabled: !!cleanId,
  });

  useEffect(() => {
    if (empresaData) {
      setLocalEmpresa({
        ...empresaData,
        activo: Boolean(empresaData.activo),
        id_moneda_base: empresaData.id_moneda_base ?? '',
      });
    }
  }, [empresaData]);

  const { data: monedas = [] } = useQuery<MonedaApiResponse, Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/activas/'],
    queryFn: () => get<MonedaApiResponse>('/finanzas/monedas/activas/'),
    select: toList,
  });

  const updateMutation = useMutation({
    mutationFn: (data: Empresa) => put<Empresa>(`/core/empresas/${cleanId}/`, { ...data, activo: !!data.activo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/empresas/', cleanId] });
      queryClient.invalidateQueries({ queryKey: ['/core/empresas/'] });
      snackbar.success('Empresa actualizada');
    },
    onError: () => snackbar.error('Error al actualizar'),
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!localEmpresa) return;
    const { name, value } = e.target;
    if (name === 'activo') {
      setLocalEmpresa({ ...localEmpresa, activo: value === 'true' });
    } else if (name === 'id_moneda_base') {
      setLocalEmpresa({ ...localEmpresa, id_moneda_base: value.toString() });
    } else {
      setLocalEmpresa({ ...localEmpresa, [name]: value });
    }
  };

  const handleSave = () => {
    if (!localEmpresa) return;
    updateMutation.mutate(localEmpresa);
  };

  if (loadingEmpresa || !localEmpresa) {
    return (
      <PageLayout maxWidth={560}>
        <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
      </PageLayout>
    );
  }

  return (
    <PageLayout maxWidth={560}>
      <Typography variant="h5" mb={3}>Detalle de empresa</Typography>
      {(!monedas || monedas.length === 0) && (
        <Alert severity="warning" sx={{ mb: 2 }}>No se encontraron monedas disponibles.</Alert>
      )}
      <Box component="form" onSubmit={(e) => { e.preventDefault(); handleSave(); }}>
        <Stack spacing={2}>
          <TextField name="nombre_legal" label="Nombre legal" value={localEmpresa.nombre_legal} onChange={handleChange} fullWidth />
          <TextField name="nombre_comercial" label="Nombre comercial" value={localEmpresa.nombre_comercial} onChange={handleChange} fullWidth />
          <TextField name="identificador_fiscal" label="Identificador fiscal" value={localEmpresa.identificador_fiscal} onChange={handleChange} fullWidth />
          <TextField name="email_contacto" type="email" label="Email contacto" value={localEmpresa.email_contacto} onChange={handleChange} fullWidth />
          <TextField select name="activo" label="Activo" value={localEmpresa.activo ? 'true' : 'false'} onChange={handleChange} fullWidth>
            <MenuItem value="true">Sí</MenuItem>
            <MenuItem value="false">No</MenuItem>
          </TextField>
          <TextField select name="id_moneda_base" label="Moneda base" value={localEmpresa.id_moneda_base?.toString() ?? ''} onChange={handleChange} fullWidth>
            <MenuItem value="">Seleccione moneda</MenuItem>
            {(Array.isArray(monedas) ? monedas : []).map(moneda => (
              <MenuItem key={moneda.id_moneda} value={moneda.id_moneda}>{moneda.nombre} ({moneda.codigo_iso})</MenuItem>
            ))}
          </TextField>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/empresas')}>Volver a la lista</Button>
            <Button type="submit" variant="contained" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Guardando…' : 'Guardar cambios'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default CompanyDetailPage;
