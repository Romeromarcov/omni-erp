import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { notaCreditoVentaService } from '../../../services/ventas';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos } from '../../../services/productosService';
import { fetchClientes } from '../../../services/clientesService';
import { toList } from '../../../utils/api';
import type { NotaCreditoVenta, DetalleNotaCreditoVenta } from '../../../types/ventas';
import type { Cliente } from '../../../services/clientesService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, IconButton, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import { D, sumDecimals } from '../../../lib/decimal';

const NotaCreditoVentaFormPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);
  const empresaId = getEmpresaId() || '1';

  const [formData, setFormData] = useState<Partial<NotaCreditoVenta>>({
    fecha_emision: new Date().toISOString().split('T')[0],
    estado: 'BORRADOR',
    motivo: 'DEVOLUCION',
    detalles: []
  });

  const [error, setError] = useState<string | null>(null);

  const { data: clientes = [] } = useQuery<unknown, Error, Cliente[]>({
    queryKey: [`/ventas/clientes/?id_empresa=${empresaId}`],
    queryFn: () => fetchClientes(empresaId),
    select: toList,
  });

  const { data: productos = [] } = useQuery<unknown, Error, Producto[]>({
    queryKey: [`/ventas/productos/?id_empresa=${empresaId}`],
    queryFn: () => fetchProductos(empresaId),
    select: toList,
  });

  const { data: notaCreditoData, isLoading: loading } = useQuery<NotaCreditoVenta>({
    queryKey: [`/ventas/notas-credito-venta/${id}/`],
    queryFn: () => notaCreditoVentaService.getById(id!),
    enabled: isEditing && !!id,
  });

  useEffect(() => {
    if (notaCreditoData) setFormData(notaCreditoData);
  }, [notaCreditoData]);

  const handleInputChange = (field: keyof NotaCreditoVenta, value: string | number | boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleClienteChange = (clienteId: string) => {
    const cliente = clientes.find(c => c.id_cliente === clienteId);
    if (cliente) {
      setFormData(prev => ({ ...prev, id_cliente: {
        id_cliente: cliente.id_cliente,
        nombre: cliente.razon_social, // Usar razon_social como nombre
        razon_social: cliente.razon_social,
        rif: cliente.rif,
        telefono: cliente.telefono || ''
      }}));
    }
  };

  const addDetalle = () => {
    const newDetalle: DetalleNotaCreditoVenta = {
      id_detalle_nota_credito: `temp_${Date.now()}`,
      id_nota_credito: '',
      id_producto: '',
      cantidad: 1,
      precio_unitario: 0,
      subtotal: 0,
      monto_impuesto: 0,
      total_linea: 0
    };
    setFormData(prev => ({
      ...prev,
      detalles: [...(prev.detalles || []), newDetalle]
    }));
  };

  const updateDetalle = (index: number, field: keyof DetalleNotaCreditoVenta, value: string | number) => {
    const detalles = [...(formData.detalles || [])];
    detalles[index] = { ...detalles[index], [field]: value };

    // Recalcular subtotal (decimal.js para evitar errores de punto flotante)
    if (field === 'cantidad' || field === 'precio_unitario') {
      const cantidad = field === 'cantidad' ? value : detalles[index].cantidad;
      const precioUnitario = field === 'precio_unitario' ? value : detalles[index].precio_unitario;
      const subtotal = D(cantidad).times(D(precioUnitario));
      detalles[index].subtotal = subtotal.toNumber();
      detalles[index].total_linea = subtotal.plus(D(detalles[index].monto_impuesto)).toNumber();
    }

    setFormData(prev => ({ ...prev, detalles }));

    // Recalcular total
    const total = sumDecimals(detalles.map(det => det.total_linea)).toNumber();
    setFormData(prev => ({ ...prev, monto_total: total }));
  };

  const removeDetalle = (index: number) => {
    const detalles = [...(formData.detalles || [])];
    detalles.splice(index, 1);
    setFormData(prev => ({ ...prev, detalles }));

    // Recalcular total
    const total = sumDecimals(detalles.map(det => det.total_linea)).toNumber();
    setFormData(prev => ({ ...prev, monto_total: total }));
  };

  const saveMutation = useMutation({
    mutationFn: (data: Partial<NotaCreditoVenta>) => {
      if (isEditing && id) {
        return notaCreditoVentaService.update(id, data);
      } else {
        return notaCreditoVentaService.create(data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/notas-credito-venta/'] });
      navigate('/ventas/notas-credito-venta');
    },
    onError: () => setError('Error al guardar la nota de crédito'),
  });

  const saving = saveMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
        <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
          {isEditing ? 'Editar' : 'Crear'} Nota de Crédito de Venta
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

        <form onSubmit={handleSubmit}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 3 }}>Información General</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 3, mb: 3 }}>
              <TextField
                fullWidth
                label="Cliente"
                select
                value={formData.id_cliente?.id_cliente || ''}
                onChange={(e) => handleClienteChange(e.target.value)}
                required
              >
                {clientes.map((cliente) => (
                  <MenuItem key={cliente.id_cliente} value={cliente.id_cliente}>
                    {cliente.razon_social} - {cliente.rif}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                fullWidth
                label="Fecha de Emisión"
                type="date"
                value={formData.fecha_emision}
                onChange={(e) => handleInputChange('fecha_emision', e.target.value)}
                required
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                fullWidth
                label="Motivo"
                select
                value={formData.motivo}
                onChange={(e) => handleInputChange('motivo', e.target.value)}
                required
              >
                <MenuItem value="DEVOLUCION">Devolución</MenuItem>
                <MenuItem value="DESCUENTO">Descuento</MenuItem>
                <MenuItem value="ERROR_FACTURACION">Error de Facturación</MenuItem>
                <MenuItem value="ANULACION">Anulación</MenuItem>
                <MenuItem value="OTRO">Otro</MenuItem>
              </TextField>
              <TextField
                fullWidth
                label="Estado"
                select
                value={formData.estado}
                onChange={(e) => handleInputChange('estado', e.target.value)}
                required
              >
                <MenuItem value="BORRADOR">Borrador</MenuItem>
                <MenuItem value="EMITIDA">Emitida</MenuItem>
                <MenuItem value="APLICADA">Aplicada</MenuItem>
                <MenuItem value="ANULADA">Anulada</MenuItem>
              </TextField>
            </Box>
            <TextField
              fullWidth
              label="Observaciones"
              multiline
              rows={3}
              value={formData.observaciones || ''}
              onChange={(e) => handleInputChange('observaciones', e.target.value)}
            />
          </Paper>

          <Paper sx={{ p: 3, mb: 3 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography variant="h6">Detalles</Typography>
              <Button variant="contained" color="secondary" onClick={addDetalle}>
                <AddIcon /> Agregar Producto
              </Button>
            </Box>

            {formData.detalles && formData.detalles.length > 0 ? (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Producto</TableCell>
                      <TableCell align="right">Cantidad</TableCell>
                      <TableCell align="right">Precio Unitario</TableCell>
                      <TableCell align="right">Subtotal</TableCell>
                      <TableCell align="right">Acciones</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {formData.detalles.map((detalle, index) => (
                      <TableRow key={detalle.id_detalle_nota_credito}>
                        <TableCell>
                          <TextField
                            select
                            fullWidth
                            value={detalle.id_producto}
                            onChange={(e) => updateDetalle(index, 'id_producto', e.target.value)}
                            required
                          >
                            {productos.map((producto) => (
                              <MenuItem key={producto.id_producto} value={producto.id_producto}>
                                {producto.nombre_producto}
                              </MenuItem>
                            ))}
                          </TextField>
                        </TableCell>
                        <TableCell align="right">
                          <TextField
                            type="number"
                            value={detalle.cantidad}
                            onChange={(e) => updateDetalle(index, 'cantidad', parseFloat(e.target.value) || 0)}
                            inputProps={{ min: 0, step: 0.01 }}
                            required
                          />
                        </TableCell>
                        <TableCell align="right">
                          <TextField
                            type="number"
                            value={detalle.precio_unitario}
                            onChange={(e) => updateDetalle(index, 'precio_unitario', parseFloat(e.target.value) || 0)}
                            inputProps={{ min: 0, step: 0.01 }}
                            required
                          />
                        </TableCell>
                        <TableCell align="right">
                          {detalle.subtotal?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                        </TableCell>
                        <TableCell align="right">
                          <IconButton onClick={() => removeDetalle(index)} color="error">
                            <DeleteIcon />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography color="text.secondary">
                No hay productos agregados. Haga clic en "Agregar Producto" para comenzar.
              </Typography>
            )}

            {formData.monto_total && (
              <Box sx={{ mt: 3, p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
                <Typography variant="h6" align="right">
                  Total: {formData.monto_total.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                </Typography>
              </Box>
            )}
          </Paper>

          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
            <Button variant="contained" color="secondary" onClick={() => navigate('/ventas/notas-credito-venta')}>
              Cancelar
            </Button>
            <Button variant="contained" type="submit" disabled={saving}>
              {saving ? 'Guardando...' : (isEditing ? 'Actualizar' : 'Crear')}
            </Button>
          </Box>
        </form>
      </Box>
    </PageLayout>
  );
};

export default NotaCreditoVentaFormPage;