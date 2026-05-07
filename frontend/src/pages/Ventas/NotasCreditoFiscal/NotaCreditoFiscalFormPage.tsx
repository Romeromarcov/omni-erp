import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { notaCreditoFiscalService } from '../../../services/ventas';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos } from '../../../services/productosService';
import { fetchClientes } from '../../../services/clientesService';
import type { NotaCreditoFiscal, DetalleNotaCreditoFiscal } from '../../../types/ventas';
import type { Cliente } from '../../../services/clientesService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, IconButton, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';

const NotaCreditoFiscalFormPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(id);

  const [formData, setFormData] = useState<Partial<NotaCreditoFiscal>>({
    fecha_emision: new Date().toISOString().split('T')[0],
    estado: 'BORRADOR',
    motivo: 'DEVOLUCION',
    afecta_inventario_fiscal: true,
    detalles: []
  });

  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
    if (isEditing && id) {
      loadNotaCredito(id);
    }
  }, [id, isEditing]);

  const loadData = async () => {
    try {
      // TODO: Obtener empresa del contexto/usuario
      const empresaId = getEmpresaId() || '1'; // Fallback a '1' si no hay empresa
      const [clientesData, productosData] = await Promise.all([
        fetchClientes(empresaId),
        fetchProductos(empresaId)
      ]);
      const clientes = Array.isArray(clientesData) ? clientesData : clientesData.results || [];
      const productos = Array.isArray(productosData) ? productosData : productosData.results || [];
      setClientes(clientes);
      setProductos(productos);
    } catch (err) {
      console.error('Error cargando datos:', err);
    }
  };

  const loadNotaCredito = async (notaCreditoId: string) => {
    setLoading(true);
    try {
      const data = await notaCreditoFiscalService.getById(notaCreditoId);
      setFormData(data);
    } catch (err) {
      setError('Error al cargar la nota de crédito fiscal');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: keyof NotaCreditoFiscal, value: string | number | boolean) => {
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
    const newDetalle: DetalleNotaCreditoFiscal = {
      id_detalle_nota_credito: `temp_${Date.now()}`,
      id_nota_credito_fiscal: '',
      id_producto: '',
      cantidad: 1,
      precio_unitario: 0,
      descuento_porcentaje: 0,
      descuento_monto: 0,
      subtotal: 0,
      monto_impuesto: 0,
      total_linea: 0
    };
    setFormData(prev => ({
      ...prev,
      detalles: [...(prev.detalles || []), newDetalle]
    }));
  };

  const updateDetalle = (index: number, field: keyof DetalleNotaCreditoFiscal, value: string | number) => {
    const detalles = [...(formData.detalles || [])];
    detalles[index] = { ...detalles[index], [field]: value };

    // Recalcular valores
    if (field === 'cantidad' || field === 'precio_unitario' || field === 'descuento_porcentaje') {
      const cantidad = Number(detalles[index].cantidad);
      const precioUnitario = Number(detalles[index].precio_unitario);
      const descuentoPorcentaje = Number(detalles[index].descuento_porcentaje);

      const subtotalSinDescuento = cantidad * precioUnitario;
      const descuentoMonto = subtotalSinDescuento * (descuentoPorcentaje / 100);
      const subtotal = subtotalSinDescuento - descuentoMonto;

      detalles[index].descuento_monto = descuentoMonto;
      detalles[index].subtotal = subtotal;
      detalles[index].monto_impuesto = subtotal * 0.16; // IVA 16%
      detalles[index].total_linea = subtotal + detalles[index].monto_impuesto;
    }

    setFormData(prev => ({ ...prev, detalles }));

    // Recalcular totales
    const totales = detalles.reduce((acc, det) => ({
      base_imponible: acc.base_imponible + (det.subtotal || 0),
      monto_iva: acc.monto_iva + (det.monto_impuesto || 0),
      monto_total: acc.monto_total + (det.total_linea || 0)
    }), { base_imponible: 0, monto_iva: 0, monto_total: 0 });

    setFormData(prev => ({ ...prev, ...totales }));
  };

  const removeDetalle = (index: number) => {
    const detalles = [...(formData.detalles || [])];
    detalles.splice(index, 1);
    setFormData(prev => ({ ...prev, detalles }));

    // Recalcular totales
    const totales = detalles.reduce((acc, det) => ({
      base_imponible: acc.base_imponible + (det.subtotal || 0),
      monto_iva: acc.monto_iva + (det.monto_impuesto || 0),
      monto_total: acc.monto_total + (det.total_linea || 0)
    }), { base_imponible: 0, monto_iva: 0, monto_total: 0 });

    setFormData(prev => ({ ...prev, ...totales }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEditing && id) {
        await notaCreditoFiscalService.update(id, formData);
      } else {
        await notaCreditoFiscalService.create(formData);
      }
      navigate('/ventas/notas-credito-fiscal');
    } catch (err) {
      setError('Error al guardar la nota de crédito fiscal');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
        <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
          {isEditing ? 'Editar' : 'Crear'} Nota de Crédito Fiscal
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
                label="Número de Control"
                value={formData.numero_control || ''}
                onChange={(e) => handleInputChange('numero_control', e.target.value)}
                required
              />
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
                <MenuItem value="AJUSTE_PRECIO">Ajuste de Precio</MenuItem>
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
                      <TableCell align="right">% Descuento</TableCell>
                      <TableCell align="right">Subtotal</TableCell>
                      <TableCell align="right">Impuesto</TableCell>
                      <TableCell align="right">Total</TableCell>
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
                            onChange={(e) => updateDetalle(index, 'cantidad', Number(e.target.value) || 0)}
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
                          <TextField
                            type="number"
                            value={detalle.descuento_porcentaje}
                            onChange={(e) => updateDetalle(index, 'descuento_porcentaje', Number(e.target.value) || 0)}
                            inputProps={{ min: 0, max: 100, step: 0.01 }}
                          />
                        </TableCell>
                        <TableCell align="right">
                          {detalle.subtotal?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                        </TableCell>
                        <TableCell align="right">
                          {detalle.monto_impuesto?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                        </TableCell>
                        <TableCell align="right">
                          {detalle.total_linea?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
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
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2 }}>
                  <Typography variant="body2">
                    Base Imponible: {formData.base_imponible?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                  </Typography>
                  <Typography variant="body2">
                    IVA: {formData.monto_iva?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                  </Typography>
                  <Typography variant="h6" align="right">
                    Total: {formData.monto_total.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                  </Typography>
                </Box>
              </Box>
            )}
          </Paper>

          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
            <Button variant="contained" color="secondary" onClick={() => navigate('/ventas/notas-credito-fiscal')}>
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

export default NotaCreditoFiscalFormPage;