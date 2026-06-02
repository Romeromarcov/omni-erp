import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, useFieldArray, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import PageLayout from '../../../components/PageLayout';
import { notaCreditoVentaService } from '../../../services/ventas';
import { getEmpresaId } from '../../../utils/empresa';
import { fetchProductos } from '../../../services/productosService';
import { fetchClientes } from '../../../services/clientesService';
import { toList } from '../../../utils/api';
import { notaCreditoVentaSchema, type NotaCreditoVentaInput } from '../../../schemas/ventas.schemas';
import type { NotaCreditoVenta } from '../../../types/ventas';
import type { Cliente } from '../../../services/clientesService';
import type { Producto } from '../../../services/productosService';
import { Alert, Box, Button, IconButton, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import { D, sumDecimals } from '../../../lib/decimal';

const defaultValues: NotaCreditoVentaInput = {
  id_cliente: '',
  fecha_emision: new Date().toISOString().split('T')[0],
  estado: 'BORRADOR',
  motivo: 'DEVOLUCION',
  observaciones: '',
  detalles: [],
};

const NotaCreditoVentaFormPage: React.FC = () => {
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
  } = useForm<NotaCreditoVentaInput>({
    resolver: zodResolver(notaCreditoVentaSchema),
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

  const { data: notaCreditoData, isLoading: loading } = useQuery<NotaCreditoVenta>({
    queryKey: [`/ventas/notas-credito-venta/${id}/`],
    queryFn: () => notaCreditoVentaService.getById(id!),
    enabled: isEditing && !!id,
  });

  // FE-HIGH-6: rehidratar con datos del servidor sin pisar ediciones en curso.
  useEffect(() => {
    if (notaCreditoData && !isDirty) {
      reset({
        id_cliente: notaCreditoData.id_cliente?.id_cliente || '',
        fecha_emision: (notaCreditoData.fecha_emision || '').slice(0, 10),
        estado: notaCreditoData.estado || 'BORRADOR',
        motivo: notaCreditoData.motivo || 'DEVOLUCION',
        observaciones: notaCreditoData.observaciones || '',
        detalles: (notaCreditoData.detalles || []).map((d) => ({
          id_producto: d.id_producto || '',
          cantidad: Number(d.cantidad ?? 0),
          precio_unitario: Number(d.precio_unitario ?? 0),
        })),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notaCreditoData]);

  // Total en vivo calculado con decimal.js sobre los detalles observados.
  const detalles = watch('detalles');
  const montoTotal = sumDecimals(
    (detalles || []).map((d) => D(d.cantidad || 0).times(D(d.precio_unitario || 0))),
  );

  const saveMutation = useMutation({
    mutationFn: (data: Partial<NotaCreditoVenta>) => {
      if (isEditing && id) {
        return notaCreditoVentaService.update(id, data);
      }
      return notaCreditoVentaService.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/notas-credito-venta/'] });
      navigate('/ventas/notas-credito-venta');
    },
    onError: () => setError('Error al guardar la nota de crédito'),
  });

  const saving = saveMutation.isPending;

  const onSubmit = (values: NotaCreditoVentaInput) => {
    setError(null);
    const cliente = clientes.find((c) => c.id_cliente === values.id_cliente);
    const detallesPayload = values.detalles.map((d) => {
      const subtotal = D(d.cantidad).times(D(d.precio_unitario));
      return {
        id_producto: d.id_producto,
        cantidad: d.cantidad,
        precio_unitario: d.precio_unitario,
        subtotal: subtotal.toNumber(),
        monto_impuesto: 0,
        total_linea: subtotal.toNumber(),
      };
    });
    const total = sumDecimals(detallesPayload.map((d) => d.total_linea)).toNumber();
    const payload: Partial<NotaCreditoVenta> = {
      fecha_emision: values.fecha_emision,
      estado: values.estado,
      motivo: values.motivo,
      observaciones: values.observaciones,
      monto_total: total,
      detalles: detallesPayload as NotaCreditoVenta['detalles'],
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
          {isEditing ? 'Editar' : 'Crear'} Nota de Crédito de Venta
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
                label="Fecha de Emisión"
                type="date"
                {...register('fecha_emision')}
                error={!!errors.fecha_emision}
                helperText={errors.fecha_emision?.message}
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
                  >
                    <MenuItem value="DEVOLUCION">Devolución</MenuItem>
                    <MenuItem value="DESCUENTO">Descuento</MenuItem>
                    <MenuItem value="ERROR_FACTURACION">Error de Facturación</MenuItem>
                    <MenuItem value="ANULACION">Anulación</MenuItem>
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
                onClick={() => append({ id_producto: '', cantidad: 1, precio_unitario: 0 })}
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
                      <TableCell align="right">Acciones</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {fields.map((fieldItem, index) => {
                      const linea = detalles?.[index];
                      const subtotal = D(linea?.cantidad || 0).times(D(linea?.precio_unitario || 0)).toNumber();
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
                            {subtotal.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
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
                  Total: {montoTotal.toNumber().toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
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
