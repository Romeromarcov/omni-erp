import React, { useState, useEffect, useCallback } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { cajasFisicasService, type CajaFisica, type CajaVirtual, type Datafono } from '../../../services/cajasFisicasService';
import { Alert, Box, Button, Chip, IconButton, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import VisibilityIcon from '@mui/icons-material/Visibility';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';

const CajasFisicasListPage: React.FC = () => {
  const navigate = useNavigate();
  const [cajasFisicas, setCajasFisicas] = useState<CajaFisica[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const loadCajasFisicas = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const response = await cajasFisicasService.getCajasFisicas({
        empresa: idEmpresa,
        page_size: 100 // Cargar todas por ahora
      });
      
      setCajasFisicas(response.results);
    } catch (err) {
      setError('Error al cargar las cajas físicas');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [idEmpresa]);

  useEffect(() => {
    if (idEmpresa) {
      loadCajasFisicas();
    }
  }, [idEmpresa, loadCajasFisicas]);

  const handleDelete = async (id: string) => {
    if (!window.confirm('¿Está seguro de que desea eliminar esta caja física?')) {
      return;
    }

    try {
      await cajasFisicasService.deleteCajaFisica(id);
      await loadCajasFisicas(); // Recargar la lista
    } catch (err) {
      setError('Error al eliminar la caja física');
      console.error(err);
    }
  };

  const handleAbrirSesion = async (id: string, nombre: string) => {
    if (!window.confirm(`¿Está seguro de que desea abrir la sesión de la caja "${nombre}"?`)) {
      return;
    }

    try {
      await cajasFisicasService.abrirSesion(id);
      await loadCajasFisicas(); // Recargar la lista
    } catch (err) {
      setError('Error al abrir la sesión de caja');
      console.error(err);
    }
  };

  const handleCerrarSesion = async (id: string) => {
    const notas = prompt('Notas para el cierre de sesión (opcional):');
    if (notas === null) return; // Usuario canceló

    try {
      await cajasFisicasService.cerrarSesion(id, notas);
      await loadCajasFisicas(); // Recargar la lista
    } catch (err) {
      setError('Error al cerrar la sesión de caja');
      console.error(err);
    }
  };

  return (
    <PageLayout>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4">Cajas Físicas</Typography>
        <Button onClick={() => navigate('/finanzas/cajas-fisicas/crear')}>
          Nueva Caja Física
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Nombre</TableCell>
                <TableCell>Tipo</TableCell>
                <TableCell>Sucursal</TableCell>
                <TableCell>Identificador Dispositivo</TableCell>
                <TableCell>Estado</TableCell>
                <TableCell>Estado de Sesión</TableCell>
                <TableCell>Cajas Virtuales</TableCell>
                <TableCell>Datafonos</TableCell>
                <TableCell align="center">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} align="center">
                    Cargando...
                  </TableCell>
                </TableRow>
              ) : cajasFisicas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} align="center">
                    No hay cajas físicas registradas
                  </TableCell>
                </TableRow>
              ) : (
                cajasFisicas.map((caja) => (
                    <TableRow key={caja.id_caja_fisica} hover>
                      <TableCell>{caja.nombre}</TableCell>
                      <TableCell>{caja.tipo_caja_display}</TableCell>
                      <TableCell>{caja.sucursal_nombre || '-'}</TableCell>
                      <TableCell>
                        {caja.identificador_dispositivo ? (
                          <Tooltip title={caja.identificador_dispositivo}>
                            <span>{caja.identificador_dispositivo.substring(0, 10)}...</span>
                          </Tooltip>
                        ) : (
                          '-'
                        )}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={caja.activa ? 'Activa' : 'Inactiva'}
                          color={caja.activa ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={caja.estado_sesion_display || 'Cerrada'}
                          color={caja.esta_abierta ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        {caja.cajas_virtuales && caja.cajas_virtuales.length > 0 ? (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {caja.cajas_virtuales.map((cv: CajaVirtual) => (
                              <Chip
                                key={cv.id_caja}
                                label={`${cv.nombre} (${cv.moneda_codigo_iso})`}
                                size="small"
                                variant="outlined"
                              />
                            ))}
                          </Box>
                        ) : (
                          'Ninguna'
                        )}
                      </TableCell>
                      <TableCell>
                        {caja.datafonos && caja.datafonos.length > 0 ? (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {caja.datafonos.map((datafono: Datafono) => (
                              <Chip
                                key={datafono.id_datafono}
                                label={`${datafono.nombre} (${datafono.serial})`}
                                size="small"
                                variant="outlined"
                              />
                            ))}
                          </Box>
                        ) : (
                          'Ninguno'
                        )}
                      </TableCell>
                      <TableCell align="center">
                        <Tooltip title="Ver detalle">
                          <IconButton
                            onClick={() => navigate(`/finanzas/cajas-fisicas/${caja.id_caja_fisica}`)}
                            color="primary"
                          >
                            <VisibilityIcon />
                          </IconButton>
                        </Tooltip>
                        {caja.esta_abierta ? (
                          <Tooltip title="Cerrar sesión">
                            <IconButton
                              onClick={() => handleCerrarSesion(caja.id_caja_fisica)}
                              color="warning"
                            >
                              <StopIcon />
                            </IconButton>
                          </Tooltip>
                        ) : (
                          <Tooltip title="Abrir sesión">
                            <IconButton
                              onClick={() => handleAbrirSesion(caja.id_caja_fisica, caja.nombre)}
                              color="success"
                            >
                              <PlayArrowIcon />
                            </IconButton>
                          </Tooltip>
                        )}
                        <Tooltip title="Editar">
                          <IconButton
                            onClick={() => navigate(`/finanzas/cajas-fisicas/${caja.id_caja_fisica}/editar`)}
                            color="primary"
                          >
                            <EditIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Eliminar">
                          <IconButton
                            onClick={() => handleDelete(caja.id_caja_fisica)}
                            color="error"
                          >
                            <DeleteIcon />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </PageLayout>
  );
};

export default CajasFisicasListPage;