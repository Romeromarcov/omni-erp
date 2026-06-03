import React from 'react';
import { useNavigate } from 'react-router-dom';
import { PageContainer, PageHeader, StatusChip } from '../../../components/ui';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPlantillasMaestro, togglePlantillaMaestroActiva, type PlantillaMaestroCajasVirtuales } from '../../../services/plantillasService';
import { Alert, Box, Button, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';

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
    <PageContainer>
      <PageHeader
        title="Plantillas Maestro de Cajas Virtuales"
        actions={
          <Button variant="contained" onClick={() => navigate('/finanzas/plantillas-maestro/crear')}>
            Nueva Plantilla
          </Button>
        }
      />

      {isError && <Alert severity="error" sx={{ mb: 2 }}>Error al cargar las plantillas</Alert>}

      <Paper variant="outlined">
        {isLoading ? (
          <Box sx={{ p: 3 }}>Cargando...</Box>
        ) : plantillas.length === 0 ? (
          <Box sx={{ p: 3 }}>No hay plantillas configuradas</Box>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Nombre</TableCell>
                  <TableCell>Descripción</TableCell>
                  <TableCell align="center">Métodos de Pago</TableCell>
                  <TableCell align="center">Monedas</TableCell>
                  <TableCell align="center">Estado</TableCell>
                  <TableCell>Fecha Creación</TableCell>
                  <TableCell align="center">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {plantillas.map((plantilla) => (
                  <TableRow key={plantilla.id_plantilla} hover>
                    <TableCell>{plantilla.nombre}</TableCell>
                    <TableCell>{plantilla.descripcion || '-'}</TableCell>
                    <TableCell align="center">{plantilla.metodos_pago?.length || 0} métodos</TableCell>
                    <TableCell align="center">{plantilla.monedas?.length || 0} monedas</TableCell>
                    <TableCell align="center">
                      <StatusChip value={plantilla.activa} label={plantilla.activa ? 'Activa' : 'Inactiva'} />
                    </TableCell>
                    <TableCell>{new Date(plantilla.fecha_creacion).toLocaleDateString()}</TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
                        <Button size="small" variant="outlined" onClick={() => navigate(`/finanzas/plantillas-maestro/${plantilla.id_plantilla}`)}>
                          Editar
                        </Button>
                        <Button size="small" variant="outlined" onClick={() => handleToggleActiva(plantilla.id_plantilla, plantilla.activa)}>
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
    </PageContainer>
  );
};

export default PlantillasMaestroListPage;
