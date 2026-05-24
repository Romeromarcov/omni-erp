import React, { useState, useEffect } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cajasFisicasService } from '../../../services/cajasFisicasService';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import type { MonedaEmpresaActiva } from '../../../services/monedasEmpresaActiva';
import { Alert, Box, Button, FormControlLabel, MenuItem, Paper, Switch, TextField, Typography } from '@mui/material';

type TipoCajaChoice = { value: string; display: string };

const CajaFisicaFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id, action } = useParams<{ id: string; action: string }>();
  const isEditing = action === 'editar' && !!id;
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
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
  });

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const { data: monedas = [] } = useQuery<MonedaEmpresaActiva[]>({
    queryKey: ['/finanzas/monedas-empresa-activas/', idEmpresa],
    queryFn: () => fetchMonedasEmpresaActivas(idEmpresa),
    enabled: !!idEmpresa,
  });

  const { data: tipoCajaChoices = [] } = useQuery<TipoCajaChoice[]>({
    queryKey: ['/finanzas/cajas-fisicas/tipo-caja-choices'],
    queryFn: () => cajasFisicasService.getTipoCajaChoices(),
  });

  const { data: cajaData, isLoading } = useQuery({
    queryKey: ['/finanzas/cajas-fisicas/', id],
    queryFn: () => cajasFisicasService.getCajaFisica(id!),
    enabled: isEditing && !!id,
  });

  useEffect(() => {
    if (cajaData) {
      setForm({
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
  }, [cajaData]);

  const saveMutation = useMutation({
    mutationFn: () => {
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
      queryClient.invalidateQueries({ queryKey: ['/finanzas/cajas-fisicas/'] });
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.nombre.trim()) {
      setError('El nombre es obligatorio');
      return;
    }
    if (!form.moneda) {
      setError('Debe seleccionar una moneda');
      return;
    }
    setError('');
    setSuccess('');
    saveMutation.mutate();
  };

  const handleChange = (field: string, value: string | boolean) => {
    setForm(prev => ({
      ...prev,
      [field]: value
    }));
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
        <form onSubmit={handleSubmit}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  label="Nombre"
                  value={form.nombre}
                  onChange={(e) => handleChange('nombre', e.target.value)}
                  required
                />
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  select
                  label="Tipo de Caja"
                  value={form.tipo_caja}
                  onChange={(e) => handleChange('tipo_caja', e.target.value)}
                >
                  {tipoCajaChoices.map((choice) => (
                    <MenuItem key={choice.value} value={choice.value}>
                      {choice.display}
                    </MenuItem>
                  ))}
                </TextField>
              </Box>
            </Box>

            <TextField
              fullWidth
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => handleChange('descripcion', e.target.value)}
              multiline
              rows={2}
            />

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  select
                  label="Moneda"
                  value={form.moneda}
                  onChange={(e) => handleChange('moneda', e.target.value)}
                  required
                >
                  {monedas.map((moneda) => (
                    <MenuItem key={moneda.id_moneda} value={moneda.id_moneda}>
                      {moneda.nombre} ({moneda.codigo_iso})
                    </MenuItem>
                  ))}
                </TextField>
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  label="Nombre del Dispositivo"
                  value={form.nombre_dispositivo}
                  onChange={(e) => handleChange('nombre_dispositivo', e.target.value)}
                  placeholder="Nombre descriptivo del dispositivo"
                />
              </Box>
            </Box>

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  select
                  label="Tipo de Dispositivo"
                  value={form.tipo_dispositivo}
                  onChange={(e) => handleChange('tipo_dispositivo', e.target.value)}
                >
                  <MenuItem value="PC">Computadora Personal</MenuItem>
                  <MenuItem value="TABLET">Tablet</MenuItem>
                  <MenuItem value="MOVIL">Teléfono Móvil</MenuItem>
                  <MenuItem value="TERMINAL">Terminal de Pago</MenuItem>
                  <MenuItem value="OTRO">Otro</MenuItem>
                </TextField>
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <TextField
                  fullWidth
                  label="Identificador del Dispositivo"
                  value={form.identificador_dispositivo}
                  onChange={(e) => handleChange('identificador_dispositivo', e.target.value)}
                  placeholder="MAC address, serial number, UUID, etc."
                />
              </Box>
            </Box>

            <TextField
              fullWidth
              label="Descripción del Dispositivo"
              value={form.descripcion_dispositivo}
              onChange={(e) => handleChange('descripcion_dispositivo', e.target.value)}
              placeholder="Descripción adicional del dispositivo"
              multiline
              rows={2}
            />

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 300px' }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={form.requiere_sesion_activa}
                      onChange={(e) => handleChange('requiere_sesion_activa', e.target.checked)}
                    />
                  }
                  label="Requiere sesión activa"
                />
              </Box>
              <Box sx={{ flex: '1 1 300px' }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={form.activa}
                      onChange={(e) => handleChange('activa', e.target.checked)}
                    />
                  }
                  label="Activa"
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
