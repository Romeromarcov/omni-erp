import React, { useState, useEffect } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { cajasFisicasService } from '../../../services/cajasFisicasService';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import type { MonedaEmpresaActiva } from '../../../services/monedasEmpresaActiva';
import { cajaFisicaSchema, type CajaFisicaInput } from '../../../schemas/finanzas.schemas';
import { finanzasKeys } from '../../../lib/queryKeys';
import { Alert, Box, Button, FormControlLabel, MenuItem, Paper, Switch, TextField, Typography } from '@mui/material';

type TipoCajaChoice = { value: string; display: string };

const defaultValues: CajaFisicaInput = {
  nombre: '',
  tipo_caja: 'REGISTRADORA',
  descripcion: '',
  sucursal: '',
  moneda: '',
  nombre_dispositivo: '',
  tipo_dispositivo: 'PC',
  identificador_dispositivo: '',
  descripcion_dispositivo: '',
  requiere_sesion_activa: true,
  activa: true,
};

const CajaFisicaFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id, action } = useParams<{ id: string; action: string }>();
  const isEditing = action === 'editar' && !!id;
  const queryClient = useQueryClient();

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<CajaFisicaInput>({
    resolver: zodResolver(cajaFisicaSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const { data: monedas = [] } = useQuery<MonedaEmpresaActiva[]>({
    queryKey: finanzasKeys.monedas.empresaActivas(idEmpresa),
    queryFn: () => fetchMonedasEmpresaActivas(idEmpresa),
    enabled: !!idEmpresa,
  });

  const { data: tipoCajaChoices = [] } = useQuery<TipoCajaChoice[]>({
    queryKey: finanzasKeys.cajasFisicas.tipoChoices(),
    queryFn: () => cajasFisicasService.getTipoCajaChoices(),
  });

  const { data: cajaData, isLoading } = useQuery({
    queryKey: finanzasKeys.cajasFisicas.detail(id!),
    queryFn: () => cajasFisicasService.getCajaFisica(id!),
    enabled: isEditing && !!id,
  });

  // FE-HIGH-6: rehidratar sin pisar ediciones en curso.
  useEffect(() => {
    if (cajaData && !isDirty) {
      reset({
        nombre: cajaData.nombre,
        tipo_caja: cajaData.tipo_caja,
        descripcion: cajaData.descripcion || '',
        sucursal: cajaData.sucursal || '',
        moneda: cajaData.moneda || '',
        nombre_dispositivo: cajaData.nombre_dispositivo || '',
        tipo_dispositivo: cajaData.tipo_dispositivo || 'PC',
        identificador_dispositivo: cajaData.identificador_dispositivo || '',
        descripcion_dispositivo: cajaData.descripcion_dispositivo || '',
        requiere_sesion_activa: cajaData.requiere_sesion_activa,
        activa: cajaData.activa,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cajaData]);

  const saveMutation = useMutation({
    mutationFn: (form: CajaFisicaInput) => {
      const dataToSend = {
        ...form,
        empresa: idEmpresa,
        saldo_inicial: 0,
        saldo_actual: 0,
        esta_abierta: false,
        estado_sesion_display: 'Cerrada',
        nombre_usuario_actual: undefined,
      };
      if (isEditing && id) {
        return cajasFisicasService.updateCajaFisica(id, dataToSend);
      }
      return cajasFisicasService.createCajaFisica(dataToSend as Parameters<typeof cajasFisicasService.createCajaFisica>[0]);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: finanzasKeys.cajasFisicas.all() });
      setSuccess(isEditing ? 'Caja física actualizada correctamente' : 'Caja física creada correctamente');
      setTimeout(() => {
        navigate('/finanzas/cajas-fisicas');
      }, 1500);
    },
    onError: (err) => {
      setError(isEditing ? 'Error al actualizar la caja física' : 'Error al crear la caja física');
      console.error(err);
    },
  });

  const onSubmit = (form: CajaFisicaInput) => {
    setError('');
    setSuccess('');
    saveMutation.mutate(form);
  };

  if (isLoading) {
    return (
      <PageLayout>
        <Typography>Cargando...</Typography>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <Box sx={{ mb: 2 }}>
        <Typography variant="h4">
          {isEditing ? 'Editar Caja Física' : 'Nueva Caja Física'}
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}

      <Paper sx={{ p: 3 }}>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  label="Nombre"
                  {...register('nombre')}
                  error={!!errors.nombre}
                  helperText={errors.nombre?.message}
                  required
                />
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <Controller
                  name="tipo_caja"
                  control={control}
                  render={({ field }) => (
                    <TextField
                      fullWidth
                      select
                      label="Tipo de Caja"
                      {...field}
                      error={!!errors.tipo_caja}
                      helperText={errors.tipo_caja?.message}
                    >
                      {tipoCajaChoices.map((choice) => (
                        <MenuItem key={choice.value} value={choice.value}>
                          {choice.display}
                        </MenuItem>
                      ))}
                    </TextField>
                  )}
                />
              </Box>
            </Box>

            <TextField
              fullWidth
              label="Descripción"
              {...register('descripcion')}
              error={!!errors.descripcion}
              helperText={errors.descripcion?.message}
              multiline
              rows={2}
            />

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <Controller
                  name="moneda"
                  control={control}
                  render={({ field }) => (
                    <TextField
                      fullWidth
                      select
                      label="Moneda"
                      {...field}
                      error={!!errors.moneda}
                      helperText={errors.moneda?.message}
                      required
                    >
                      {monedas.map((moneda) => (
                        <MenuItem key={moneda.id_moneda} value={moneda.id_moneda}>
                          {moneda.nombre} ({moneda.codigo_iso})
                        </MenuItem>
                      ))}
                    </TextField>
                  )}
                />
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  label="Nombre del Dispositivo"
                  {...register('nombre_dispositivo')}
                  error={!!errors.nombre_dispositivo}
                  helperText={errors.nombre_dispositivo?.message}
                  placeholder="Nombre descriptivo del dispositivo"
                />
              </Box>
            </Box>

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <Controller
                  name="tipo_dispositivo"
                  control={control}
                  render={({ field }) => (
                    <TextField
                      fullWidth
                      select
                      label="Tipo de Dispositivo"
                      {...field}
                      error={!!errors.tipo_dispositivo}
                      helperText={errors.tipo_dispositivo?.message}
                    >
                      <MenuItem value="PC">Computadora Personal</MenuItem>
                      <MenuItem value="TABLET">Tablet</MenuItem>
                      <MenuItem value="MOVIL">Teléfono Móvil</MenuItem>
                      <MenuItem value="TERMINAL">Terminal de Pago</MenuItem>
                      <MenuItem value="OTRO">Otro</MenuItem>
                    </TextField>
                  )}
                />
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  label="Identificador del Dispositivo"
                  {...register('identificador_dispositivo')}
                  error={!!errors.identificador_dispositivo}
                  helperText={errors.identificador_dispositivo?.message}
                  placeholder="MAC address, serial number, UUID, etc."
                />
              </Box>
            </Box>

            <TextField
              fullWidth
              label="Descripción del Dispositivo"
              {...register('descripcion_dispositivo')}
              error={!!errors.descripcion_dispositivo}
              helperText={errors.descripcion_dispositivo?.message}
              placeholder="Descripción adicional del dispositivo"
              multiline
              rows={2}
            />

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <Controller
                  name="requiere_sesion_activa"
                  control={control}
                  render={({ field }) => (
                    <FormControlLabel
                      control={
                        <Switch
                          checked={field.value}
                          onChange={(e) => field.onChange(e.target.checked)}
                        />
                      }
                      label="Requiere sesión activa"
                    />
                  )}
                />
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
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
              </Box>
            </Box>
          </Box>

          <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
            <Button
              type="submit"
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Guardando...' : (isEditing ? 'Actualizar' : 'Crear')}
            </Button>
            <Button
              variant="outlined"
              onClick={() => navigate('/finanzas/cajas-fisicas')}
            >
              Cancelar
            </Button>
          </Box>
        </form>
      </Paper>
    </PageLayout>
  );
};

export default CajaFisicaFormPage;
