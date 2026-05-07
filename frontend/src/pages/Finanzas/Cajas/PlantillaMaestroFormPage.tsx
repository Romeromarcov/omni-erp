import React, { useState, useEffect, useCallback } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import { createPlantillaMaestro, updatePlantillaMaestro, getPlantillasMaestro } from '../../../services/plantillasService';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { fetchMonedasEmpresaActivas } from '../../../services/monedasEmpresaActiva';
import { Alert, Autocomplete, Box, Button, Chip, FormControlLabel, Paper, Switch, TextField, Typography } from '@mui/material';

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

  const [form, setForm] = useState({
    nombre: '',
    descripcion: '',
    metodos_pago: [] as string[],
    monedas: [] as string[],
    activa: true,
  });

  const [metodosPago, setMetodosPago] = useState<MetodoPago[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const loadData = useCallback(async () => {
    try {
      const [metodos, monedasData] = await Promise.all([
        fetchMetodosPagoEmpresaActivos(idEmpresa),
        fetchMonedasEmpresaActivas(idEmpresa)
      ]);
      setMetodosPago(metodos as MetodoPago[]);
      setMonedas(monedasData as Moneda[]);
    } catch (err) {
      console.error('Error cargando datos:', err);
    }
  }, [idEmpresa]);

  const loadPlantilla = useCallback(async (plantillaId: string) => {
    try {
      setLoading(true);
      const plantillas = await getPlantillasMaestro(idEmpresa);
      const plantilla = plantillas.find(p => p.id_plantilla === plantillaId);
      if (plantilla) {
        setForm({
          nombre: plantilla.nombre,
          descripcion: plantilla.descripcion || '',
          metodos_pago: plantilla.metodos_pago,
          monedas: plantilla.monedas,
          activa: plantilla.activa,
        });
      }
    } catch (err) {
      setError('Error al cargar la plantilla');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [idEmpresa]);

  useEffect(() => {
    loadData();
    if (isEditing && id) {
      loadPlantilla(id);
    }
  }, [id, isEditing, loadData, loadPlantilla]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.nombre.trim()) {
      setError('El nombre es obligatorio');
      return;
    }

    try {
      setSaving(true);
      setError('');
      setSuccess('');

      const data = {
        ...form,
        id_empresa: idEmpresa,
      };

      if (isEditing && id) {
        await updatePlantillaMaestro(id, data);
        setSuccess('Plantilla actualizada exitosamente');
      } else {
        await createPlantillaMaestro(data);
        setSuccess('Plantilla creada exitosamente');
      }

      setTimeout(() => {
        navigate('/finanzas/plantillas-maestro');
      }, 1500);
    } catch (err) {
      setError('Error al guardar la plantilla');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field: string, value: string | boolean | string[]) => {
    setForm(prev => ({ ...prev, [field]: value }));
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
          {isEditing ? 'Editar Plantilla Maestro' : 'Nueva Plantilla Maestro'}
        </Typography>
      </Box>

      <Paper sx={{ p: 3, maxWidth: 800, mx: 'auto' }}>
        <form onSubmit={handleSubmit}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
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
              rows={3}
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

            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
              <Button
                type="button"
                variant="outlined"
                onClick={() => navigate('/finanzas/plantillas-maestro')}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? 'Guardando...' : (isEditing ? 'Actualizar' : 'Crear')}
              </Button>
            </Box>
          </Box>
        </form>
      </Paper>
    </PageLayout>
  );
};

export default PlantillaMaestroFormPage;