import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { devolucionVentaService } from '../../../services/ventas';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos } from '../../../services/productosService';
import { fetchClientes } from '../../../services/clientesService';
import { toList } from '../../../utils/api';
import type { DevolucionVenta, DetalleDevolucionVenta } from '../../../types/ventas';
import type { Cliente } from '../../../services/clientesService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, Checkbox, FormControlLabel, IconButton, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';

const DevolucionVentaFormPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);
  const empresaId = getEmpresaId() || '1';

  const [formData, setFormData] = useState<Partial<DevolucionVenta>>({
    fecha_devolucion: new Date().toISOString().split('T')[0],
    estado: 'PENDIENTE',
    motivo_devolucion: 'DEFECTO',
    detalles: []
  });

  const [generarNotaCredito, setGenerarNotaCredito] = useState(true);
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

  const { data: devolucionData, isLoading: loading } = useQuery<DevolucionVenta>({
    queryKey: [`/ventas/devoluciones-venta/${id}/`],
    queryFn: () => devolucionVentaService.getById(id!),
    enabled: isEditing && !!id,
  });

  useEffect(() => {
    if (devolucionData) {
      setFormData(devolucionData);
      setGenerarNotaCredito(Boolean(devolucionData.id_nota_credito_generada));
    }
  }, [devolucionData]);

  const handleInputChange = (field: keyof DevolucionVenta, value: string | number | boolean) => {
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
    const newDetalle: DetalleDevolucionVenta = {
      id_detalle_devolucion: `temp_${Date.now()}`,
      id_devolucion: '',
      id_producto: '',
      cantidad_devuelta: 1,
      precio_unitario: 0,
      subtotal: 0,
      estado_producto: 'BUENO',
      accion_inventario: 'REINTEGRAR'
    };
    setFormData(prev => ({
      ...prev,
      detalles: [...(prev.detalles || []), newDetalle]
    }));
  };

  const updateDetalle = (index: number, field: keyof DetalleDevolucionVenta, value: string | number) => {
    const detalles = [...(formData.detalles || [])];
    detalles[index] = { ...detalles[index], [field]: value };

    // Recalcular subtotal
    if (field === 'cantidad_devuelta' || field === 'precio_unitario') {
      const cantidad = Number(detalles[index].cantidad_devuelta);
      const precioUnitario = Number(detalles[index].precio_unitario);
      detalles[index].subtotal = cantidad * precioUnitario;
    }

    setFormData(prev => ({ ...prev, detalles }));

    // Recalcular total
    const total = detalles.reduce((sum, det) => sum + (det.subtotal || 0), 0);
    setFormData(prev => ({ ...prev, monto_total: total }));
  };

  const removeDetalle = (index: number) => {
    const detalles = [...(formData.detalles || [])];
    detalles.splice(index, 1);
    setFormData(prev => ({ ...prev, detalles }));

    // Recalcular total
    const total = detalles.reduce((sum, det) => sum + (det.subtotal || 0), 0);
    setFormData(prev => ({ ...prev, monto_total: total }));
  };

  const saveMutation = useMutation({
    mutationFn: (submitData: Partial<DevolucionVenta> & { generar_nota_credito: boolean }) => {
      if (isEditing && id) {
        return devolucionVentaService.update(id, submitData);
      } else {
        return devolucionVentaService.create(submitData);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/devoluciones-venta/'] });
      navigate('/ventas/devoluciones-venta');
    },
    onError: () => setError('Error al guardar la devolución'),
  });

  const saving = saveMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate({ ...formData, generar_nota_credito: generarNotaCredito });
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
        <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
          {isEditing ? 'Editar' : 'Crear'} Devolución de Venta
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
                label="Factura Origen"
                value={formData.id_factura_origen || ''}
                onChange={(e) => handleInputChange('id_factura_origen', e.target.value)}
                placeholder="ID de la factura fiscal origen"
              />
              <TextField
                fullWidth
                label="Fecha de Devolución"
                type="date"
                value={formData.fecha_devolucion}
                onChange={(e) => handleInputChange('fecha_devolucion', e.target.value)}
                required
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                fullWidth
                label="Motivo de Devolución"
                select
                value={formData.motivo_devolucion}
                onChange={(e) => handleInputChange('motivo_devolucion', e.target.value)}
                required
              >
                <MenuItem value="DEFECTO">Producto defectuoso</MenuItem>
                <MenuItem value="GARANTIA">Garantía</MenuItem>
                <MenuItem value="ERROR_ENTREGA">Error en la entrega</MenuItem>
                <MenuItem value="CAMBIO_CLIENTE">Cambio por parte del cliente</MenuItem>
                <MenuItem value="VENCIMIENTO">Producto vencido</MenuItem>
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
                <MenuItem value="PENDIENTE">Pendiente</MenuItem>
                <MenuItem value="APROBADA">Aprobada</MenuItem>
                <MenuItem value="PROCESADA">Procesada</MenuItem>
                <MenuItem value="RECHAZADA">Rechazada</MenuItem>
                <MenuItem value="ANULADA">Anulada</MenuItem>
              </TextField>
            </Box>

            <FormControlLabel
              control={
                <Checkbox
                  checked={generarNotaCredito}
                  onChange={(e) => setGenerarNotaCredito(e.target.checked)}
                />
              }
              label="Generar automáticamente nota de crédito fiscal"
              sx={{ mb: 3 }}
            />

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
              <Typography variant="h6">Productos a Devolver</Typography>
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
                      <TableCell>Estado del Producto</TableCell>
                      <TableCell>Acción en Inventario</TableCell>
                      <TableCell>Observaciones</TableCell>
                      <TableCell align="right">Acciones</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {formData.detalles.map((detalle, index) => (
                      <TableRow key={detalle.id_detalle_devolucion}>
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
                            value={detalle.cantidad_devuelta}
                            onChange={(e) => updateDetalle(index, 'cantidad_devuelta', Number(e.target.value) || 0)}
                            inputProps={{ min: 0, step: 0.01 }}
                            required
                          />
                        </TableCell>
                        <TableCell align="right">
                          <TextField
                            type="number"
                            value={detalle.precio_unitario}
                            onChange={(e) => updateDetalle(index, 'precio_unitario', Number(e.target.value) || 0)}
                            inputProps={{ min: 0, step: 0.01 }}
                            required
                          />
                        </TableCell>
                        <TableCell align="right">
                          {detalle.subtotal?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                        </TableCell>
                        <TableCell>
                          <TextField
                            select
                            value={detalle.estado_producto}
                            onChange={(e) => updateDetalle(index, 'estado_producto', e.target.value)}
                            fullWidth
                          >
                            <MenuItem value="BUENO">Bueno</MenuItem>
                            <MenuItem value="DEFECTUOSO">Defectuoso</MenuItem>
                            <MenuItem value="VENCIDO">Vencido</MenuItem>
                            <MenuItem value="DAÑADO">Dañado</MenuItem>
                          </TextField>
                        </TableCell>
                        <TableCell>
                          <TextField
                            select
                            value={detalle.accion_inventario}
                            onChange={(e) => updateDetalle(index, 'accion_inventario', e.target.value)}
                            fullWidth
                          >
                            <MenuItem value="REINTEGRAR">Reintegrar al inventario</MenuItem>
                            <MenuItem value="CUARENTENA">Poner en cuarentena</MenuItem>
                            <MenuItem value="DESCARTAR">Descartar</MenuItem>
                            <MenuItem value="REPARAR">Enviar a reparar</MenuItem>
                          </TextField>
                        </TableCell>
                        <TableCell>
                          <TextField
                            value={detalle.observaciones || ''}
                            onChange={(e) => updateDetalle(index, 'observaciones', e.target.value)}
                            fullWidth
                            placeholder="Observaciones..."
                          />
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
                  Total de la Devolución: {formData.monto_total.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                </Typography>
                {generarNotaCredito && (
                  <Typography variant="body2" align="right" sx={{ mt: 1, color: 'success.main' }}>
                    Se generará automáticamente una nota de crédito fiscal por este monto
                  </Typography>
                )}
              </Box>
            )}
          </Paper>

          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
            <Button variant="contained" color="secondary" onClick={() => navigate('/ventas/devoluciones-venta')}>
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

export default DevolucionVentaFormPage;