import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { post, get } from '../../../services/api';
import { toList } from '../../../utils/api';
import { findSimilarMoneda } from '../../../utils/fuzzyDuplicate';
import { monedaSchema, type MonedaInput } from '../../../schemas/finanzas.schemas';
import type { Moneda } from './MonedaListPage';
import { finanzasKeys } from '../../../lib/queryKeys';
import { PageContainer, PageHeader } from '../../../components/ui';
import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Stack, TextField } from '@mui/material';

const defaultValues: MonedaInput = {
  tipo_moneda: 'fiat',
  codigo_iso: '',
  nombre: '',
  simbolo: '',
  decimales: 2,
  activo: true,
  referencia_externa: '',
  documento_json: '',
  tipo_operacion: '',
  fecha_cierre_estimada: '',
};

const MonedaFormPage: React.FC = () => {
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<MonedaInput>({
    resolver: zodResolver(monedaSchema),
    mode: 'onBlur',
    defaultValues,
  });

  const tipoMoneda = watch('tipo_moneda');

  const { data: monedasExistentes = [] } = useQuery<unknown, Error, Moneda[]>({
    queryKey: finanzasKeys.monedas.listFull(),
    queryFn: () => get('/finanzas/monedas/?limit=1000'),
    select: toList,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => post('/finanzas/monedas/', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: finanzasKeys.monedas.all() });
      navigate('/finanzas/monedas');
    },
    onError: () => setError('Error al crear moneda'),
  });

  const saving = createMutation.isPending;

  const onSubmit = (values: MonedaInput) => {
    setError('');
    const similar = findSimilarMoneda(values, monedasExistentes, 65);
    if (similar) {
      setError(`Ya existe una moneda similar: "${similar.nombre}" (${similar.codigo_iso})`);
      return;
    }
    const payload = {
      ...values,
      fecha_cierre_estimada: values.fecha_cierre_estimada || null,
    };
    createMutation.mutate(payload as Record<string, unknown>);
  };

  return (
    <PageContainer>
      <PageHeader title="Nueva Moneda" />
      <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate sx={{ maxWidth: 480 }}>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <Controller
            name="tipo_moneda"
            control={control}
            render={({ field }) => (
              <TextField
                select
                label="Tipo de Moneda"
                {...field}
                error={!!errors.tipo_moneda}
                helperText={errors.tipo_moneda?.message}
                disabled={saving}
                fullWidth
              >
                <MenuItem value="fiat">Fiat</MenuItem>
                <MenuItem value="crypto">Cripto</MenuItem>
                <MenuItem value="otro">Otro</MenuItem>
              </TextField>
            )}
          />
          <TextField
            label="Código ISO"
            {...register('codigo_iso')}
            error={!!errors.codigo_iso}
            helperText={errors.codigo_iso?.message}
            disabled={saving}
            fullWidth
            inputProps={{ maxLength: tipoMoneda === 'crypto' ? 5 : 3 }}
          />
          <TextField
            label="Nombre"
            {...register('nombre')}
            error={!!errors.nombre}
            helperText={errors.nombre?.message}
            disabled={saving}
            fullWidth
          />
          <TextField
            label="Símbolo"
            {...register('simbolo')}
            error={!!errors.simbolo}
            helperText={errors.simbolo?.message}
            disabled={saving}
            fullWidth
          />
          <TextField
            type="number"
            label="Decimales"
            {...register('decimales')}
            error={!!errors.decimales}
            helperText={errors.decimales?.message}
            disabled={saving}
            fullWidth
            inputProps={{ min: 0, max: 8 }}
          />
          <TextField
            label="Referencia Externa"
            {...register('referencia_externa')}
            error={!!errors.referencia_externa}
            helperText={errors.referencia_externa?.message}
            disabled={saving}
            fullWidth
          />
          <TextField
            label="Documento JSON"
            {...register('documento_json')}
            error={!!errors.documento_json}
            helperText={errors.documento_json?.message}
            disabled={saving}
            fullWidth
          />
          <TextField
            label="Tipo Operación"
            {...register('tipo_operacion')}
            error={!!errors.tipo_operacion}
            helperText={errors.tipo_operacion?.message}
            disabled={saving}
            fullWidth
          />
          <TextField
            type="date"
            label="Fecha Cierre Estimada"
            {...register('fecha_cierre_estimada')}
            error={!!errors.fecha_cierre_estimada}
            helperText={errors.fecha_cierre_estimada?.message}
            disabled={saving}
            fullWidth
            InputLabelProps={{ shrink: true }}
          />
          <Controller
            name="activo"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Checkbox checked={!!field.value} onChange={(e) => field.onChange(e.target.checked)} disabled={saving} />}
                label="Activo"
              />
            )}
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/finanzas/monedas')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={saving}>{saving ? 'Guardando…' : 'Crear'}</Button>
          </Stack>
        </Stack>
      </Box>
    </PageContainer>
  );
};

export default MonedaFormPage;
