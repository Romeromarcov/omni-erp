import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { get, post } from '../../../services/api';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import {
  Alert,
  Box,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

interface Moneda {
  id_moneda: string;
  codigo_iso: string;
  nombre: string;
}

const TIPO_TASA = [
  { value: 'OFICIAL_BCV', label: 'Oficial BCV' },
  { value: 'ESPECIAL_USUARIO', label: 'Especial Usuario' },
  { value: 'PROMEDIO_MERCADO', label: 'Promedio Mercado' },
  { value: 'FIJA', label: 'Fija' },
];

const TasaCambioCreatePage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    id_moneda_origen: '',
    id_moneda_destino: '',
    tipo_tasa: '',
    valor_tasa: '',
    fecha_tasa: '',
    hora_tasa: '',
  });
  const [error, setError] = useState('');

  const { data: monedas = [] } = useQuery<unknown, Error, Moneda[]>({
    queryKey: [`/finanzas/monedas/?id_empresa=${id_empresa}`],
    queryFn: () => get(`/finanzas/monedas/?id_empresa=${id_empresa}`),
    select: toList,
    enabled: !!id_empresa,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => post('/finanzas/tasas-cambio/', payload),
    onSuccess: () => navigate(-1),
    onError: () => setError('Error al crear tasa de cambio'),
  });

  const loading = createMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    createMutation.mutate({ id_empresa, ...form });
  };

  return (
    <PageLayout maxWidth={500}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={3}>
        <Typography variant="h5">Nueva Tasa de Cambio</Typography>
        <Button variant="outlined" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </Stack>
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          <TextField
            select
            label="Moneda Origen"
            required
            value={form.id_moneda_origen}
            onChange={e => setForm(f => ({ ...f, id_moneda_origen: e.target.value }))}
            fullWidth
          >
            <MenuItem value="">Seleccione</MenuItem>
            {monedas.map(m => <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso} - {m.nombre}</MenuItem>)}
          </TextField>
          <TextField
            select
            label="Moneda Destino"
            required
            value={form.id_moneda_destino}
            onChange={e => setForm(f => ({ ...f, id_moneda_destino: e.target.value }))}
            fullWidth
          >
            <MenuItem value="">Seleccione</MenuItem>
            {monedas.map(m => <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.codigo_iso} - {m.nombre}</MenuItem>)}
          </TextField>
          <TextField
            select
            label="Tipo de Tasa"
            required
            value={form.tipo_tasa}
            onChange={e => setForm(f => ({ ...f, tipo_tasa: e.target.value }))}
            fullWidth
          >
            <MenuItem value="">Seleccione</MenuItem>
            {TIPO_TASA.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
          </TextField>
          <TextField
            label="Valor"
            required
            type="number"
            value={form.valor_tasa}
            onChange={e => setForm(f => ({ ...f, valor_tasa: e.target.value }))}
            slotProps={{ htmlInput: { step: '0.00000001' } }}
            fullWidth
          />
          <TextField
            label="Fecha"
            required
            type="date"
            value={form.fecha_tasa}
            onChange={e => setForm(f => ({ ...f, fecha_tasa: e.target.value }))}
            slotProps={{ inputLabel: { shrink: true } }}
            fullWidth
          />
          <TextField
            label="Hora"
            type="time"
            value={form.hora_tasa}
            onChange={e => setForm(f => ({ ...f, hora_tasa: e.target.value }))}
            slotProps={{ inputLabel: { shrink: true } }}
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Registrando...' : 'Registrar'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default TasaCambioCreatePage;
