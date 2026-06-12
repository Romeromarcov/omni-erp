/**
 * Formulario de creación de Orden de Compra (workstream F).
 *
 * Crea la cabecera (POST /compras/ordenes-compra/ — `id_empresa` lo inyecta el
 * backend, H-API-2) y luego cada línea (POST /compras/detalles-orden-compra/).
 * Los subtotales y el total se calculan con decimal.js (R-CODE-4): cero
 * aritmética float sobre montos.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import DeleteOutline from '@mui/icons-material/DeleteOutline';
import { comprasService } from '../../services/comprasService';
import { fetchProductos, type Producto } from '../../services/productosService';
import { ordenCompraSchema, type OrdenCompraInput } from '../../schemas/compras.schemas';
import { comprasKeys, productosKeys } from '../../lib/queryKeys';
import { mensajeDeError, toList } from '../../utils/api';
import { D, subtotalLinea, toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader } from '../../components/ui';

const hoy = () => new Date().toISOString().slice(0, 10);

export default function OrdenCompraFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [errorGeneral, setErrorGeneral] = useState('');
  const empresaId = getEmpresaId() || '';

  const { data: proveedores = [] } = useQuery({
    queryKey: comprasKeys.proveedores(),
    queryFn: () => comprasService.getProveedores(),
  });

  const { data: productosRaw } = useQuery({
    queryKey: productosKeys.porEmpresa(empresaId),
    queryFn: () => fetchProductos(empresaId),
    enabled: !!empresaId,
  });
  const productos = useMemo(() => toList<Producto>(productosRaw), [productosRaw]);

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<OrdenCompraInput>({
    resolver: zodResolver(ordenCompraSchema),
    defaultValues: {
      id_proveedor: '',
      numero_orden: '',
      fecha_orden: hoy(),
      observaciones: '',
      detalles: [{ id_producto: '', cantidad: '', precio_unitario: '' }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'detalles' });
  const detallesWatch = watch('detalles');

  // Total de la OC con decimal.js — nunca aritmética float (R-CODE-4).
  // Sin useMemo: `watch` puede devolver la misma referencia de array mutada,
  // lo que congelaría el memo; el cálculo es barato por render.
  const total = (detallesWatch ?? []).reduce(
    (acc, d) => acc.plus(subtotalLinea(d.cantidad, d.precio_unitario)),
    D(0),
  );

  const crearMutation = useMutation({
    mutationFn: async (input: OrdenCompraInput) => {
      const orden = await comprasService.crearOrden({
        id_proveedor: input.id_proveedor,
        numero_orden: input.numero_orden,
        fecha_orden: input.fecha_orden,
        observaciones: input.observaciones || '',
      });
      // Las líneas se crean en secuencia; el subtotal se fija con decimal.js.
      for (const linea of input.detalles) {
        await comprasService.crearDetalle({
          id_orden_compra: orden.id_orden_compra,
          id_producto: linea.id_producto,
          cantidad: linea.cantidad,
          precio_unitario: linea.precio_unitario,
          subtotal: subtotalLinea(linea.cantidad, linea.precio_unitario).toFixed(4),
        });
      }
      return orden;
    },
    onSuccess: (orden) => {
      snackbar.success(t('compras.form.creada'));
      void queryClient.invalidateQueries({ queryKey: comprasKeys.ordenesAll() });
      navigate(`/compras/ordenes/${orden.id_orden_compra}`);
    },
    onError: (err: unknown) => {
      // 400 del backend (p. ej. numero_orden duplicado) visible en la página.
      setErrorGeneral(mensajeDeError(err, t('compras.form.error')));
    },
  });

  return (
    <PageContainer>
      <PageHeader title={t('compras.form.title')} subtitle={t('compras.form.subtitle')} />
      <form
        onSubmit={handleSubmit((input) => {
          setErrorGeneral('');
          crearMutation.mutate(input);
        })}
        noValidate
      >
        <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
          {errorGeneral && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorGeneral}
            </Alert>
          )}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <TextField
              select
              label={t('compras.form.proveedor')}
              fullWidth
              required
              defaultValue=""
              error={!!errors.id_proveedor}
              helperText={errors.id_proveedor?.message}
              {...register('id_proveedor')}
            >
              {proveedores.map((p) => (
                <MenuItem key={p.id_proveedor} value={p.id_proveedor}>
                  {p.razon_social}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('compras.form.numeroOrden')}
              fullWidth
              required
              error={!!errors.numero_orden}
              helperText={errors.numero_orden?.message}
              {...register('numero_orden')}
            />
            <TextField
              label={t('compras.form.fechaOrden')}
              type="date"
              fullWidth
              required
              InputLabelProps={{ shrink: true }}
              error={!!errors.fecha_orden}
              helperText={errors.fecha_orden?.message}
              {...register('fecha_orden')}
            />
          </Stack>
          <TextField
            label={t('compras.form.observaciones')}
            fullWidth
            multiline
            rows={2}
            error={!!errors.observaciones}
            helperText={errors.observaciones?.message}
            {...register('observaciones')}
          />
        </Paper>

        <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {t('compras.form.lineas')}
          </Typography>
          {errors.detalles?.message && <Alert severity="warning" sx={{ mb: 1 }}>{errors.detalles.message}</Alert>}
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('compras.form.producto')}</TableCell>
                <TableCell width={140}>{t('compras.form.cantidad')}</TableCell>
                <TableCell width={160}>{t('compras.form.precioUnitario')}</TableCell>
                <TableCell width={140} align="right">
                  {t('compras.form.subtotal')}
                </TableCell>
                <TableCell width={56} />
              </TableRow>
            </TableHead>
            <TableBody>
              {fields.map((field, idx) => {
                // eslint-disable-next-line security/detect-object-injection -- FP: `idx` es el índice entero que emite fields.map (array de RHF), no una clave arbitraria
                const erroresLinea = errors.detalles?.[idx];
                const lineaWatch = detallesWatch?.at(idx);
                return (
                <TableRow key={field.id}>
                  <TableCell>
                    <TextField
                      select
                      fullWidth
                      size="small"
                      defaultValue=""
                      label={t('compras.form.producto')}
                      error={!!erroresLinea?.id_producto}
                      helperText={erroresLinea?.id_producto?.message}
                      {...register(`detalles.${idx}.id_producto`)}
                    >
                      {productos.map((p) => (
                        <MenuItem key={p.id_producto} value={p.id_producto}>
                          {p.nombre_producto}
                        </MenuItem>
                      ))}
                    </TextField>
                  </TableCell>
                  <TableCell>
                    <TextField
                      size="small"
                      inputMode="decimal"
                      label={t('compras.form.cantidad')}
                      error={!!erroresLinea?.cantidad}
                      helperText={erroresLinea?.cantidad?.message}
                      {...register(`detalles.${idx}.cantidad`)}
                    />
                  </TableCell>
                  <TableCell>
                    <TextField
                      size="small"
                      inputMode="decimal"
                      label={t('compras.form.precioUnitario')}
                      error={!!erroresLinea?.precio_unitario}
                      helperText={erroresLinea?.precio_unitario?.message}
                      {...register(`detalles.${idx}.precio_unitario`)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {toFixedStr(
                        subtotalLinea(lineaWatch?.cantidad, lineaWatch?.precio_unitario),
                      )}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <IconButton
                      size="small"
                      aria-label={t('compras.form.quitarLinea')}
                      onClick={() => remove(idx)}
                      disabled={fields.length === 1}
                    >
                      <DeleteOutline fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 2 }}>
            <Button
              startIcon={<AddOutlined />}
              onClick={() => append({ id_producto: '', cantidad: '', precio_unitario: '' })}
            >
              {t('compras.form.agregarLinea')}
            </Button>
            <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {`${t('compras.form.total')}: ${toFixedStr(total)}`}
            </Typography>
          </Stack>
        </Paper>

        <Stack direction="row" spacing={2} justifyContent="flex-end">
          <Button onClick={() => navigate('/compras/ordenes')} disabled={crearMutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={crearMutation.isPending}
            startIcon={crearMutation.isPending ? <CircularProgress size={16} /> : undefined}
          >
            {t('compras.form.crear')}
          </Button>
        </Stack>
      </form>
    </PageContainer>
  );
}
