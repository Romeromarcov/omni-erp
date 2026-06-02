import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, useFieldArray, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import PageLayout from '../../../components/PageLayout';
import { devolucionVentaService } from '../../../services/ventas';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos } from '../../../services/productosService';
import { fetchClientes } from '../../../services/clientesService';
import { toList } from '../../../utils/api';
import { devolucionVentaSchema, type DevolucionVentaInput } from '../../../schemas/ventas.schemas';
import type { DevolucionVenta } from '../../../types/ventas';
import type { Cliente } from '../../../services/clientesService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, Checkbox, FormControlLabel, IconButton, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import { D, sumDecimals } from '../../../lib/decimal';

const defaultValues: DevolucionVentaInput = {
  id_cliente: '',
  id_factura_origen: '',
  fecha_devolucion: new Date().toISOString().split('T')[0],
  estado: 'PENDIENTE',
  motivo_devolucion: 'DEFECTO',
  generar_nota_credito: true,
  observaciones: '',
  detalles: [],
};

const DevolucionVentaFormPage: React.FC = () => {
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
  } = useForm<DevolucionVentaInput>({
    resolver: zodResolver(devolucionVentaSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'detalles' });

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

  // FE-HIGH-6: rehidratar con datos del servidor sin pisar ediciones en curso.
  useEffect(() => {
    if (devolucionData && !isDirty) {
      reset({
        id_cliente: devolucionData.id_cliente?.id_cliente || '',
        id_factura_origen: devolucionData.id_factura_origen || '',
        fecha_devolucion: (devolucionData.fecha_devolucion || '').slice(0, 10),
        estado: devolucionData.estado || 'PENDIENTE',
        motivo_devolucion: devolucionData.motivo_devolucion || 'DEFECTO',
        generar_nota_credito: Boolean(devolucionData.id_nota_credito_generada),
        observaciones: devolucionData.observaciones || '',
        detalles: (devolucionData.detalles || []).map((d) => ({
          id_producto: d.id_producto || '',
          cantidad_devuelta: Number(d.cantidad_devuelta ?? 0),
          precio_unitario: Number(d.precio_unitario ?? 0),
          estado_producto: d.estado_producto || 'BUENO',
          accion_inventario: d.accion_inventario || 'REINTEGRAR',
          observaciones: d.observaciones || '',
        })),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devolucionData]);

  // Total en vivo calculado con decimal.js sobre los detalles observados.
  const detalles = watch('detalles');
  const generarNotaCredito = watch('generar_nota_credito');
  const montoTotal = sumDecimals(
    (detalles || []).map((d) => D(d.cantidad_devuelta || 0).times(D(d.precio_unitario || 0))),
  );

  const saveMutation = useMutation({
    mutationFn: (submitData: Partial<DevolucionVenta> & { generar_nota_credito: boolean }) => {
      if (isEditing && id) {
        return devolucionVentaService.update(id, submitData);
      }
      return devolucionVentaService.create(submitData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/devoluciones-venta/'] });
      navigate('/ventas/devoluciones-venta');
    },
    onError: () => setError('Error al guardar la devolución'),
  });

  const saving = saveMutation.isPending;

  const onSubmit = (values: DevolucionVentaInput) => {
    setError(null);
    const cliente = clientes.find((c) => c.id_cliente === values.id_cliente);
    const detallesPayload = values.detalles.map((d) => ({
      id_producto: d.id_producto,
      cantidad_devuelta: d.cantidad_devuelta,
      precio_unitario: d.precio_unitario,
      subtotal: D(d.cantidad_devuelta).times(D(d.precio_unitario)).toNumber(),
      estado_producto: d.estado_producto,
      accion_inventario: d.accion_inventario,
      observaciones: d.observaciones,
    }));
    const total = sumDecimals(detallesPayload.map((d) => d.subtotal)).toNumber();
    const payload: Partial<DevolucionVenta> & { generar_nota_credito: boolean } = {
      id_factura_origen: values.id_factura_origen,
      fecha_devolucion: values.fecha_devolucion,
      estado: values.estado,
      motivo_devolucion: values.motivo_devolucion,
      observaciones: values.observaciones,
      monto_total: total,
      generar_nota_credito: values.generar_nota_credito,
      detalles: detallesPayload as DevolucionVenta['detalles'],
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
          {isEditing ? 'Editar' : 'Crear'} Devolución de Venta
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
                label="Fecha de Devolución"
                type="date"
                {...register('fecha_devolucion')}
                error={!!errors.fecha_devolucion}
                helperText={errors.fecha_devolucion?.message}
                required
                InputLabelProps={{ shrink: true }}
              />
              <Controller
                name="motivo_devolucion"
                control={control}
                render={({ field }) => (
                  <TextField
                    fullWidth
                    label="Motivo de Devolución"
                    select
                    {...field}
                    error={!!errors.motivo_devolucion}
                    helperText={errors.motivo_devolucion?.message}
                    required
                  >
                    <MenuItem value="DEFECTO">Producto defectuoso</MenuItem>
                    <MenuItem value="GARANTIA">Garantía</MenuItem>
                    <MenuItem value="ERROR_ENTREGA">Error en la entrega</MenuItem>
                    <MenuItem value="CAMBIO_CLIENTE">Cambio por parte del cliente</MenuItem>
                    <MenuItem value="VENCIMIENTO">Producto vencido</MenuItem>
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
                    <MenuItem value="PENDIENTE">Pendiente</MenuItem>
                    <MenuItem value="APROBADA">Aprobada</MenuItem>
                    <MenuItem value="PROCESADA">Procesada</MenuItem>
                    <MenuItem value="RECHAZADA">Rechazada</MenuItem>
                    <MenuItem value="ANULADA">Anulada</MenuItem>
                  </TextField>
                )}
              />
            </Box>

            <Controller
              name="generar_nota_credito"
              control={control}
              render={({ field }) => (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                    />
                  }
                  label="Generar automáticamente nota de crédito fiscal"
                  sx={{ mb: 3 }}
                />
              )}
            />

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
              <Typography variant="h6">Productos a Devolver</Typography>
              <Button
                variant="contained"
                color="secondary"
                onClick={() =>
                  append({
                    id_producto: '',
                    cantidad_devuelta: 1,
                    precio_unitario: 0,
                    estado_producto: 'BUENO',
                    accion_inventario: 'REINTEGRAR',
                    observaciones: '',
                  })
                }
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
                      <TableCell align="right">Subtotal</TableCell>
                      <TableCell>Estado del Producto</TableCell>
                      <TableCell>Acción en Inventario</TableCell>
                      <TableCell>Observaciones</TableCell>
                      <TableCell align="right">Acciones</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {fields.map((fieldItem, index) => {
                      const linea = detalles?.[index];
                      const subtotal = D(linea?.cantidad_devuelta || 0).times(D(linea?.precio_unitario || 0)).toNumber();
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
                              {...register(`detalles.${index}.cantidad_devuelta`)}
                              error={!!errors.detalles?.[index]?.cantidad_devuelta}
                              helperText={errors.detalles?.[index]?.cantidad_devuelta?.message}
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
                            {subtotal.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                          </TableCell>
                          <TableCell>
                            <Controller
                              name={`detalles.${index}.estado_producto`}
                              control={control}
                              render={({ field }) => (
                                <TextField select fullWidth {...field}>
                                  <MenuItem value="BUENO">Bueno</MenuItem>
                                  <MenuItem value="DEFECTUOSO">Defectuoso</MenuItem>
                                  <MenuItem value="VENCIDO">Vencido</MenuItem>
                                  <MenuItem value="DAÑADO">Dañado</MenuItem>
                                </TextField>
                              )}
                            />
                          </TableCell>
                          <TableCell>
                            <Controller
                              name={`detalles.${index}.accion_inventario`}
                              control={control}
                              render={({ field }) => (
                                <TextField select fullWidth {...field}>
                                  <MenuItem value="REINTEGRAR">Reintegrar al inventario</MenuItem>
                                  <MenuItem value="CUARENTENA">Poner en cuarentena</MenuItem>
                                  <MenuItem value="DESCARTAR">Descartar</MenuItem>
                                  <MenuItem value="REPARAR">Enviar a reparar</MenuItem>
                                </TextField>
                              )}
                            />
                          </TableCell>
                          <TableCell>
                            <TextField
                              {...register(`detalles.${index}.observaciones`)}
                              fullWidth
                              placeholder="Observaciones..."
                            />
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
                <Typography variant="h6" align="right">
                  Total de la Devolución: {montoTotal.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
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
