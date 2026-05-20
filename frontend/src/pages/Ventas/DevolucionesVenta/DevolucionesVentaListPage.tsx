import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { devolucionVentaService } from '../../../services/ventas';
import type { DevolucionVenta } from '../../../types/ventas';
import { Alert, Box, Button, Chip, InputAdornment, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';

const DevolucionesVentaListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');

  const { data: devoluciones = [], isLoading: loading, isError } = useQuery<DevolucionVenta[]>({
    queryKey: ['/ventas/devoluciones-venta/'],
    queryFn: () => devolucionVentaService.getAll(),
  });

  const error = isError ? 'Error al cargar las devoluciones' : null;

  const procesarMutation = useMutation({
    mutationFn: (id: string) => devolucionVentaService.procesar(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/devoluciones-venta/'] });
    },
    onError: () => alert('Error al procesar la devolución'),
  });

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'PENDIENTE': return 'warning';
      case 'PROCESADA': return 'success';
      case 'RECHAZADA': return 'error';
      case 'CANCELADA': return 'default';
      default: return 'default';
    }
  };

  const filteredDevoluciones = devoluciones.filter(devolucion =>
    devolucion.numero_devolucion?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    devolucion.id_cliente?.razon_social?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    devolucion.id_cliente?.rif?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    devolucion.motivo_devolucion?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleProcesar = (id: string) => {
    procesarMutation.mutate(id);
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;
  if (error) return <PageLayout><Alert severity="error">{error}</Alert></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1">
            Devoluciones de Venta
          </Typography>
          <Button variant="contained" onClick={() => navigate('new')}>
            Nueva Devolución
          </Button>
        </Box>

        <Paper sx={{ p: 3, mb: 3 }}>
          <TextField
            fullWidth
            placeholder="Buscar por número, cliente, RIF o motivo..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }}
            sx={{ mb: 2 }}
          />
        </Paper>

        <Paper sx={{ p: 3 }}>
          {filteredDevoluciones.length > 0 ? (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Número</TableCell>
                    <TableCell>Fecha</TableCell>
                    <TableCell>Cliente</TableCell>
                    <TableCell>Motivo</TableCell>
                    <TableCell align="right">Monto</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell align="center">Acciones</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredDevoluciones.map((devolucion) => (
                    <TableRow key={devolucion.id_devolucion}>
                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {devolucion.numero_devolucion}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {new Date(devolucion.fecha_devolucion).toLocaleDateString('es-ES', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </TableCell>
                      <TableCell>
                        {devolucion.id_cliente ? (
                          <div>
                            <div style={{ fontWeight: 'bold' }}>{devolucion.id_cliente.razon_social}</div>
                            <div style={{ fontSize: '12px', color: '#6c757d' }}>{devolucion.id_cliente.rif}</div>
                          </div>
                        ) : (
                          <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                        )}
                      </TableCell>
                      <TableCell>{devolucion.motivo_devolucion}</TableCell>
                      <TableCell align="right">
                        {devolucion.monto_total?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={devolucion.estado || 'PENDIENTE'}
                          color={getEstadoColor(devolucion.estado || 'PENDIENTE')}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
                          <Button
                            variant="contained" color="secondary"
                            onClick={() => navigate(`${devolucion.id_devolucion}`)}
                          >
                            Ver
                          </Button>
                          <Button
                            variant="contained" color="secondary"
                            onClick={() => navigate(`${devolucion.id_devolucion}/edit`)}
                          >
                            Editar
                          </Button>
                          {devolucion.estado === 'PENDIENTE' && (
                            <Button
                              variant="contained"
                              onClick={() => handleProcesar(devolucion.id_devolucion)}
                            >
                              Procesar
                            </Button>
                          )}
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" color="text.secondary">
                {searchTerm ? 'No se encontraron devoluciones con los criterios de búsqueda' : 'No hay devoluciones registradas'}
              </Typography>
              {!searchTerm && (
                <Button variant="contained" onClick={() => navigate('new')} style={{ marginTop: 16 }}>
                  Crear primera devolución
                </Button>
              )}
            </Box>
          )}
        </Paper>
      </Box>
    </PageLayout>
  );
};

export default DevolucionesVentaListPage;