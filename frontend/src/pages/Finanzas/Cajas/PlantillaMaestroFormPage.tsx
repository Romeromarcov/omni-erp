import React, { useState, useEffect } from 'react';
import { PageContainer, PageHeader } from '../../../components/ui';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { createPlantillaMaestro, updatePlantillaMaestro, getPlantillasMaestro } from '../../../services/plantillasService';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { plantillaMaestroSchema, type PlantillaMaestroInput } from '../../../schemas/finanzas.schemas';
import { Alert, Autocomplete, Box, Button, Card, Chip, FormControlLabel, Stack, Switch, TextField } from '@mui/material';

interface MetodoPago {
  id_metodo_pago: string;
  nombre: string;
}

interface Moneda {
  id_moneda: string;
  nombre: string;
  simbolo: string;
}

const defaultValues: PlantillaMaestroInput = {
  nombre: '',
  descripcion: '',
  metodos_pago: [],
  monedas: [],
  activa: true,
};

const PlantillaMaestroFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEditing = !!id;
  const queryClient = useQueryClient();

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<PlantillaMaestroInput>({
    resolver: zodResolver(plantillaMaestroSchema),
    mode: 'onBlur',
    defaultValues,
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

  // FE-HIGH-6: rehidratar sin pisar ediciones en curso.
  useEffect(() => {
    if (isEditing && id && plantillasData && !isDirty) {
      const plantilla = plantillasData.find(p => p.id_plantilla === id);
      if (plantilla) {
        reset({
          nombre: plantilla.nombre,
          descripcion: plantilla.descripcion || '',
          metodos_pago: plantilla.metodos_pago,
          monedas: plantilla.monedas,
          activa: plantilla.activa,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEditing, id, plantillasData]);

  const saveMutation = useMutation({
    mutationFn: (form: PlantillaMaestroInput) => {
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

  const onSubmit = (form: PlantillaMaestroInput) => {
    setError('');
    setSuccess('');
    saveMutation.mutate(form);
  };

  return (
    <PageContainer>
      <PageHeader title={isEditing ? 'Editar Plantilla Maestro' : 'Nueva Plantilla Maestro'} />
      <Card sx={{ p: { xs: 2, md: 3 }, maxWidth: 800 }}>
      <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Stack spacing={3}>
          <TextField
            label="Nombre"
            {...register('nombre')}
            error={!!errors.nombre}
            helperText={errors.nombre?.message}
            required
            fullWidth
          />

          <TextField
            label="Descripción"
            {...register('descripcion')}
            error={!!errors.descripcion}
            helperText={errors.descripcion?.message}
            multiline
            minRows={3}
            fullWidth
          />

          <Controller
            name="metodos_pago"
            control={control}
            render={({ field }) => (
              <Autocomplete
                multiple
                options={metodosPago}
                getOptionLabel={(option) => option.nombre}
                value={metodosPago.filter(mp => field.value.includes(mp.id_metodo_pago))}
                onChange={(_, newValue) => field.onChange(newValue.map(mp => mp.id_metodo_pago))}
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
            )}
          />

          <Controller
            name="monedas"
            control={control}
            render={({ field }) => (
              <Autocomplete
                multiple
                options={monedas}
                getOptionLabel={(option) => `${option.nombre} (${option.simbolo})`}
                value={monedas.filter(m => field.value.includes(m.id_moneda))}
                onChange={(_, newValue) => field.onChange(newValue.map(m => m.id_moneda))}
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
            )}
          />

          <Controller
            name="activa"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={
                  <Switch
                    checked={field.value}
                    onChange={(e) => field.onChange(e.target.checked)}
                  />
                }
                label="Activa"
              />
            )}
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
      </Card>
    </PageContainer>
  );
};

export default PlantillaMaestroFormPage;
