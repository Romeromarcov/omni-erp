import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, useFieldArray, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import PageLayout from '../../../components/PageLayout';
import { notaCreditoFiscalService } from '../../../services/ventas';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos } from '../../../services/productosService';
import { fetchClientes } from '../../../services/clientesService';
import { toList } from '../../../utils/api';
import { notaCreditoFiscalSchema, type NotaCreditoFiscalInput } from '../../../schemas/ventas.schemas';
import { ventasKeys } from '../../../lib/queryKeys';
import type { NotaCreditoFiscal } from '../../../types/ventas';
import type { Cliente } from '../../../services/clientesService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, IconButton, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import { D, sumDecimals } from '../../../lib/decimal';

const IVA_RATE = 0.16;

const defaultValues: NotaCreditoFiscalInput = {
  id_cliente: '',
  id_factura_origen: '',
  numero_control: '',
  fecha_emision: new Date().toISOString().split('T')[0],
  estado: 'BORRADOR',
  motivo: 'DEVOLUCION',
  afecta_inventario_fiscal: true,
  observaciones: '',
  detalles: [],
};

// Calcula los importes de una línea con decimal.js.
const calcularLinea = (cantidad: number, precio: number, descPct: number) => {
  const subtotalSinDescuento = D(cantidad || 0).times(D(precio || 0));
  const descuentoMonto = subtotalSinDescuento.times(D(descPct || 0).div(100));
  const subtotal = subtotalSinDescuento.minus(descuentoMonto);
  const montoImpuesto = subtotal.times(IVA_RATE);
  const totalLinea = subtotal.plus(montoImpuesto);
  return { descuentoMonto, subtotal, montoImpuesto, totalLinea };
};

const NotaCreditoFiscalFormPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);
  const empresaId = getEmpresaId() || '1';

  const [error, setError] = useState<string | null>(null);

  const {
    control,
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isDirty },
  } = useForm<NotaCreditoFiscalInput>({
    resolver: zodResolver(notaCreditoFiscalSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'detalles' });

  const { data: clientes = [] } = useQuery<unknown, Error, Cliente[]>({
    queryKey: ventasKeys.clientes(empresaId),
    queryFn: () => fetchClientes(empresaId),
    select: toList,
  });

  const { data: productos = [] } = useQuery<unknown, Error, Producto[]>({
    queryKey: ventasKeys.productos(empresaId),
    queryFn: () => fetchProductos(empresaId),
    select: toList,
  });

  const { data: notaCreditoData, isLoading: loading } = useQuery<NotaCreditoFiscal>({
    queryKey: ventasKeys.notasCreditoFiscal.detail(id!),
    queryFn: () => notaCreditoFiscalService.getById(id!),
    enabled: isEditing && !!id,
  });

  // FE-HIGH-6: rehidratar con datos del servidor sin pisar ediciones en curso.
  useEffect(() => {
    if (notaCreditoData && !isDirty) {
      reset({
        id_cliente: notaCreditoData.id_cliente?.id_cliente || '',
        id_factura_origen: notaCreditoData.id_factura_origen || '',
        numero_control: notaCreditoData.numero_control || '',
        fecha_emision: (notaCreditoData.fecha_emision || '').slice(0, 10),
        estado: notaCreditoData.estado || 'BORRADOR',
        motivo: notaCreditoData.motivo || 'DEVOLUCION',
        afecta_inventario_fiscal: notaCreditoData.afecta_inventario_fiscal ?? true,
        observaciones: notaCreditoData.observaciones || '',
        detalles: (notaCreditoData.detalles || []).map((d) => ({
          id_producto: d.id_producto || '',
          cantidad: Number(d.cantidad ?? 0),
          precio_unitario: Number(d.precio_unitario ?? 0),
          descuento_porcentaje: Number(d.descuento_porcentaje ?? 0),
        })),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notaCreditoData]);

  // Totales en vivo calculados con decimal.js sobre los detalles observados.
  const detalles = watch('detalles');
  const lineas = (detalles || []).map((d) =>
    calcularLinea(Number(d.cantidad) || 0, Number(d.precio_unitario) || 0, Number(d.descuento_porcentaje) || 0),
  );
  const baseImponible = sumDecimals(lineas.map((l) => l.subtotal));
  const montoIva = sumDecimals(lineas.map((l) => l.montoImpuesto));
  const montoTotal = sumDecimals(lineas.map((l) => l.totalLinea));

  const saveMutation = useMutation({
    mutationFn: (data: Partial<NotaCreditoFiscal>) => {
      if (isEditing && id) {
        return notaCreditoFiscalService.update(id, data);
      }
      return notaCreditoFiscalService.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ventasKeys.notasCreditoFiscal.all() });
      navigate('/ventas/notas-credito-fiscal');
    },
    onError: () => setError('Error al guardar la nota de crédito fiscal'),
  });

  const saving = saveMutation.isPending;

  const onSubmit = (values: NotaCreditoFiscalInput) => {
    setError(null);
    const cliente = clientes.find((c) => c.id_cliente === values.id_cliente);
    const detallesPayload = values.detalles.map((d) => {
      const { descuentoMonto, subtotal, montoImpuesto, totalLinea } = calcularLinea(
        d.cantidad, d.precio_unitario, d.descuento_porcentaje,
      );
      return {
        id_producto: d.id_producto,
        cantidad: d.cantidad,
        precio_unitario: d.precio_unitario,
        descuento_porcentaje: d.descuento_porcentaje,
        descuento_monto: descuentoMonto.toNumber(),
        subtotal: subtotal.toNumber(),
        monto_impuesto: montoImpuesto.toNumber(),
        total_linea: totalLinea.toNumber(),
      };
    });
    const payload: Partial<NotaCreditoFiscal> = {
      id_factura_origen: values.id_factura_origen,
      numero_control: values.numero_control,
      fecha_emision: values.fecha_emision,
      estado: values.estado,
      motivo: values.motivo,
      afecta_inventario_fiscal: values.afecta_inventario_fiscal,
      observaciones: values.observaciones,
      base_imponible: baseImponible.toNumber(),
      monto_iva: montoIva.toNumber(),
      monto_total: montoTotal.toNumber(),
      detalles: detallesPayload as NotaCreditoFiscal['detalles'],
      id_cliente: cliente
        ? {
            id_cliente: cliente.id_cliente,
            nombre: cliente.razon_social,
            razon_social: cliente.razon_social,
            rif: cliente.rif,
            telefono: cliente.telefono || '',
          }
        : null,
    };
    saveMutation.mutate(payload);
  };

  if (loading) return <PageLayout><div>Cargando...</div></PageLayout>;

  return (
    <PageLayout>
      <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
        <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
          {isEditing ? 'Editar' : 'Crear'} Nota de Crédito Fiscal
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 3 }}>Información General</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 3, mb: 3 }}>
              <Controller
                name="id_cliente"
                control={control}
                render={({ field }) => (
                  <TextField
                    fullWidth
                    label="Cliente"
                    select
                    {...field}
                    error={!!errors.id_cliente}
                    helperText={errors.id_cliente?.message}
                  >
                    {clientes.map((cliente) => (
                      <MenuItem key={cliente.id_cliente} value={cliente.id_cliente}>
                        {cliente.razon_social} - {cliente.rif}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
              <TextField
                fullWidth
                label="Factura Origen"
                {...register('id_factura_origen')}
                error={!!errors.id_factura_origen}
                helperText={errors.id_factura_origen?.message}
                placeholder="ID de la factura fiscal origen"
              />
              <TextField
                fullWidth
                label="Número de Control"
                {...register('numero_control')}
                error={!!errors.numero_control}
                helperText={errors.numero_control?.message}
                required
              />
              <TextField
                fullWidth
                label="Fecha de Emisión"
                type="date"
                {...register('fecha_emision')}
                error={!!errors.fecha_emision}
                helperText={errors.fecha_emision?.message}
                required
                InputLabelProps={{ shrink: true }}
              />
              <Controller
                name="motivo"
                control={control}
                render={({ field }) => (
                  <TextField
                    fullWidth
                    label="Motivo"
                    select
                    {...field}
                    error={!!errors.motivo}
                    helperText={errors.motivo?.message}
                    required
                  >
                    <MenuItem value="DEVOLUCION">Devolución</MenuItem>
                    <MenuItem value="DESCUENTO">Descuento</MenuItem>
                    <MenuItem value="ERROR_FACTURACION">Error de Facturación</MenuItem>
                    <MenuItem value="ANULACION">Anulación</MenuItem>
                    <MenuItem value="AJUSTE_PRECIO">Ajuste de Precio</MenuItem>
                    <MenuItem value="OTRO">Otro</MenuItem>
                  </TextField>
                )}
              />
              <Controller
                name="estado"
                control={control}
                render={({ field }) => (
                  <TextField
                    fullWidth
                    label="Estado"
                    select
                    {...field}
                    error={!!errors.estado}
                    helperText={errors.estado?.message}
                    required
                  >
                    <MenuItem value="BORRADOR">Borrador</MenuItem>
                    <MenuItem value="EMITIDA">Emitida</MenuItem>
                    <MenuItem value="APLICADA">Aplicada</MenuItem>
                    <MenuItem value="ANULADA">Anulada</MenuItem>
                  </TextField>
                )}
              />
            </Box>
            <TextField
              fullWidth
              label="Observaciones"
              multiline
              rows={3}
              {...register('observaciones')}
              error={!!errors.observaciones}
              helperText={errors.observaciones?.message}
            />
          </Paper>

          <Paper sx={{ p: 3, mb: 3 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography variant="h6">Detalles</Typography>
              <Button
                variant="contained"
                color="secondary"
                onClick={() => append({ id_producto: '', cantidad: 1, precio_unitario: 0, descuento_porcentaje: 0 })}
              >
                <AddIcon /> Agregar Producto
              </Button>
            </Box>

            {errors.detalles?.message && (
              <Alert severity="error" sx={{ mb: 2 }}>{errors.detalles.message}</Alert>
            )}

            {fields.length > 0 ? (
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
                    {fields.map((fieldItem, index) => {
                      const linea = lineas[index];
                      return (
                        <TableRow key={fieldItem.id}>
                          <TableCell>
                            <Controller
                              name={`detalles.${index}.id_producto`}
                              control={control}
                              render={({ field }) => (
                                <TextField
                                  select
                                  fullWidth
                                  {...field}
                                  error={!!errors.detalles?.[index]?.id_producto}
                                  helperText={errors.detalles?.[index]?.id_producto?.message}
                                >
                                  {productos.map((producto) => (
                                    <MenuItem key={producto.id_producto} value={producto.id_producto}>
                                      {producto.nombre_producto}
                                    </MenuItem>
                                  ))}
                                </TextField>
                              )}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              type="number"
                              {...register(`detalles.${index}.cantidad`)}
                              error={!!errors.detalles?.[index]?.cantidad}
                              helperText={errors.detalles?.[index]?.cantidad?.message}
                              inputProps={{ min: 0, step: 0.01 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              type="number"
                              {...register(`detalles.${index}.precio_unitario`)}
                              error={!!errors.detalles?.[index]?.precio_unitario}
                              helperText={errors.detalles?.[index]?.precio_unitario?.message}
                              inputProps={{ min: 0, step: 0.01 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              type="number"
                              {...register(`detalles.${index}.descuento_porcentaje`)}
                              error={!!errors.detalles?.[index]?.descuento_porcentaje}
                              helperText={errors.detalles?.[index]?.descuento_porcentaje?.message}
                              inputProps={{ min: 0, max: 100, step: 0.01 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            {linea?.subtotal.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                          </TableCell>
                          <TableCell align="right">
                            {linea?.montoImpuesto.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                          </TableCell>
                          <TableCell align="right">
                            {linea?.totalLinea.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                          </TableCell>
                          <TableCell align="right">
                            <IconButton onClick={() => remove(index)} color="error">
                              <DeleteIcon />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography color="text.secondary">
                No hay productos agregados. Haga clic en "Agregar Producto" para comenzar.
              </Typography>
            )}

            {fields.length > 0 && (
              <Box sx={{ mt: 3, p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2 }}>
                  <Typography variant="body2">
                    Base Imponible: {baseImponible.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                  </Typography>
                  <Typography variant="body2">
                    IVA: {montoIva.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                  </Typography>
                  <Typography variant="h6" align="right">
                    Total: {montoTotal.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
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
