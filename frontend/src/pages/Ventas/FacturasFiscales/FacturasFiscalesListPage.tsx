import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { facturaFiscalService } from '../../../services/ventas';
import type { FacturaFiscal } from '../../../types/ventas';
import { Alert, Box, Button, Chip, IconButton, Menu, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';

const FacturasFiscalesListPage: React.FC = () => {
  const navigate = useNavigate();
  const [facturas, setFacturas] = useState<FacturaFiscal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [selectedFactura, setSelectedFactura] = useState<FacturaFiscal | null>(null);

  useEffect(() => {
    // Verificar si el usuario está autenticado antes de cargar datos
    const token = localStorage.getItem('token');
    if (!token) {
      setError('Usuario no autenticado. Redirigiendo al login...');
      window.location.href = '/login';
      return;
    }
    loadFacturas();
  }, []);

  const loadFacturas = async () => {
    setLoading(true);
    try {
      const data = await facturaFiscalService.getAll();
      setFacturas(data);
    } catch (err) {
      setError('Error al cargar las facturas fiscales');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'BORRADOR': return 'default';
      case 'EMITIDA': return 'primary';
      case 'PAGADA': return 'success';
      case 'ANULADA': return 'error';
      default: return 'default';
    }
  };

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, factura: FacturaFiscal) => {
    setAnchorEl(event.currentTarget);
    setSelectedFactura(factura);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
    setSelectedFactura(null);
  };

  const handleView = () => {
    if (selectedFactura) {
      navigate(`/ventas/facturas-fiscales/${selectedFactura.id_factura}`);
    }
    handleMenuClose();
  };

  const handleEdit = () => {
    if (selectedFactura) {
      navigate(`/ventas/facturas-fiscales/${selectedFactura.id_factura}/edit`);
    }
    handleMenuClose();
  };

  const handleDelete = async () => {
    if (selectedFactura && window.confirm('¿Está seguro de que desea eliminar esta factura fiscal?')) {
      try {
        await facturaFiscalService.delete(selectedFactura.id_factura);
        await loadFacturas();
      } catch (error) {
        console.error('Error eliminando factura fiscal:', error);
        alert('Error al eliminar la factura fiscal');
      }
    }
    handleMenuClose();
  };

  const handleCrearNotaCredito = async () => {
    if (selectedFactura) {
      try {
        await facturaFiscalService.generarNotaCredito(selectedFactura.id_factura, 'DEVOLUCION', {});
        await loadFacturas();
      } catch (error) {
        console.error('Error creando nota de crédito:', error);
        alert('Error al crear la nota de crédito');
      }
    }
    handleMenuClose();
  };

  if (loading) {
    return (
      <PageLayout>
        <div>Cargando facturas fiscales...</div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout>
        <Alert severity="error">{error}</Alert>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4" component="h1">
          Facturas Fiscales
        </Typography>
        <Button variant="contained" onClick={() => navigate('/ventas/facturas-fiscales/new')}>
          Nueva Factura Fiscal
        </Button>
      </Box>

      <Paper sx={{ p: 3 }}>
        {facturas.length > 0 ? (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Número</TableCell>
                  <TableCell>Fecha</TableCell>
                  <TableCell>Cliente</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell align="right">Total</TableCell>
                  <TableCell>Origen</TableCell>
                  <TableCell align="center">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {facturas.map((factura) => (
                  <TableRow key={factura.id_factura} hover>
                    <TableCell>{factura.numero_factura}</TableCell>
                    <TableCell>{new Date(factura.fecha_emision).toLocaleDateString()}</TableCell>
                    <TableCell>
                      {factura.id_cliente ? (
                        <div>
                          <div style={{ fontWeight: 'bold' }}>{factura.id_cliente.nombre}</div>
                          <div style={{ fontSize: '12px', color: '#6c757d' }}>
                            {factura.id_cliente.razon_social} - {factura.id_cliente.rif}
                          </div>
                        </div>
                      ) : (
                        <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={factura.estado}
                        color={getEstadoColor(factura.estado)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {factura.detalles?.reduce((total, detalle) => total + detalle.total_linea, 0).toLocaleString('es-VE', { style: 'currency', currency: 'VES' }) || '0'}
                    </TableCell>
                    <TableCell>
                      {factura.id_nota_venta_origen ? 'Nota Venta' : 'Directa'}
                    </TableCell>
                    <TableCell align="center">
                      <IconButton onClick={(e) => handleMenuOpen(e, factura)}>
                        <MoreVertIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h6" color="text.secondary">
              No hay facturas fiscales registradas
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Crea tu primera factura fiscal haciendo clic en "Nueva Factura Fiscal"
            </Typography>
          </Box>
        )}
      </Paper>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
      >
        <MenuItem onClick={handleView}>Ver Detalles</MenuItem>
        <MenuItem onClick={handleEdit} disabled={selectedFactura?.estado !== 'BORRADOR'}>
          Editar
        </MenuItem>
        <MenuItem onClick={handleDelete} disabled={selectedFactura?.estado !== 'BORRADOR'}>
          Eliminar
        </MenuItem>
        {selectedFactura?.estado === 'EMITIDA' && (
          <MenuItem onClick={handleCrearNotaCredito}>
            Crear Nota de Crédito
          </MenuItem>
        )}
      </Menu>
    </PageLayout>
  );
};

export default FacturasFiscalesListPage;