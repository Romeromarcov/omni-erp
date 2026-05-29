import React, { useState, useEffect } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createPlantillaMaestro, updatePlantillaMaestro, getPlantillasMaestro } from '../../../services/plantillasService';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { Alert, Autocomplete, Box, Button, Chip, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';

interface MetodoPago {
  id_metodo_pago: string;
  nombre: string;
}

interface Moneda {
  id_moneda: string;
  nombre: string;
  simbolo: string;
}

const PlantillaMaestroFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEditing = !!id;
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    nombre: '',
    descripcion: '',
    metodos_pago: [] as string[],
    monedas: [] as string[],
    activa: true,
  });

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const { data: metodosPago = [] } = useQuery<MetodoPago[]>({
    queryKey: ['/finanzas/metodos-pago-empresa-activas/', idEmpresa],
    queryFn: () => fetchMetodosPagoEmpresaActivos(idEmpresa) as unknown as Promise<MetodoPago[]>,
    enabled: !!idEmpresa,
  });

  const { data: monedas = [] } = useQuery<Moneda[]>({
    queryKey: ['/finanzas/monedas-empresa-activas/', idEmpresa],
    queryFn: () => fetchMonedasEmpresaActivas(idEmpresa) as unknown as Promise<Moneda[]>,
    enabled: !!idEmpresa,
  });

  const { data: plantillasData } = useQuery({
    queryKey: ['/finanzas/plantillas-maestro-cajas/', idEmpresa],
    queryFn: () => getPlantillasMaestro(idEmpresa),
    enabled: isEditing && !!idEmpresa,
  });

  useEffect(() => {
    if (isEditing && id && plantillasData) {
      const plantilla = plantillasData.find(p => p.id_plantilla === id);
      if (plantilla) {
        setForm({
          nombre: plantilla.nombre,
          descripcion: plantilla.descripcion || '',
          metodos_pago: plantilla.metodos_pago,
          monedas: plantilla.monedas,
          activa: plantilla.activa,
        });
      }
    }
  }, [isEditing, id, plantillasData]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const data = { ...form, id_empresa: idEmpresa };
      if (isEditing && id) {
        return updatePlantillaMaestro(id, data);
      }
      return createPlantillaMaestro(data as Parameters<typeof createPlantillaMaestro>[0]);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/plantillas-maestro-cajas/', idEmpresa] });
      setSuccess(isEditing ? 'Plantilla actualizada exitosamente' : 'Plantilla creada exitosamente');
      setTimeout(() => {
        navigate('/finanzas/plantillas-maestro');
      }, 1500);
    },
    onError: (err) => {
      setError('Error al guardar la plantilla');
      console.error(err);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.nombre.trim()) {
      setError('El nombre es obligatorio');
      return;
    }
    setError('');
    setSuccess('');
    saveMutation.mutate();
  };

  const handleChange = (field: string, value: string | boolean | string[]) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  return (
    <PageLayout maxWidth={800}>
      <Typography variant="h5" mb={3}>
        {isEditing ? 'Editar Plantilla Maestro' : 'Nueva Plantilla Maestro'}
      </Typography>

      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={3}>
          <TextField
            label="Nombre"
            value={form.nombre}
            onChange={(e) => handleChange('nombre', e.target.value)}
            required
            fullWidth
          />

          <TextField
            label="Descripción"
            value={form.descripcion}
            onChange={(e) => handleChange('descripcion', e.target.value)}
            multiline
            minRows={3}
            fullWidth
          />

          <Autocomplete
            multiple
            options={metodosPago}
            getOptionLabel={(option) => option.nombre}
            value={metodosPago.filter(mp => form.metodos_pago.includes(mp.id_metodo_pago))}
            onChange={(_, newValue) => {
              handleChange('metodos_pago', newValue.map(mp => mp.id_metodo_pago));
            }}
            renderTags={(value, getTagProps) =>
              value.map((option, index) => (
                <Chip
                  label={option.nombre}
                  {...getTagProps({ index })}
                  size="small"
                />
              ))
            }
            renderInput={(params) => (
              <TextField
                {...params}
                label="Métodos de Pago"
                placeholder="Selecciona métodos de pago"
              />
            )}
          />

          <Autocomplete
            multiple
            options={monedas}
            getOptionLabel={(option) => `${option.nombre} (${option.simbolo})`}
            value={monedas.filter(m => form.monedas.includes(m.id_moneda))}
            onChange={(_, newValue) => {
              handleChange('monedas', newValue.map(m => m.id_moneda));
            }}
            renderTags={(value, getTagProps) =>
              value.map((option, index) => (
                <Chip
                  label={`${option.nombre} (${option.simbolo})`}
                  {...getTagProps({ index })}
                  size="small"
                />
              ))
            }
            renderInput={(params) => (
              <TextField
                {...params}
                label="Monedas"
                placeholder="Selecciona monedas"
              />
            )}
          />

          <FormControlLabel
            control={
              <Switch
                checked={form.activa}
                onChange={(e) => handleChange('activa', e.target.checked)}
              />
            }
            label="Activa"
          />

          {error && <Alert severity="error">{error}</Alert>}
          {success && <Alert severity="success">{success}</Alert>}

          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button
              type="button"
              variant="outlined"
              onClick={() => navigate('/finanzas/plantillas-maestro')}
            >
              Cancelar
            </Button>
            <Button type="submit" variant="contained" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Guardando...' : (isEditing ? 'Actualizar' : 'Crear')}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default PlantillaMaestroFormPage;
