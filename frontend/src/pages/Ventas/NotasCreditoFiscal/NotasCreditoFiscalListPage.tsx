import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { notaCreditoFiscalService } from '../../../services/ventas';
import type { NotaCreditoFiscal } from '../../../types/ventas';
import { Alert, Box, Button, Chip, InputAdornment, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';

const NotasCreditoFiscalListPage: React.FC = () => {
  const navigate = useNavigate();
  const [notasCredito, setNotasCredito] = useState<NotaCreditoFiscal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    loadNotasCredito();
  }, []);

  const loadNotasCredito = async () => {
    setLoading(true);
    try {
      const data = await notaCreditoFiscalService.getAll();
      setNotasCredito(data);
    } catch (err) {
      setError('Error al cargar las notas de crédito fiscal');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'PENDIENTE': return 'warning';
      case 'APLICADA': return 'success';
      case 'ANULADA': return 'error';
      default: return 'default';
    }
  };

  const filteredNotas = notasCredito.filter(nota =>
    nota.numero_nota_credito?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    nota.id_cliente?.razon_social?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    nota.id_cliente?.rif?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAplicar = async (id: string) => {
    try {
      await notaCreditoFiscalService.aplicar(id);
      await loadNotasCredito(); // Recargar la lista
    } catch (error) {
      console.error('Error aplicando nota de crédito fiscal:', error);
      alert('Error al aplicar la nota de crédito fiscal');
    }
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;
  if (error) return <PageLayout><Alert severity="error">{error}</Alert></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1">
            Notas de Crédito Fiscal
          </Typography>
          <Button variant="contained" onClick={() => navigate('new')}>
            Nueva Nota de Crédito Fiscal
          </Button>
        </Box>

        <Paper sx={{ p: 3, mb: 3 }}>
          <TextField
            fullWidth
            placeholder="Buscar por número, cliente o RIF..."
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
          {filteredNotas.length > 0 ? (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Número</TableCell>
                    <TableCell>Fecha</TableCell>
                    <TableCell>Cliente</TableCell>
                    <TableCell align="right">Monto Total</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell align="center">Acciones</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredNotas.map((nota) => (
                    <TableRow key={nota.id_nota_credito_fiscal}>
                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {nota.numero_nota_credito}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {new Date(nota.fecha_emision).toLocaleDateString('es-ES', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </TableCell>
                      <TableCell>
                        {nota.id_cliente ? (
                          <div>
                            <div style={{ fontWeight: 'bold' }}>{nota.id_cliente.razon_social}</div>
                            <div style={{ fontSize: '12px', color: '#6c757d' }}>{nota.id_cliente.rif}</div>
                          </div>
                        ) : (
                          <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        {nota.monto_total?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={nota.estado || 'PENDIENTE'}
                          color={getEstadoColor(nota.estado || 'PENDIENTE')}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
                          <Button
                            variant="contained" color="secondary"
                            onClick={() => navigate(`${nota.id_nota_credito_fiscal}`)}
                          >
                            Ver
                          </Button>
                          <Button
                            variant="contained" color="secondary"
                            onClick={() => navigate(`${nota.id_nota_credito_fiscal}/edit`)}
                          >
                            Editar
                          </Button>
                          {nota.estado !== 'APLICADA' && (
                            <Button
                              variant="contained"
                              onClick={() => handleAplicar(nota.id_nota_credito_fiscal)}
                            >
                              Aplicar
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
                {searchTerm ? 'No se encontraron notas de crédito fiscal con los criterios de búsqueda' : 'No hay notas de crédito fiscal registradas'}
              </Typography>
              {!searchTerm && (
                <Button variant="contained" onClick={() => navigate('new')} style={{ marginTop: 16 }}>
                  Crear primera nota de crédito fiscal
                </Button>
              )}
            </Box>
          )}
        </Paper>
      </Box>
    </PageLayout>
  );
};

export default NotasCreditoFiscalListPage;