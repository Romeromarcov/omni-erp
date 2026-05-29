import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { post, get } from '../../../services/api';
import { toList } from '../../../utils/api';
import { findSimilarMoneda } from '../../../utils/fuzzyDuplicate';
import type { Moneda } from './MonedaListPage';
import PageLayout from '../../../components/PageLayout';
import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material';

const defaultMoneda: Partial<Moneda> = {
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
  const [moneda, setMoneda] = useState<Partial<Moneda>>(defaultMoneda);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: monedasExistentes = [] } = useQuery<unknown, Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/?limit=1000'],
    queryFn: () => get('/finanzas/monedas/?limit=1000'),
    select: toList,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => post('/finanzas/monedas/', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/monedas/'] });
      navigate('/finanzas/monedas');
    },
    onError: () => setError('Error al crear moneda'),
  });

  const saving = createMutation.isPending;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setMoneda({ ...moneda, [e.target.name]: e.target.value });
  };

  const handleCheck = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMoneda({ ...moneda, [e.target.name]: e.target.checked });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const similar = findSimilarMoneda(moneda, monedasExistentes, 65);
    if (similar) {
      setError(`Ya existe una moneda similar: "${similar.nombre}" (${similar.codigo_iso})`);
      return;
    }
    const payload = {
      ...moneda,
      fecha_cierre_estimada: moneda.fecha_cierre_estimada
        ? (typeof moneda.fecha_cierre_estimada === 'string' && moneda.fecha_cierre_estimada.match(/^\d{4}-\d{2}-\d{2}$/)
            ? moneda.fecha_cierre_estimada
            : null)
        : null,
    };
    createMutation.mutate(payload as Record<string, unknown>);
  };

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Nueva Moneda</Typography>
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField select name="tipo_moneda" label="Tipo de Moneda" value={moneda.tipo_moneda || 'fiat'} onChange={handleChange} required fullWidth>
            <MenuItem value="fiat">Fiat</MenuItem>
            <MenuItem value="crypto">Cripto</MenuItem>
            <MenuItem value="otro">Otro</MenuItem>
          </TextField>
          <TextField name="codigo_iso" label="Código ISO" value={moneda.codigo_iso} onChange={handleChange} required fullWidth inputProps={{ maxLength: moneda.tipo_moneda === 'crypto' ? 5 : 3 }} />
          <TextField name="nombre" label="Nombre" value={moneda.nombre} onChange={handleChange} required fullWidth />
          <TextField name="simbolo" label="Símbolo" value={moneda.simbolo} onChange={handleChange} required fullWidth />
          <TextField name="decimales" type="number" label="Decimales" value={moneda.decimales} onChange={handleChange} required fullWidth inputProps={{ min: 0, max: 8 }} />
          <TextField name="referencia_externa" label="Referencia Externa" value={moneda.referencia_externa || ''} onChange={handleChange} fullWidth />
          <TextField name="documento_json" label="Documento JSON" value={moneda.documento_json || ''} onChange={handleChange} fullWidth />
          <TextField name="tipo_operacion" label="Tipo Operación" value={moneda.tipo_operacion || ''} onChange={handleChange} fullWidth />
          <TextField name="fecha_cierre_estimada" type="date" label="Fecha Cierre Estimada" value={moneda.fecha_cierre_estimada || ''} onChange={handleChange} fullWidth InputLabelProps={{ shrink: true }} />
          <FormControlLabel control={<Checkbox name="activo" checked={!!moneda.activo} onChange={handleCheck} />} label="Activo" />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/finanzas/monedas')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={saving}>{saving ? 'Guardando…' : 'Crear'}</Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default MonedaFormPage;
