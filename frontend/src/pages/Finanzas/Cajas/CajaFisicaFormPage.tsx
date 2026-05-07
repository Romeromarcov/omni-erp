import React, { useState, useEffect, useCallback } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import { cajasFisicasService } from '../../../services/cajasFisicasService';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { Alert, Box, Button, FormControlLabel, MenuItem, Paper, Switch, TextField, Typography } from '@mui/material';

interface Moneda {
  id_moneda: string;
  nombre: string;
  simbolo: string;
}

const CajaFisicaFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id, action } = useParams<{ id: string; action: string }>();
  const isEditing = action === 'editar' && !!id;

  const [form, setForm] = useState({
    nombre: '',
    tipo_caja: 'REGISTRADORA',
    descripcion: '',
    sucursal: '',
    moneda: '',
    // Campos del dispositivo
    nombre_dispositivo: '',
    tipo_dispositivo: 'PC',
    identificador_dispositivo: '',
    descripcion_dispositivo: '',
    requiere_sesion_activa: true,
    activa: true,
  });

  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [tipoCajaChoices, setTipoCajaChoices] = useState<Array<{ value: string; display: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [monedasData, tipoChoices] = await Promise.all([
        fetchMonedasEmpresaActivas(idEmpresa),
        cajasFisicasService.getTipoCajaChoices()
      ]);
      setMonedas(Array.isArray(monedasData) ? monedasData : []);
      setTipoCajaChoices(tipoChoices);

      if (isEditing && id) {
        const cajaData = await cajasFisicasService.getCajaFisica(id);
        setForm({
          nombre: cajaData.nombre,
          tipo_caja: cajaData.tipo_caja,
          descripcion: cajaData.descripcion || '',
          sucursal: cajaData.sucursal || '',
          moneda: cajaData.moneda || '',
          // Campos del dispositivo
          nombre_dispositivo: cajaData.nombre_dispositivo || '',
          tipo_dispositivo: cajaData.tipo_dispositivo || 'PC',
          identificador_dispositivo: cajaData.identificador_dispositivo || '',
          descripcion_dispositivo: cajaData.descripcion_dispositivo || '',
          requiere_sesion_activa: cajaData.requiere_sesion_activa,
          activa: cajaData.activa,
        });
      }
    } catch (err) {
      setError('Error al cargar los datos');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [idEmpresa, isEditing, id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.nombre.trim()) {
      setError('El nombre es obligatorio');
      return;
    }

    if (!form.moneda) {
      setError('Debe seleccionar una moneda');
      return;
    }

    try {
      setSaving(true);
      setError('');
      setSuccess('');

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
        await cajasFisicasService.updateCajaFisica(id, dataToSend);
        setSuccess('Caja física actualizada correctamente');
      } else {
        await cajasFisicasService.createCajaFisica(dataToSend);
        setSuccess('Caja física creada correctamente');
      }

      // Redirigir después de un breve delay para mostrar el mensaje de éxito
      setTimeout(() => {
        navigate('/finanzas/cajas-fisicas');
      }, 1500);

    } catch (err) {
      setError(isEditing ? 'Error al actualizar la caja física' : 'Error al crear la caja física');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field: string, value: string | boolean) => {
    setForm(prev => ({
      ...prev,
      [field]: value
    }));
  };

  if (loading) {
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
                      {moneda.nombre} ({moneda.simbolo})
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
              disabled={saving}
            >
              {saving ? 'Guardando...' : (isEditing ? 'Actualizar' : 'Crear')}
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