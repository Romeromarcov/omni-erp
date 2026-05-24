import React from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPlantillasMaestro, togglePlantillaMaestroActiva, type PlantillaMaestroCajasVirtuales } from '../../../services/plantillasService';
import { Alert, Box, Button, Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';

const PlantillasMaestroListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const { data: plantillas = [], isLoading, isError } = useQuery<PlantillaMaestroCajasVirtuales[]>({
    queryKey: ['/finanzas/plantillas-maestro-cajas/', idEmpresa],
    queryFn: () => getPlantillasMaestro(idEmpresa),
    enabled: !!idEmpresa,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, activa }: { id: string; activa: boolean }) => togglePlantillaMaestroActiva(id, activa),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/plantillas-maestro-cajas/', idEmpresa] });
    },
    onError: (err) => {
      console.error('Error al cambiar el estado de la plantilla', err);
    },
  });

  const handleToggleActiva = (id: string, actualmenteActiva: boolean) => {
    toggleMutation.mutate({ id, activa: !actualmenteActiva });
  };

  return (
    <PageLayout>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4">Plantillas Maestro de Cajas Virtuales</Typography>
        <Button onClick={() => navigate('/finanzas/plantillas-maestro/crear')}>
          Nueva Plantilla
        </Button>
      </Box>

      {isError && <Alert severity="error" sx={{ mb: 2 }}>Error al cargar las plantillas</Alert>}

      <Paper sx={{ p: 2 }}>
        {isLoading ? (
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
