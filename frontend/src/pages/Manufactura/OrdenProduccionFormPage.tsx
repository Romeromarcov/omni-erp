/**
 * Formulario de creación de Orden de Producción (1.I).
 *
 * Crea la OF (POST /manufactura/ordenes-produccion/ — `empresa` la inyecta el
 * backend, CTF-004) y navega al detalle. La cantidad viaja como string decimal
 * (R-CODE-4). La lista de materiales (BOM) es opcional: si se asocia, habilita
 * el consumo de materiales y el MRP de la OF.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
} from '@mui/material';
import { manufacturaService } from '../../services/manufacturaService';
import { fetchProductos, type Producto } from '../../services/productosService';
import { crearOrdenSchema, type CrearOrdenInput } from '../../schemas/manufactura.schemas';
import { manufacturaKeys, productosKeys } from '../../lib/queryKeys';
import { mensajeDeError, toList } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader } from '../../components/ui';

const hoy = () => new Date().toISOString().slice(0, 10);

export default function OrdenProduccionFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [errorGeneral, setErrorGeneral] = useState('');
  const empresaId = getEmpresaId() || '';

  const { data: productosRaw } = useQuery({
    queryKey: productosKeys.porEmpresa(empresaId),
    queryFn: () => fetchProductos(empresaId),
    enabled: !!empresaId,
  });
  const productos = useMemo(() => toList<Producto>(productosRaw), [productosRaw]);

  const { data: listas = [] } = useQuery({
    queryKey: manufacturaKeys.listasMateriales(),
    queryFn: () => manufacturaService.getListasMateriales(),
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CrearOrdenInput>({
    resolver: zodResolver(crearOrdenSchema),
    defaultValues: {
      producto: '',
      cantidad: '',
      fecha_inicio: hoy(),
      lista_materiales: '',
      referencia_externa: '',
      observaciones: '',
    },
  });

  const crearMutation = useMutation({
    mutationFn: (input: CrearOrdenInput) =>
      manufacturaService.crearOrden({
        producto: input.producto,
        cantidad: input.cantidad,
        fecha_inicio: input.fecha_inicio,
        ...(input.lista_materiales ? { lista_materiales: input.lista_materiales } : {}),
        ...(input.referencia_externa ? { referencia_externa: input.referencia_externa } : {}),
        ...(input.observaciones ? { observaciones: input.observaciones } : {}),
      }),
    onSuccess: (orden) => {
      snackbar.success(t('manufactura.form.creada'));
      void queryClient.invalidateQueries({ queryKey: manufacturaKeys.ordenesAll() });
      navigate(`/manufactura/ordenes/${orden.id}`);
    },
    onError: (err: unknown) => {
      setErrorGeneral(mensajeDeError(err, t('manufactura.form.error')));
    },
  });

  return (
    <PageContainer>
      <PageHeader title={t('manufactura.form.title')} subtitle={t('manufactura.form.subtitle')} />
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
          <Stack spacing={2}>
            <TextField
              select
              label={t('manufactura.form.producto')}
              fullWidth
              required
              defaultValue=""
              error={!!errors.producto}
              helperText={errors.producto?.message}
              {...register('producto')}
            >
              {productos.map((p) => (
                <MenuItem key={p.id_producto} value={p.id_producto}>
                  {p.nombre_producto}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('manufactura.form.cantidad')}
                fullWidth
                required
                inputMode="decimal"
                error={!!errors.cantidad}
                helperText={errors.cantidad?.message}
                {...register('cantidad')}
              />
              <TextField
                label={t('manufactura.form.fechaInicio')}
                type="date"
                fullWidth
                required
                InputLabelProps={{ shrink: true }}
                error={!!errors.fecha_inicio}
                helperText={errors.fecha_inicio?.message}
                {...register('fecha_inicio')}
              />
            </Stack>
            <TextField
              select
              label={t('manufactura.form.listaMateriales')}
              fullWidth
              defaultValue=""
              error={!!errors.lista_materiales}
              helperText={errors.lista_materiales?.message}
              {...register('lista_materiales')}
            >
              <MenuItem value="">{t('manufactura.form.sinLista')}</MenuItem>
              {listas.map((l) => (
                <MenuItem key={l.id} value={l.id}>
                  {l.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('manufactura.form.referencia')}
              fullWidth
              error={!!errors.referencia_externa}
              helperText={errors.referencia_externa?.message}
              {...register('referencia_externa')}
            />
            <TextField
              label={t('manufactura.form.observaciones')}
              fullWidth
              multiline
              rows={2}
              error={!!errors.observaciones}
              helperText={errors.observaciones?.message}
              {...register('observaciones')}
            />
          </Stack>
        </Paper>

        <Stack direction="row" spacing={2} justifyContent="flex-end">
          <Button onClick={() => navigate('/manufactura/ordenes')} disabled={crearMutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={crearMutation.isPending}
            startIcon={crearMutation.isPending ? <CircularProgress size={16} /> : undefined}
          >
            {t('manufactura.form.crear')}
          </Button>
        </Stack>
      </form>
    </PageContainer>
  );
}
