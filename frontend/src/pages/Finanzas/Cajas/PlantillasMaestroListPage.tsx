import React, { useState, useEffect, useCallback } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { getPlantillasMaestro, togglePlantillaMaestroActiva, type PlantillaMaestroCajasVirtuales } from '../../../services/plantillasService';
import { Alert, Box, Button, Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';

const PlantillasMaestroListPage: React.FC = () => {
  const navigate = useNavigate();
  const [plantillas, setPlantillas] = useState<PlantillaMaestroCajasVirtuales[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const loadPlantillas = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getPlantillasMaestro(idEmpresa);
      setPlantillas(data);
    } catch (err) {
      setError('Error al cargar las plantillas');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [idEmpresa]);

  useEffect(() => {
    if (idEmpresa) {
      loadPlantillas();
    }
  }, [idEmpresa, loadPlantillas]);

  const handleToggleActiva = async (id: string, actualmenteActiva: boolean) => {
    try {
      await togglePlantillaMaestroActiva(id, !actualmenteActiva);
      await loadPlantillas(); // Recargar la lista
    } catch (err) {
      setError('Error al cambiar el estado de la plantilla');
      console.error(err);
    }
  };

  return (
    <PageLayout>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4">Plantillas Maestro de Cajas Virtuales</Typography>
        <Button onClick={() => navigate('/finanzas/plantillas-maestro/crear')}>
          Nueva Plantilla
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ p: 2 }}>
        {loading ? (
          <Typography>Cargando...</Typography>
        ) : plantillas.length === 0 ? (
          <Typography>No hay plantillas configuradas</Typography>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Nombre</TableCell>
                  <TableCell>Descripción</TableCell>
                  <TableCell>Métodos de Pago</TableCell>
                  <TableCell>Monedas</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Fecha Creación</TableCell>
                  <TableCell>Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {plantillas.map((plantilla) => (
                  <TableRow key={plantilla.id_plantilla}>
                    <TableCell>{plantilla.nombre}</TableCell>
                    <TableCell>{plantilla.descripcion || '-'}</TableCell>
                    <TableCell>{plantilla.metodos_pago?.length || 0} métodos</TableCell>
                    <TableCell>{plantilla.monedas?.length || 0} monedas</TableCell>
                    <TableCell>
                      <Chip
                        label={plantilla.activa ? 'Activa' : 'Inactiva'}
                        color={plantilla.activa ? 'success' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{new Date(plantilla.fecha_creacion).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Button
                          variant="outlined"
                          onClick={() => navigate(`/finanzas/plantillas-maestro/${plantilla.id_plantilla}`)}
                        >
                          Editar
                        </Button>
                        <Button
                          variant="outlined"
                          onClick={() => handleToggleActiva(plantilla.id_plantilla, plantilla.activa)}
                        >
                          {plantilla.activa ? 'Desactivar' : 'Activar'}
                        </Button>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </PageLayout>
  );
};

export default PlantillasMaestroListPage;