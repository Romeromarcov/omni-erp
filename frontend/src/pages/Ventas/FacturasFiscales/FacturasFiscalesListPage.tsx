import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { facturaFiscalService } from '../../../services/ventas';
import type { FacturaFiscal } from '../../../types/ventas';
import { Alert, Box, Button, Chip, IconButton, Menu, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';

const FacturasFiscalesListPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [selectedFactura, setSelectedFactura] = useState<FacturaFiscal | null>(null);

  const { data: facturas = [], isLoading: loading, isError } = useQuery<FacturaFiscal[]>({
    queryKey: ['/ventas/facturas-fiscales/'],
    queryFn: () => facturaFiscalService.getAll(),
  });

  const error = isError ? 'Error al cargar las facturas fiscales' : null;

  const deleteMutation = useMutation({
    mutationFn: (id: string) => facturaFiscalService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/facturas-fiscales/'] });
    },
    onError: () => alert('Error al eliminar la factura fiscal'),
  });

  const generarNotaCreditoMutation = useMutation({
    mutationFn: (id: string) => facturaFiscalService.generarNotaCredito(id, 'DEVOLUCION', {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/facturas-fiscales/'] });
    },
    onError: () => alert('Error al crear la nota de crédito'),
  });

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

  const handleDelete = () => {
    if (selectedFactura && window.confirm('¿Está seguro de que desea eliminar esta factura fiscal?')) {
      deleteMutation.mutate(selectedFactura.id_factura);
    }
    handleMenuClose();
  };

  const handleCrearNotaCredito = () => {
    if (selectedFactura) {
      generarNotaCreditoMutation.mutate(selectedFactura.id_factura);
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